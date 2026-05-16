#!/bin/sh
# Print parcel count and suggest FIELD_MODULUS so each chunk has about TARGET_FIELDS parcels
# (using hash split: field_id %% MODULUS == remainder).
#
# Acre rule matches export: GREATEST(COALESCE(gisacre,0), COALESCE(ll_gisacre,0)) >= MIN_GISACRE.
#
# Env:
#   MIN_GISACRE       default 30
#   HAUL_AG_FILTERS   default 0 (1 = agricultural-only + skip homesite)
#   TARGET_FIELDS     default 400 — aim for ~this many parcels per chunk (tune: 250–800)
#
# Usage: ./scripts/haul_chunk_plan.sh

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
TARGET_FIELDS="${TARGET_FIELDS:-400}"

AC_EXPR="GREATEST(COALESCE(gisacre, 0::numeric), COALESCE(ll_gisacre, 0::numeric))"
CLAUSE="geom IS NOT NULL AND ${AC_EXPR} >= ${MIN_GISACRE}"
DESC="max(gisacre,ll_gisacre)>=${MIN_GISACRE}"

if [ "$HAUL_AG_FILTERS" = "1" ]; then
  CLAUSE="${CLAUSE} AND usedesc ILIKE 'Agricultural%' AND lower(trim(coalesce(usedesc, ''))) <> 'farm homesite'"
  DESC="${DESC}, ag-only, no homesite"
fi

N="$(docker exec aginfo-postgis psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -A -c \
  "SELECT COUNT(*) FROM parcels WHERE ${CLAUSE};" | tr -d ' ')"

if [ -z "$N" ] || ! echo "$N" | grep -Eq '^[0-9]+$'; then
  echo "Could not read parcel count."
  exit 1
fi

if [ "$N" -eq 0 ]; then
  echo "0 parcels match ($DESC)."
  exit 0
fi

# FIELD_MODULUS = ceil(N / TARGET)
MODULUS=$(( (N + TARGET_FIELDS - 1) / TARGET_FIELDS ))
if [ "$MODULUS" -lt 1 ]; then
  MODULUS=1
fi

PER=$(( N / MODULUS ))
# average ~ N / MODULUS if ids spread evenly across remainders

echo "Filter: ${DESC}"
echo "Total parcels (approx. routing fields): ${N}"
echo "Target per chunk: ~${TARGET_FIELDS} fields"
echo ""
echo "Suggested FIELD_MODULUS=${MODULUS}  →  ${MODULUS} sequential jobs (remainder 0..$((MODULUS - 1)))"
echo "Average ~${PER} parcels per chunk (hash by id; actual counts vary slightly)."
echo ""
echo "Run:"
echo "  FIELD_MODULUS=${MODULUS} MIN_GISACRE=${MIN_GISACRE} HAUL_AG_FILTERS=${HAUL_AG_FILTERS} ./scripts/run_haul_chunked_matrix.sh"
