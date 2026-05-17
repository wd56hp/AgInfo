#!/usr/bin/env python3
"""Restrict a points GeoPackage to one horizontal latitude band (for smaller OSM bboxes)."""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="inp", required=True, type=Path)
    p.add_argument("--out", dest="out", type=Path, required=True)
    p.add_argument("--layer", default=None)
    p.add_argument("--band", type=int, required=True, help="0 .. bands-1")
    p.add_argument("--bands", type=int, required=True, help="number of horizontal stripes")
    args = p.parse_args()
    if args.bands < 1:
        raise SystemExit("--bands must be >= 1")
    if not (0 <= args.band < args.bands):
        raise SystemExit("--band must satisfy 0 <= band < bands")

    layer = args.layer or "section_sites"
    gdf = gpd.read_file(args.inp, layer=args.layer or None)
    if gdf.empty:
        gdf.head(0).to_file(args.out, driver="GPKG", layer=layer)
        return

    yy = gdf.geometry.y.astype("float64")
    lo, hi = float(yy.min()), float(yy.max())
    if lo == hi:
        gdf.to_file(args.out, driver="GPKG", layer=layer)
        return

    span = hi - lo
    for b in range(args.bands):
        t0 = lo + span * (b / args.bands)
        t1 = lo + span * ((b + 1) / args.bands)
        if b < args.bands - 1:
            m = (yy >= t0) & (yy < t1)
        else:
            m = (yy >= t0) & (yy <= t1)
        if b == args.band:
            sub = gdf.loc[m].copy()
            if sub.empty:
                gdf.head(0).to_file(args.out, driver="GPKG", layer=layer)
            else:
                sub.to_file(args.out, driver="GPKG", layer=layer)
            return
    raise RuntimeError("unreachable")


if __name__ == "__main__":
    main()
