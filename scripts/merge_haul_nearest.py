#!/usr/bin/env python3
"""Build routes_nearest.csv from routes_all.csv (after chunked haul_routing runs)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from haul_routing.pipeline import build_nearest_from_routes_all  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(
        description="One row per field_id: best OK route by drive time, else first row (matches build_haul_matrix)."
    )
    p.add_argument("--all-input", required=True, help="Concatenated routes_all.csv")
    p.add_argument("--nearest-output", required=True, help="Output routes_nearest.csv")
    args = p.parse_args()

    inp = Path(args.all_input)
    if not inp.is_file():
        raise SystemExit(f"Missing {inp}")

    df = pd.read_csv(inp)
    df_nn = build_nearest_from_routes_all(df)
    out = Path(args.nearest_output)
    out.parent.mkdir(parents=True, exist_ok=True)
    df_nn.to_csv(out, index=False)
    print(f"Wrote {len(df_nn)} rows -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
