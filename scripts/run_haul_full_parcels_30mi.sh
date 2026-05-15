#!/bin/sh
# Export parcels (gisacre >= 30) + grain elevators from PostGIS, run haul matrix (30 mi facility prefilter).
# Runs inside Docker (Python + OSMnx). Requires: aginfo-postgis up, .env with DB password.

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

H_OUT="haul_routing/runs/parcels_30mi"
mkdir -p "${REPO_ROOT}/${H_OUT}"

echo "HAUL_PG_URL -> aginfo-postgis / ${POSTGRES_DB} as ${POSTGRES_USER}"
echo "Outputs -> ${H_OUT}/"

docker run --rm \
  --network aginfo_aginfo-net \
  -v "${REPO_ROOT}:/work" \
  -w /work \
  -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
  -e HAUL_PG_URL \
  -e H_OUT \
  python:3.11-slim \
  bash -c 'set -e
    pip install --no-cache-dir -q -r haul_routing/requirements.txt
    python scripts/export_postgis_for_haul.py --output-dir "$H_OUT" --min-gisacre 30
    python scripts/build_haul_matrix.py \
      --fields "$H_OUT/parcels_fields.gpkg" \
      --fields-layer parcels \
      --facilities "$H_OUT/facilities_elevators.gpkg" \
      --facilities-layer facilities \
      --all-output "$H_OUT/routes_all.csv" \
      --nearest-output "$H_OUT/routes_nearest.csv" \
      --max-miles 30 \
      --unload-minutes 30 \
      --network-buffer-miles 10 \
      --all-gpkg "$H_OUT/routes_all.gpkg" \
      --nearest-gpkg "$H_OUT/routes_nearest.gpkg" \
      --postgis-url "$HAUL_PG_URL" \
      --postgis-all-table haul_field_facility_routes_all \
      --postgis-nearest-table haul_field_facility_routes_nearest
    echo "--- routes_nearest (first lines) ---"
    head -5 "$H_OUT/routes_nearest.csv"
    wc -l "$H_OUT/routes_all.csv" "$H_OUT/routes_nearest.csv"
  '

echo "Recreating QGIS views..."
if [ -f haul_routing/sql/qgis_views.sql ]; then
  docker exec -i aginfo-postgis psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" < haul_routing/sql/qgis_views.sql
fi

echo "Done."
