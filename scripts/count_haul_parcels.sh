#!/bin/sh
# Count parcels eligible for haul export (same filters as export_postgis_for_haul / chunked runner).
# Acre rule: GREATEST(COALESCE(gisacre,0), COALESCE(ll_gisacre,0)) >= MIN_GISACRE.
# Requires: aginfo-postgis, .env with POSTGRES_PASSWORD (and optional overrides).
#
# Env:
#   MIN_GISACRE       default 30
#   HAUL_AG_FILTERS   default 0 — set 1 for --agricultural-only + --skip-homesite (smaller set)
#
# Usage: ./scripts/count_haul_parcels.sh

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

MIN_GISACRE="${MIN_GISACRE:-30}"
HAUL_AG_FILTERS="${HAUL_AG_FILTERS:-0}"

AC_EXPR="GREATEST(COALESCE(gisacre, 0::numeric), COALESCE(ll_gisacre, 0::numeric))"
CLAUSE="geom IS NOT NULL AND ${AC_EXPR} >= ${MIN_GISACRE}"
LABEL="max(gisacre, ll_gisacre) >= ${MIN_GISACRE}"

if [ "$HAUL_AG_FILTERS" = "1" ]; then
  CLAUSE="${CLAUSE} AND usedesc ILIKE 'Agricultural%' AND lower(trim(coalesce(usedesc, ''))) <> 'farm homesite'"
  LABEL="${LABEL} + agricultural + exclude homesite"
fi

echo "=== Haul parcel count ($LABEL) ==="
docker exec aginfo-postgis psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -A -c \
  "SELECT COUNT(*) FROM parcels WHERE ${CLAUSE};"
