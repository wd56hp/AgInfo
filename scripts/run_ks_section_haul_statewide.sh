#!/usr/bin/env bash
# Batch OSM haul: statewide ks_plss_section_site (DASC ArcGIS centroids) -> CSV chunks -> PostGIS
# haul_ks_section_facility_routes_* tables — schema file drops legacy v_ks_section_* views if present.
#
# Replaces parcel-only (~6 county) coverage: run load_ks_section_sites_from_dasc.py (in this script)
# so all ~82,896 KS sections get a centroid from Kansas DASC PLSS polygons.
#
# Env:
#   SKIP_DASC_LOAD=1 — skip ArcGIS download if ks_plss_section_site is already full (~90s saved).
#   FIELD_WORKERS=1 — parallel routing workers (default 1; use 2 only if plenty of RAM).
#   FIELD_MODULUS — hash chunk count within each band (default 48). Larger => fewer sections per run.
#   GEO_BANDS — horizontal latitude stripes; each run loads OSM only for that band's bbox + buffer (default 8).
#               Set GEO_BANDS=1 to disable (not recommended: one huge statewide graph each time).
#   MAX_MILES, SPEED_CONFIG — passthrough to build_haul_matrix.py
#
# Swap: run as root on the Unraid host (adjust SWAPFILE to cache disk):
#   SWAP_SIZE_GB=16 SWAPFILE=/mnt/cache/.aginfo_swap.img bash scripts/setup_unraid_swap.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="${ROOT}/haul_routing/runs/ks_section_statewide"
mkdir -p "$OUT"
# Geographic stripes shrink the OSM download (hash modulus alone does not — field IDs are scattered statewide).
BANDS="${GEO_BANDS:-8}"
# ~82k / 8 bands ~ 10k points/band; / MOD hash chunks for shorter runs and checkpoints.
MOD="${FIELD_MODULUS:-48}"
MAX_M="${MAX_MILES:-45}"
WORKERS="${FIELD_WORKERS:-1}"
SPEED_CFG="${SPEED_CONFIG:-aginfo/config/road_speeds.yaml}"
if [[ ! -f "$SPEED_CFG" ]]; then
  SPEED_CFG="haul_routing/config/road_speeds.yaml"
fi

run_py() {
  docker run --rm --network aginfo_aginfo-net \
    --env-file "${ROOT}/.env" \
    -e PYTHONUNBUFFERED=1 \
    -v "${ROOT}:/work" -w /work \
    python:3.11-slim bash -lc "$1"
}

PRECMD='pip install -q -r haul_routing/requirements.txt && export HAUL_PG_URL=$(python -c "import os; from urllib.parse import quote_plus; u,p,db=os.environ[\"POSTGRES_USER\"],os.environ[\"POSTGRES_PASSWORD\"],os.environ[\"POSTGRES_DB\"]; print(f\"postgresql://{quote_plus(u)}:{quote_plus(p)}@aginfo-postgis:5432/{db}\")")'

echo "=== DASC statewide section centroids -> ks_plss_section_site $(date -Is) ==="
if [[ "${SKIP_DASC_LOAD:-0}" == "1" ]]; then
  echo "SKIP_DASC_LOAD=1 — leaving ks_plss_section_site unchanged."
else
  run_py "${PRECMD} && python scripts/load_ks_section_sites_from_dasc.py --postgis-url \"\$HAUL_PG_URL\""
fi

echo "=== Export elevators (KS statewide lat/lon hull) + section sites gpkg $(date -Is) ==="
run_py "${PRECMD} && python scripts/export_postgis_for_haul.py --database-url \"\$HAUL_PG_URL\" --output-dir haul_routing/runs/ks_section_statewide --ks-grain-statewide --limit-parcels 1 --parcel-bbox=-102.05,36.99,-94.59,40.01 && python scripts/export_ks_section_sites_for_haul.py --postgis-url \"\$HAUL_PG_URL\" --out haul_routing/runs/ks_section_statewide/section_sites.gpkg"

ALL_CSV="${OUT}/routes_all.csv"
rm -f "$ALL_CSV"

