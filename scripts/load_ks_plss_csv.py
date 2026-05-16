#!/usr/bin/env python3
"""Create KS PLSS tables/views (if needed) and load the three PLSS CSV exports into PostGIS."""

from __future__ import annotations

import argparse
import os
import sys
from io import StringIO
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

SECTION_RENAME = {
    "\ufeffFeature ID": "feature_id",
    "Feature ID": "feature_id",
    "Object ID": "object_id",
    "DASC PLSS Indicator": "dasc_plss_indicator",
    "Perimeter Length": "perimeter_length",
    "PLSS NAD83 ID": "plss_nad83_id",
    "PLSS Alternate ID": "plss_alternate_id",
    "Meridian Flag": "meridian_flag",
    "Meridian Number": "meridian_number",
    "Township Flag": "township_flag",
    "Township Number": "township_number",
    "Range Flag": "range_flag",
    "Range Number": "range_number",
    "Section Flag": "section_flag",
    "Section Number": "section_number",
    "Excluded Area Indicator A": "excluded_area_indicator_a",
    "Excluded Area Indicator B": "excluded_area_indicator_b",
    "Section-Range-Township": "section_range_township",
    "Shape Area (No Data)": "shape_area_no_data",
    "Shape Length": "shape_length",
    "Computed Shape Area": "computed_shape_area",
    "Computed Shape Length": "computed_shape_length",
}

TR_RENAME = {
    "OBJECTID": "objectid",
    "T_R": "t_r",
    "Shape__Area": "shape__area",
    "Shape__Length": "shape__length",
}

QQ_RENAME = {
    "FID": "fid",
    "OBJECTID": "objectid",
    "RECNMBR": "recnmbr",
    "TRS_Q2": "trs_q2",
    "SHAPE_AREA": "shape_area",
    "SHAPE_LEN": "shape_len",
    "Shape__Area": "shape_area_computed",
    "Shape__Length": "shape_len_computed",
}

SECTION_COLS = [
    "feature_id",
    "object_id",
    "dasc_plss_indicator",
    "perimeter_length",
    "plss_nad83_id",
    "plss_alternate_id",
    "meridian_flag",
    "meridian_number",
    "township_flag",
    "township_number",
    "range_flag",
    "range_number",
    "section_flag",
    "section_number",
    "excluded_area_indicator_a",
    "excluded_area_indicator_b",
    "section_range_township",
    "shape_area_no_data",
    "shape_length",
    "computed_shape_area",
    "computed_shape_length",
]

TR_COLS = ["objectid", "t_r", "shape__area", "shape__length"]
QQ_COLS = [
    "fid",
    "objectid",
    "recnmbr",
    "trs_q2",
    "shape_area",
    "shape_len",
    "shape_area_computed",
    "shape_len_computed",
]


def _apply_sql_file(engine: Engine, path: Path) -> None:
    raw_text = path.read_text(encoding="utf-8")
    stripped = "\n".join(ln for ln in raw_text.splitlines() if not ln.strip().startswith("--"))
    # Split on semicolon followed by newline (end of statement)
    stmts = []
    buf: list[str] = []
    for line in stripped.splitlines():
        buf.append(line)
        if line.rstrip().endswith(";"):
            stmt = "\n".join(buf).strip()
            if stmt:
                stmts.append(stmt.rstrip(";"))
            buf = []
    if buf:
        stmt = "\n".join(buf).strip()
        if stmt:
            stmts.append(stmt.rstrip(";"))

    with engine.begin() as conn:
        for stmt in stmts:
            if not stmt.strip():
                continue
            conn.execute(text(stmt + ";"))


def _copy_chunks(
    engine: Engine,
    csv_path: Path,
    table: str,
    columns: list[str],
    rename: dict[str, str],
    chunksize: int,
) -> int:
    total = 0
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        for chunk in pd.read_csv(
            csv_path,
            chunksize=chunksize,
            encoding="utf-8-sig",
            low_memory=False,
        ):
            chunk = chunk.rename(columns=rename)
            for c in columns:
                if c not in chunk.columns:
                    raise ValueError(f"Missing column {c!r} in {csv_path} after rename; got {list(chunk.columns)}")
            chunk = chunk[columns]
            buf = StringIO()
            chunk.to_csv(buf, index=False, header=False, na_rep="\\N")
            buf.seek(0)
            col_sql = ", ".join(f'"{c}"' for c in columns)
            cur.copy_expert(
                f'COPY "{table}" ({col_sql}) FROM STDIN WITH (FORMAT csv, NULL \'\\N\')',
                buf,
            )
            total += len(chunk)
        raw.commit()
    finally:
        raw.close()
    return total


