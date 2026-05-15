# Haul routing (OSM drive network)

Compute **road-based** drive miles and drive times from **field polygon centroids** to **grain facilities**, using OpenStreetMap via [OSMnx](https://osmnx.readthedocs.io/). Great-circle distance is used only to:

1. Filter which facilities are routing candidates (default **50 miles**).
2. Tie-break when two routes have equal one-way drive time.

Final `drive_miles` and `drive_minutes_one_way` come from **shortest-path routing** on a projected drive network with **configurable per-highway speeds** (YAML).

## Smoke test (10 fields)

Requires Docker. From the repo root:

```bash
chmod +x scripts/run_haul_smoke_test.sh   # once
./scripts/run_haul_smoke_test.sh
```

This installs `haul_routing/requirements.txt` in a `python:3.11-slim` container, writes `haul_routing/tests/fixtures/fields_10_ks.geojson` and `facilities_3_ks.geojson`, runs the CLI, and leaves CSV + GeoPackage outputs under `haul_routing/tests/out_smoke/`.

### Parcels ≥30 ac + elevators (`--max-miles 30`)

From the repo root, with Docker and `aginfo-postgis` running on `aginfo_aginfo-net`:

```bash
chmod +x scripts/run_haul_full_parcels_30mi.sh
./scripts/run_haul_full_parcels_30mi.sh
```

Exports **parcels with `gisacre` ≥ 30** (with geometry) and **active grain elevators** (`facility_type_id = 1`) in a **regional bounding box** around your parcel extent (excludes far-off geocodes that would force a continent-scale OSM download). Routing uses a **30 mi** great-circle facility prefilter. Outputs go under `haul_routing/runs/parcels_30mi/`; PostGIS tables **`haul_field_facility_routes_all`** / **`haul_field_facility_routes_nearest`**; then QGIS views from `haul_routing/sql/qgis_views.sql`.

Large jobs (tens of thousands of parcels) can take a long time; one Dijkstra tree is built per parcel.

### Smaller runs: filter parcels, tighter radius, chunks

For production-sized counties, combine:

1. **Export fewer parcels** — `scripts/export_postgis_for_haul.py` supports `--agricultural-only`, `--skip-homesite` (drops “Farm Homesite”), repeatable `--exclude-usedesc`, `--min-gisacre`, and `--counties` (comma-separated, case-insensitive).
2. **Smaller facility prefilter** — lower `--max-miles` (for example **15–20**) so each field considers fewer elevators (less CPU per parcel).
3. **Chunk by parcel id** — `python scripts/build_haul_matrix.py --field-modulus M --field-remainder r --append-all-csv --no-nearest ...` runs one slice `field_id % M == r`. Concatenate into one `routes_all.csv`, then  
   `python scripts/merge_haul_nearest.py --all-input routes_all.csv --nearest-output routes_nearest.csv`.
4. **OSM cache** — OSMnx caches under `haul_routing/osmnx_cache` (override with `OSMNX_CACHE`; set `OSMNX_USE_CACHE=0` to disable). Saving a **GraphML** once (`--osm-graph`) avoids repeated Overpass downloads for later chunks.

Example driver (Docker, same network as PostGIS): `scripts/run_haul_chunked_matrix.sh` exports **ag-only** parcels, drops homesites, keeps **`gisacre` ≥ 30** by default (`MIN_GISACRE`), uses **20 mi** and **10** id-based chunks, merges `routes_nearest.csv` at the end. Tune `FIELD_MODULUS`, `MAX_MILES`, `MIN_GISACRE`, `H_OUT`, and `OSM_GRAPH` via environment variables (see comments in that script). With `--append-all-csv`, the pipeline **skips PostGIS**; load tables once after you have final CSVs.

## Installation

From the AgInfo repo root (or any environment with network access for OSM downloads):

```bash
cd /path/to/AgInfo
python -m venv .venv-haul
source .venv-haul/bin/activate   # Windows: .venv-haul\Scripts\activate
pip install -r haul_routing/requirements.txt
```

Dependencies include: `geopandas`, `shapely`, `pandas`, `networkx`, `osmnx`, **`scipy`** (required by OSMnx for snapping to projected graphs), `pyproj`, `rtree`, `tqdm`, `PyYAML`, `psycopg2-binary`, `sqlalchemy`.

**OSMnx** downloads data from the public OSM API / Overpass (rate limits apply). For large areas or repeated runs, download once and pass **`--osm-graph`** (GraphML saved with `ox.save_graphml`).

## Speed and unload configuration

Default file: **`aginfo/config/road_speeds.yaml`** (falls back to **`haul_routing/config/road_speeds.yaml`**).

- Top-level keys are OSM `highway` values (mph).
- Special keys: `dirt_road`, `gravel_road`, `unknown_road` (fallback), plus surface hints in code.
- `defaults.unload_minutes`: default unload time (overridden by CLI/API).

## Required input columns

### Fields layer

| Column | Purpose |
|--------|---------|
| **Geometry** | Polygon or point (polygons → **centroid** as routing origin). |
| **`field_id`** (or `id`, `fid`, `parcel_id`, …) | Stable identifier in outputs. |
| **`owner_name`** (optional) | If missing, falls back to `owner`, `OWNER`, `owntype` when present. |

### Facilities layer

| Column | Purpose |
|--------|---------|
| **Geometry** | Point (facility location). |
| **`facility_id`** (or `id`, …) | Stable id. |
| **`facility_name`** (or `name`, …) | Label in outputs. |

Column names can be overridden via CLI flags (`--field-id-column`, etc.).

## Example CLI

```bash
python scripts/build_haul_matrix.py \
  --fields data/fields.gpkg \
  --facilities data/facilities.gpkg \
  --all-output outputs/field_facility_routes.csv \
  --nearest-output outputs/nearest_facility_by_field.csv \
  --max-miles 50 \
  --unload-minutes 30 \
  --network-buffer-miles 10 \
  --all-gpkg outputs/field_facility_routes.gpkg \
  --nearest-gpkg outputs/nearest_facility_by_field.gpkg
```

Optional PostGIS load (tables are **replaced** each run; recreate QGIS views afterward if needed):

```bash
python scripts/build_haul_matrix.py \
  --fields data/fields.gpkg \
  --facilities data/facilities.gpkg \
  --all-output outputs/all.csv \
  --nearest-output outputs/nearest.csv \
  --postgis-url "postgresql://agadmin:YOURPASSWORD@localhost:15433/aginfo"
```

Then apply QGIS-oriented views:

```bash
docker exec -i aginfo-postgis psql -U agadmin -d aginfo -f /path/in/container/...
# or from host (copy sql into db/temp that is mounted):
psql "postgresql://..." -f haul_routing/sql/qgis_views.sql
```

## Python API

```python
from haul_routing import calculate_field_to_facility_routes

df_all, df_nearest = calculate_field_to_facility_routes(
    fields_path="data/fields.gpkg",
    facilities_path="data/facilities.gpkg",
    output_all_routes_path="outputs/all.csv",
    output_nearest_path="outputs/nearest.csv",
    max_candidate_miles=50,
    unload_minutes=30,
    speed_config_path="aginfo/config/road_speeds.yaml",
)
```

## Output columns

| Column | Description |
|--------|-------------|
| `field_id` | Field identifier |
| `owner_name` | Owner if available |
| `facility_id`, `facility_name` | Facility (null if no candidate / error row) |
| `crow_miles` | Geodesic miles (candidate filter context) |
| `drive_miles` | **Route** distance along OSM edges (one way) |
| `drive_minutes_one_way` | **Route** time from YAML speeds (one way) |
| `unload_minutes` | From config / argument |
| `one_way_drive_plus_unload_minutes` | `drive_minutes_one_way + unload_minutes` |
| `total_minutes_two_way_plus_unload` | `2 * drive_minutes_one_way + unload_minutes` |
| `is_closest_facility` | `True` for fastest route among successful candidates (`all` table only) |
| `status` | `ok`, `no_field_road_connection`, `no_facility_road_connection`, `no_facility_within_prefilter_miles`, `route_failed` |
| `field_centroid_lon`, `field_centroid_lat`, `field_centroid_wkt` | Origin used for routing |

**Nearest-only** table: one row per field; `is_closest_facility` is always `True` when a successful route exists.

## PostGIS tables and QGIS

- **`haul_field_facility_routes_all`**: all field–facility pairs attempted (with `geom` = field centroid).
- **`haul_field_facility_routes_nearest`**: one row per field.

Views **`v_haul_routes_all_qgis`** and **`v_haul_routes_nearest_qgis`** (see `haul_routing/sql/qgis_views.sql`) expose a `qgs_fid` and `geom` for QGIS.

**Note:** `to_postgis(..., if_exists="replace")` drops dependent views. After loading data, run `haul_routing/sql/qgis_views.sql` again.

## Design notes

- Routing graph is **drive**, **simplified**, **projected**; edge length is metric; speeds from YAML give **travel_time** per edge; shortest path minimizes **time**.
- Origins/destinations are **snapped** to nearest graph nodes (`osmnx.distance.nearest_nodes`).
- Heat maps: use **`drive_minutes_one_way`** or **`drive_miles`** from GeoPackage/PostGIS and symbolize; longest hauls are natural hot spots for styling.
