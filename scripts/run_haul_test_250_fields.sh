#!/bin/sh
# 250 real parcels (PostGIS) + elevators → haul matrix. Logs to OUT/run.log for watch/tail.
# Requires: aginfo-postgis on aginfo_aginfo-net, .env with DB password.
#
# Default clip matches elevator export corridor (parcels-only); still set HAUL_TEST_COUNTIES
# for a fast local OSM pull. Tiny boxes can yield 0 parcels if your data lies outside KS/OK etc.
#   HAUL_TEST_COUNTIES="Barton,Ellis"     — filter by county names (comma-separated)
#   HAUL_TEST_PARCEL_BBOX=-99.6,38.1,-98.8,38.5  — your own W,S,E,N in WGS84 (use = form or quoted)
#   HAUL_TEST_SPATIAL_CLIP=0              — no bbox clip (old behavior; may be very slow)
#
# Run (repo root):
#   ./scripts/run_haul_test_250_fields.sh
#
# Watch:
#   watch -n 2 'tail -30 /mnt/user/appdata/AgInfo/haul_routing/tests/out_250_fields/run.log'
#
# Also loads PostGIS tables haul_field_facility_routes_all / _nearest (same names as full run).

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

OUT="${OUT:-haul_routing/tests/out_250_fields}"
N="${HAUL_TEST_N:-250}"
export OUT N
export HAUL_TEST_SPATIAL_CLIP="${HAUL_TEST_SPATIAL_CLIP:-1}"
export HAUL_TEST_PARCEL_BBOX="${HAUL_TEST_PARCEL_BBOX:-}"
export HAUL_TEST_COUNTIES="${HAUL_TEST_COUNTIES:-}"

mkdir -p "${REPO_ROOT}/${OUT}"
LOG="${REPO_ROOT}/${OUT}/run.log"
{
  echo "=== $(date -Iseconds 2>/dev/null || date) haul test (N=${N}, OUT=${OUT}) ==="
  echo "Log file: ${LOG}"
  echo "HAUL_TEST_SPATIAL_CLIP=${HAUL_TEST_SPATIAL_CLIP} HAUL_TEST_COUNTIES=${HAUL_TEST_COUNTIES:-"(unset)"} HAUL_TEST_PARCEL_BBOX=${HAUL_TEST_PARCEL_BBOX:-"(default if clip on)"}"
  echo "Starting Docker (pip may take a minute before more lines appear) ..."
} > "${LOG}"

echo "Logging to ${LOG}"

docker rm -f haul-test-250 2>/dev/null || true

docker run --rm \
  --name haul-test-250 \
  --network aginfo_aginfo-net \
  -v "${REPO_ROOT}:/work" \
  -w /work \
  -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
  -e HAUL_PG_URL \
  -e OUT \
  -e N \
  -e HAUL_TEST_SPATIAL_CLIP \
  -e HAUL_TEST_PARCEL_BBOX \
  -e HAUL_TEST_COUNTIES \
  python:3.11-slim \
  bash -c 'set -e
    pip install --no-cache-dir -q -r haul_routing/requirements.txt
    SP="${HAUL_TEST_SPATIAL_CLIP:-1}"
    PBO="${HAUL_TEST_PARCEL_BBOX:-}"
    CT="${HAUL_TEST_COUNTIES:-}"
    DEFAULT_BBOX="-103.5,36.0,-94.0,40.5"
    cmd=(python scripts/export_postgis_for_haul.py --output-dir "$OUT" --min-gisacre 30 --limit-parcels "$N")
    if [ -n "$CT" ]; then cmd+=(--counties "$CT"); fi
    if [ "$SP" = "1" ]; then
      BBOX="${PBO:-$DEFAULT_BBOX}"
      cmd+=(--parcel-bbox="$BBOX")
      echo "Using parcel bbox: $BBOX"
    elif [ -n "$PBO" ]; then
      cmd+=(--parcel-bbox="$PBO")
    fi
    "${cmd[@]}"
    python scripts/build_haul_matrix.py \
      --fields "$OUT/parcels_fields.gpkg" --fields-layer parcels \
      --facilities "$OUT/facilities_elevators.gpkg" --facilities-layer facilities \
      --all-output "$OUT/routes_all.csv" \
      --nearest-output "$OUT/routes_nearest.csv" \
      --max-miles 30 \
      --unload-minutes 30 \
      --network-buffer-miles 10 \
      --all-gpkg "$OUT/routes_all.gpkg" \
      --nearest-gpkg "$OUT/routes_nearest.gpkg" \
      --postgis-url "$HAUL_PG_URL" \
      --postgis-all-table haul_field_facility_routes_all \
      --postgis-nearest-table haul_field_facility_routes_nearest
    echo "---- routes_nearest (head) ----"
    head -10 "$OUT/routes_nearest.csv"
    wc -l "$OUT/routes_all.csv" "$OUT/routes_nearest.csv"
  ' 2>&1 | tee -a "${LOG}"

echo "Done. Artifacts under ${REPO_ROOT}/${OUT}"

if [ -f "${REPO_ROOT}/haul_routing/sql/qgis_views.sql" ]; then
  echo "Applying QGIS views (haul)..."
  docker exec -i aginfo-postgis psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" < "${REPO_ROOT}/haul_routing/sql/qgis_views.sql"
fi