def _pg_url_from_env() -> str:
    u = os.environ.get("HAUL_PG_URL", "").strip()
    if u:
        return u
    user = os.environ.get("POSTGRES_USER", "").strip()
    password = os.environ.get("POSTGRES_PASSWORD", "").strip()
    db = os.environ.get("POSTGRES_DB", "").strip()
    if user and password and db:
        host = os.environ.get("POSTGRES_HOST", "localhost").strip()
        port = os.environ.get("POSTGRES_PORT", os.environ.get("POSTGIS_HOST_PORT", "5432")).strip()
        from urllib.parse import quote_plus

        return f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{db}"

    env_path = _ROOT / ".env"
    if not env_path.is_file():
        return ""
    vals: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v0 = line.partition("=")
        k, v = k.strip(), v0.strip().strip("'").strip('"')
        if k:
            vals[k] = v
    user = vals.get("POSTGRES_USER", "agadmin")
    password = vals.get("POSTGRES_PASSWORD", "")
    db = vals.get("POSTGRES_DB", "aginfo")
    if not password:
        return ""
    host = vals.get("POSTGRES_HOST", "localhost")
    port = vals.get("POSTGRES_PORT", vals.get("POSTGIS_HOST_PORT", "5432"))
    from urllib.parse import quote_plus

    return f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{db}"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--postgis-url",
        default=os.environ.get("HAUL_PG_URL", ""),
        help="SQLAlchemy URL (default: HAUL_PG_URL or .env toward aginfo-postgis)",
    )
    p.add_argument(
        "--section-csv",
        type=Path,
        default=_ROOT / "Temp" / "Kansas_PLSS_View_-3631500939410394299.csv",
    )
    p.add_argument(
        "--township-range-csv",
        type=Path,
        default=_ROOT / "Temp" / "PLSS-_Township_Range.csv",
    )
    p.add_argument(
        "--qq-csv",
        type=Path,
        default=_ROOT / "Temp" / "PLSS_Section_Township_Range_QQ_(Quarter_Quarter).csv",
    )
    p.add_argument("--schema-sql", type=Path, default=_ROOT / "db" / "init" / "13_schema_ks_plss.sql")
    p.add_argument("--skip-schema", action="store_true", help="Do not run CREATE TABLE / VIEW SQL")
    p.add_argument("--chunk-rows", type=int, default=150_000, help="Rows per COPY batch (QQ file is large)")
    args = p.parse_args()

    url = (args.postgis_url or _pg_url_from_env()).strip()
    if not url:
        raise SystemExit("Set --postgis-url or HAUL_PG_URL (or POSTGRES_* in .env for Docker hostname)")

    for label, path in (
        ("section", args.section_csv),
        ("township-range", args.township_range_csv),
        ("qq", args.qq_csv),
    ):
        if not path.is_file():
            raise SystemExit(f"Missing {label} CSV: {path}")

    engine = create_engine(url)

    if not args.skip_schema:
        _apply_sql_file(engine, args.schema_sql)

    with engine.begin() as conn:  # type: Connection
        conn.execute(text("TRUNCATE ks_plss_quarter_quarter, ks_plss_section, ks_plss_township_range"))

    n_tr = _copy_chunks(
        engine, args.township_range_csv, "ks_plss_township_range", TR_COLS, TR_RENAME, args.chunk_rows
    )
    n_sec = _copy_chunks(engine, args.section_csv, "ks_plss_section", SECTION_COLS, SECTION_RENAME, args.chunk_rows)
    n_qq = _copy_chunks(
        engine, args.qq_csv, "ks_plss_quarter_quarter", QQ_COLS, QQ_RENAME, args.chunk_rows
    )

    print(
        f"Loaded ks_plss_township_range: {n_tr} rows, "
        f"ks_plss_section: {n_sec} rows, "
        f"ks_plss_quarter_quarter: {n_qq} rows"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
