#!/usr/bin/env python3
"""Write small GeoJSON fixtures for haul routing smoke tests (10 fields, 3 facilities)."""

from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "haul_routing" / "tests" / "fixtures"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Great Bend, KS area — compact so OSM download stays small
    base_lon, base_lat = -98.776, 38.355
    dx, dy = 0.012, 0.01
    fields = []
    for i in range(10):
        row, col = divmod(i, 5)
        x0 = base_lon + col * dx
        y0 = base_lat + row * dy
        d = 0.002
        ring = [
            [x0, y0],
            [x0 + d, y0],
            [x0 + d, y0 + d],
            [x0, y0 + d],
            [x0, y0],
        ]
        fields.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": {
                    "field_id": i + 1,
                    "owner_name": f"Test Owner {i + 1}",
                },
            }
        )

    facilities = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-98.765, 38.36]},
            "properties": {"facility_id": 101, "facility_name": "Elevator A"},
        },
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-98.82, 38.38]},
            "properties": {"facility_id": 102, "facility_name": "Elevator B"},
        },
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-98.70, 38.33]},
            "properties": {"facility_id": 103, "facility_name": "Elevator C"},
        },
    ]

    (out_dir / "fields_10_ks.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": fields}, indent=2),
        encoding="utf-8",
    )
    (out_dir / "facilities_3_ks.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": facilities}, indent=2),
        encoding="utf-8",
    )
    print("Wrote", out_dir / "fields_10_ks.geojson")
    print("Wrote", out_dir / "facilities_3_ks.geojson")


if __name__ == "__main__":
    main()
