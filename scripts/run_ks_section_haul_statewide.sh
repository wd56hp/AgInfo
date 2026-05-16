#!/usr/bin/env bash
# Batch OSM haul: statewide ks_plss_section_site (DASC ArcGIS centroids) -> CSV chunks -> PostGIS
# haul_ks_section_facility_routes_* -> re-apply views incl. v_ks_section_nearest_facility.
#
# Replaces parcel-only (~6 county) coverage: run load_ks_section_sites_from_dasc.py (in this script)
# so all ~82,896 KS sections get a centroid from Kansas DASC PLSS polygons.
#
# Env: SKIP_DASC_LOAD=1 — skip ArcGIS download if ks_plss_section_site is already full (~90s saved).
# Env: FIELD_WORKERS=1 — recommended if Docker host runs out of memory during routing.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="${ROOT}/haul_routing/runs/ks_section_statewide"
mkdir -p "$OUT"
# ~82k sections: default 64 chunks ≈ 1.3k sections each (tune FIELD_MODULUS).
# Default 2 workers — statewide OSM graph is huge; set FIELD_WORKERS=1 if the host OOMs during routing.
MOD="${FIELD_MODULUS:-64}"
MAX_M="${MAX_MILES:-45}"
WORKERS="${FIELD_WORKERS:-2}"
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

for r in $(seq 0 $((MOD - 1))); do
  echo "=== Haul chunk remainder ${r}/${MOD} $(date -Is) ==="
  if [[ "$r" -eq 0 ]]; then
    run_py "${PRECMD} && python scripts/build_haul_matrix.py \
      --fields haul_routing/runs/ks_section_statewide/section_sites.gpkg --fields-layer section_sites \
      --field-id-column field_id --owner-column 0 \
      --facilities haul_routing/runs/ks_section_statewide/facilities_elevators.gpkg --facilities-layer facilities \
      --all-output haul_routing/runs/ks_section_statewide/routes_all.csv \
      --nearest-output haul_routing/runs/ks_section_statewide/routes_nearest_dummy.csv \
      --max-miles ${MAX_M} --network-buffer-miles 12 --field-workers ${WORKERS} \
      --field-modulus ${MOD} --field-remainder ${r} \
      --speed-config ${SPEED_CFG}"
  else
    run_py "${PRECMD} && python scripts/build_haul_matrix.py \
      --fields haul_routing/runs/ks_section_statewide/section_sites.gpkg --fields-layer section_sites \
      --field-id-column field_id --owner-column 0 \
      --facilities haul_routing/runs/ks_section_statewide/facilities_elevators.gpkg --facilities-layer facilities \
      --all-output haul_routing/runs/ks_section_statewide/routes_all.csv \
      --append-all-csv --no-nearest \
      --max-miles ${MAX_M} --network-buffer-miles 12 --field-workers ${WORKERS} \
      --field-modulus ${MOD} --field-remainder ${r} \
      --speed-config ${SPEED_CFG}"
  fi
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

echo "=== Re-apply KS section views $(date -Is) ==="
docker exec -i aginfo-postgis psql -U agadmin -d aginfo -v ON_ERROR_STOP=1 < "${ROOT}/db/init/15_schema_ks_section_haul.sql"
docker exec -i aginfo-postgis psql -U agadmin -d aginfo -v ON_ERROR_STOP=1 < "${ROOT}/db/init/17_view_ks_section_nearest_facility.sql"

docker exec aginfo-postgis psql -U agadmin -d aginfo -c "SELECT count(*) AS nearest_rows FROM v_ks_section_nearest_facility;"
echo "Done $(date -Is)"
