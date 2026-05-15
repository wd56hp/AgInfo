#!/bin/sh
# Export filtered parcels once, route in parallel chunks (field_id % MODULUS == remainder), merge nearest.
# Reduces wall time and lets you cap facility prefilter (--max-miles) and parcel count.
#
# Env (optional):
#   FIELD_MODULUS   default 10
#   MAX_MILES       default 20 (great-circle facility prefilter)
#   MIN_GISACRE     default 30 (parcels below this gisacre are excluded)
#   H_OUT           output dir under repo (default haul_routing/runs/parcels_chunked)
#   OSM_GRAPH       optional GraphML path under /work (e.g. haul_routing/runs/plains.graphml)
#   OSMNX_USE_CACHE  set to 0 to disable OSMnx on-disk cache (slower repeat, less disk)
#
# Usage: from repo root, with aginfo-postgis on aginfo_aginfo-net:
#   chmod +x scripts/run_haul_chunked_matrix.sh
#   ./scripts/run_haul_chunked_matrix.sh

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

FIELD_MODULUS="${FIELD_MODULUS:-10}"
MAX_MILES="${MAX_MILES:-20}"
MIN_GISACRE="${MIN_GISACRE:-30}"
H_OUT="${H_OUT:-haul_routing/runs/parcels_chunked}"
OSM_GRAPH="${OSM_GRAPH:-}"

mkdir -p "${REPO_ROOT}/${H_OUT}"

docker run --rm \
  --network aginfo_aginfo-net \
  -v "${REPO_ROOT}:/work" \
  -w /work \
  -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
  -e HAUL_PG_URL \
  -e FIELD_MODULUS \
  -e MAX_MILES \
  -e MIN_GISACRE \
  -e H_OUT \
  -e OSM_GRAPH \
  -e OSMNX_USE_CACHE="${OSMNX_USE_CACHE:-1}" \
  python:3.11-slim \
  bash -c 'set -e
    pip install --no-cache-dir -q -r haul_routing/requirements.txt
    python scripts/export_postgis_for_haul.py --output-dir "$H_OUT" \
      --agricultural-only --skip-homesite --min-gisacre "$MIN_GISACRE"
    rm -f "$H_OUT/routes_all.csv" "$H_OUT/routes_nearest.csv"
    GRAPH_ARGS=""
    if [ -n "$OSM_GRAPH" ]; then GRAPH_ARGS="--osm-graph $OSM_GRAPH"; fi
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
    echo "--- done ---"
    wc -l "$H_OUT/routes_all.csv" "$H_OUT/routes_nearest.csv" || true
  '

echo "Chunked haul matrix finished. Load PostGIS + QGIS views separately if needed (see haul_routing/README.md)."