# started=0: first build_haul_matrix overwrites routes_all.csv; later chunks use --append-all-csv.
started=0
for ((b = 0; b < BANDS; b++)); do
  if [[ "${BANDS}" -le 1 ]]; then
    FIELDS_GPKG="haul_routing/runs/ks_section_statewide/section_sites.gpkg"
    FIELDS_LAYER="section_sites"
    echo "=== Geo band ${b}/${BANDS} (full statewide GPKG, no sub-filter) $(date -Is) ==="
  else
    FIELDS_GPKG="haul_routing/runs/ks_section_statewide/section_sites_band_${b}.gpkg"
    echo "=== Build geo band ${b}/${BANDS} -> ${FIELDS_GPKG} $(date -Is) ==="
    run_py "${PRECMD} && python scripts/filter_section_sites_geo_band.py \
      --in haul_routing/runs/ks_section_statewide/section_sites.gpkg \
      --out ${FIELDS_GPKG} \
      --layer section_sites \
      --band ${b} --bands ${BANDS}"
    FIELDS_LAYER="section_sites"
  fi

  for r in $(seq 0 $((MOD - 1))); do
    echo "=== Haul geo ${b}/${BANDS} · hash remainder ${r}/${MOD} $(date -Is) ==="
    if [[ "${started}" -eq 0 ]]; then
      run_py "${PRECMD} && python scripts/build_haul_matrix.py \
        --fields ${FIELDS_GPKG} --fields-layer ${FIELDS_LAYER} \
        --field-id-column field_id --owner-column 0 \
        --facilities haul_routing/runs/ks_section_statewide/facilities_elevators.gpkg --facilities-layer facilities \
        --all-output haul_routing/runs/ks_section_statewide/routes_all.csv \
        --nearest-output haul_routing/runs/ks_section_statewide/routes_nearest_dummy.csv \
        --max-miles ${MAX_M} --network-buffer-miles 12 --field-workers ${WORKERS} \
        --field-modulus ${MOD} --field-remainder ${r} \
        --speed-config ${SPEED_CFG}"
    else
      run_py "${PRECMD} && python scripts/build_haul_matrix.py \
        --fields ${FIELDS_GPKG} --fields-layer ${FIELDS_LAYER} \
        --field-id-column field_id --owner-column 0 \
        --facilities haul_routing/runs/ks_section_statewide/facilities_elevators.gpkg --facilities-layer facilities \
        --all-output haul_routing/runs/ks_section_statewide/routes_all.csv \
        --append-all-csv --no-nearest \
        --max-miles ${MAX_M} --network-buffer-miles 12 --field-workers ${WORKERS} \
        --field-modulus ${MOD} --field-remainder ${r} \
        --speed-config ${SPEED_CFG}"
    fi
    started=1
  done
done

echo "=== Merge nearest $(date -Is) ==="
run_py "${PRECMD} && python scripts/merge_haul_nearest.py --all-input haul_routing/runs/ks_section_statewide/routes_all.csv --nearest-output haul_routing/runs/ks_section_statewide/routes_nearest.csv"

echo "=== Load PostGIS $(date -Is) ==="
run_py "${PRECMD} && python scripts/load_haul_csv_to_postgis.py \
  --all-csv haul_routing/runs/ks_section_statewide/routes_all.csv \
  --nearest-csv haul_routing/runs/ks_section_statewide/routes_nearest.csv \
  --postgis-url \"\$HAUL_PG_URL\" \
  --all-table haul_ks_section_facility_routes_all \
  --nearest-table haul_ks_section_facility_routes_nearest \
  --no-qgis-views"

echo "=== Re-apply KS section haul tables (drops obsolete v_ks_section_* views) $(date -Is) ==="
docker exec -i aginfo-postgis psql -U agadmin -d aginfo -v ON_ERROR_STOP=1 < "${ROOT}/db/init/15_schema_ks_section_haul.sql"

docker exec aginfo-postgis psql -U agadmin -d aginfo -c "SELECT count(*) AS nearest_rows FROM haul_ks_section_facility_routes_nearest;"
echo "Done $(date -Is)"
