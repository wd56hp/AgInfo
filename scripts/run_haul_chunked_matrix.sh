#!/bin/sh
# Full-statement haul matrix in manageable pieces:
# 1) Export parcels (≥ MIN_GISACRE) + elevators once to GeoPackage.
# 2) Run build_haul_matrix FIELD_MODULUS times: field_id % MODULUS == 0 .. MODULUS-1, append CSV.
# 3) merge_haul_nearest.py → routes_nearest.csv
#
# "All fields over 30 acres" (no agricultural-only filter): default HAUL_AG_FILTERS=0.
# Set HAUL_AG_FILTERS=1 to match older behavior (--agricultural-only --skip-homesite), fewer parcels.
#
# How many chunks? Run first:
#   ./scripts/haul_chunk_plan.sh
# It prints total parcel count and suggests FIELD_MODULUS for ~TARGET_FIELDS parcels per chunk
# (default ~400; your 250-field test was quicker — use TARGET_FIELDS=250 for more, smaller jobs).
#
# Rule of thumb: each chunk downloads OSM once — reuse OSM_GRAPH after first chunk for similar bbox.
# Shorter wall-clock: lower MAX_MILES (e.g. 20), smaller TARGET_FIELDS / higher FIELD_MODULUS.
#
# Env (optional):
#   FIELD_MODULUS     required for splitting; get from haul_chunk_plan.sh (default 20 placeholder)
#   MAX_MILES         default 20
#   MIN_GISACRE       default 30
#   HAUL_AG_FILTERS   default 0 — set 1 for agricultural-only + skip homesite
#   H_OUT             default haul_routing/runs/parcels_chunked
#   OSM_GRAPH         optional GraphML under /work
#   HAUL_LOAD_POSTGIS default 0 — set 1 to load merged CSVs into PostGIS when job finishes
#   OSMNX_USE_CACHE   default 1
#
# Usage:
#   chmod +x scripts/count_haul_parcels.sh scripts/haul_chunk_plan.sh scripts/run_haul_chunked_matrix.sh
#   ./scripts/haul_chunk_plan.sh
#   FIELD_MODULUS=... ./scripts/run_haul_chunked_matrix.sh

set -eu
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [ -f .env ]; then
  POSTGRES_USER="$(grep -E '^POSTGRES_USER=' .env | head -1 | cut -d= -f2- | tr -d '\r')"
  POSTGRES_PASSWORD="$(grep -E '^POSTGRES_PASSWORD=' .env | head -1 | cut -d= -f2- | tr -d '\r')"
  POSTGRES_DB="$(grep -E '^POSTGRES_DB=' .env | head -1 | cut -d= -f2- | tr -d '\r')"
  export POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB
fi

: "${POSTGRES_USER:=agadmin}"
: "${POSTGRES_DB:=aginfo}"
: "${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}"
export HAUL_PG_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@aginfo-postgis:5432/${POSTGRES_DB}"

FIELD_MODULUS="${FIELD_MODULUS:-20}"
MAX_MILES="${MAX_MILES:-20}"
MIN_GISACRE="${MIN_GISACRE:-30}"
HAUL_AG_FILTERS="${HAUL_AG_FILTERS:-0}"
H_OUT="${H_OUT:-haul_routing/runs/parcels_chunked}"
OSM_GRAPH="${OSM_GRAPH:-}"
HAUL_LOAD_POSTGIS="${HAUL_LOAD_POSTGIS:-0}"

mkdir -p "${REPO_ROOT}/${H_OUT}"

export FIELD_MODULUS MAX_MILES MIN_GISACRE HAUL_AG_FILTERS H_OUT OSM_GRAPH HAUL_LOAD_POSTGIS HAUL_PG_URL

docker run --rm -i \
  --network aginfo_aginfo-net \
  -v "${REPO_ROOT}:/work" \
  -w /work \
  -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
  -e HAUL_PG_URL \
  -e FIELD_MODULUS \
  -e MAX_MILES \
  -e MIN_GISACRE \
  -e HAUL_AG_FILTERS \
  -e H_OUT \
  -e OSM_GRAPH \
  -e HAUL_LOAD_POSTGIS \
  -e OSMNX_USE_CACHE="${OSMNX_USE_CACHE:-1}" \
  python:3.11-slim \
  bash -s <<'HAUL_CHUNKED_INNER'
set -e
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
pip install --no-cache-dir -q -r haul_routing/requirements.txt
EXP=(python scripts/export_postgis_for_haul.py --output-dir "$H_OUT" --min-gisacre "$MIN_GISACRE")
if [ "$HAUL_AG_FILTERS" = "1" ]; then
  EXP+=(--agricultural-only --skip-homesite)
  echo "Export: agricultural-only + skip homesite"
else
  echo "Export: all parcels with max(gisacre, ll_gisacre) >= ${MIN_GISACRE} (no ag-only filter)"
fi
"${EXP[@]}"
rm -f "$H_OUT/routes_all.csv" "$H_OUT/routes_nearest.csv"
GRAPH_ARGS=""
if [ -n "$OSM_GRAPH" ]; then GRAPH_ARGS="--osm-graph=${OSM_GRAPH}"; fi
i=0
while [ "$i" -lt "$FIELD_MODULUS" ]; do
  echo "=== Chunk remainder=$i / modulus=$FIELD_MODULUS ==="
  python scripts/build_haul_matrix.py \
    --fields "$H_OUT/parcels_fields.gpkg" \
    --fields-layer parcels \
    --facilities "$H_OUT/facilities_elevators.gpkg" \
    --facilities-layer facilities \
    --all-output "$H_OUT/routes_all.csv" \
    --no-nearest \
    --max-miles "$MAX_MILES" \
    --unload-minutes 30 \
    --network-buffer-miles 10 \
    --field-modulus "$FIELD_MODULUS" \
    --field-remainder "$i" \
    --append-all-csv \
    $GRAPH_ARGS
  i=$((i + 1))
done
python scripts/merge_haul_nearest.py \
  --all-input "$H_OUT/routes_all.csv" \
  --nearest-output "$H_OUT/routes_nearest.csv"
echo "--- merged ---"
wc -l "$H_OUT/routes_all.csv" "$H_OUT/routes_nearest.csv" || true
if [ "$HAUL_LOAD_POSTGIS" = "1" ]; then
  echo "--- loading PostGIS ---"
  python scripts/load_haul_csv_to_postgis.py \
    --all-csv "$H_OUT/routes_all.csv" \
    --nearest-csv "$H_OUT/routes_nearest.csv" \
    --postgis-url "$HAUL_PG_URL"
fi
HAUL_CHUNKED_INNER

echo "Chunked haul matrix artifacts: ${REPO_ROOT}/${H_OUT}/"
if [ -f "${REPO_ROOT}/haul_routing/sql/qgis_views.sql" ]; then
  echo "Applying QGIS views..."
  docker exec -i aginfo-postgis psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" < "${REPO_ROOT}/haul_routing/sql/qgis_views.sql"
fi

echo "Done."
