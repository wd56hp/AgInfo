#!/usr/bin/env bash
# Install haul_routing deps, generate 10-field fixtures, run routing smoke test (Docker).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="${HAUL_TEST_IMAGE:-python:3.11-slim}"
OUT_DIR="${REPO_ROOT}/haul_routing/tests/out_smoke"

mkdir -p "${OUT_DIR}"

echo "Using image: ${IMAGE}"
docker pull -q "${IMAGE}"

docker run --rm \
  -v "${REPO_ROOT}:/work" \
  -w /work \
  -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
  "${IMAGE}" \
  bash -c '
    set -e
    pip install --no-cache-dir -q -r haul_routing/requirements.txt
    python scripts/generate_haul_test_fixtures.py
    python scripts/build_haul_matrix.py \
      --fields haul_routing/tests/fixtures/fields_10_ks.geojson \
      --facilities haul_routing/tests/fixtures/facilities_3_ks.geojson \
      --all-output haul_routing/tests/out_smoke/routes_all.csv \
      --nearest-output haul_routing/tests/out_smoke/routes_nearest.csv \
      --max-miles 50 \
      --unload-minutes 30 \
      --network-buffer-miles 5 \
      --all-gpkg haul_routing/tests/out_smoke/routes_all.gpkg \
      --nearest-gpkg haul_routing/tests/out_smoke/routes_nearest.gpkg
    echo "---- routes_nearest (head) ----"
    head -15 haul_routing/tests/out_smoke/routes_nearest.csv
    echo "---- row counts ----"
    wc -l haul_routing/tests/out_smoke/routes_all.csv haul_routing/tests/out_smoke/routes_nearest.csv
  '

echo "Smoke test artifacts under ${OUT_DIR}"
