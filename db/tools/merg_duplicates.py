#!/usr/bin/env python3
"""
Global interactive deduper:
  1) Merge duplicate companies first (repoint all FKs)
  2) Merge duplicate facilities in groups (2+):
     - create NEW facility
     - archive originals into public.deactivated_facilities
     - set originals INACTIVE
     - repoint all FKs from old facility_ids -> new facility_id

Requires:
  pip install psycopg2-binary python-dotenv

.env expects:
  POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGIS_HOST_PORT
Optional:
  PGHOST (default localhost)

Safety:
  Default is DRY RUN unless you pass --apply

Notes:
  - Auto-discovers FK references using pg_catalog, so you don't have to maintain REPOINT lists.
  - Company table in schema doesn't have status; this script (optionally) archives companies to
    public.deactivated_company (or deactivated_companies) IF that table exists; otherwise it just leaves old company rows
    in place (but repointed so they no longer have dependents).
"""

import os
import re
import sys
import argparse
from typing import Any, Dict, List, Optional, Tuple, Set
from collections import defaultdict

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

# ----------------------------
# Address normalization (CR -> County Road)
# ----------------------------
CR_PATTERNS = [
    (re.compile(r"\bC\.?\s*R\.?\b", re.IGNORECASE), "County Road"),
    (re.compile(r"\bCo\.?\s*Rd\.?\b", re.IGNORECASE), "County Road"),
    (re.compile(r"\bCty\.?\s*Rd\.?\b", re.IGNORECASE), "County Road"),
]
BAD = {"", "n/a", "na", "none", "unknown", "null", "-", "--"}

COMPANY_SUFFIXES = [
    "inc", "inc.", "incorporated",
    "corp", "corp.", "corporation",
    "llc", "l.l.c", "l.l.c.", "ltd", "ltd.",
    "co", "co.", "company",
]

# ----------------------------
# DB helpers
# ----------------------------
def db_connect():
    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("POSTGIS_HOST_PORT")
    if not port:
        raise SystemExit("ERROR: POSTGIS_HOST_PORT missing in .env")
    for k in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"):
        if not os.environ.get(k):
            raise SystemExit(f"ERROR: {k} missing in .env")
    return psycopg2.connect(
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=host,
        port=port,
    )

def table_columns(conn, schema: str, table: str) -> Set[str]:
    sql = """
      SELECT column_name
      FROM information_schema.columns
      WHERE table_schema = %s AND table_name = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (schema, table))
        return {r[0] for r in cur.fetchall()}

def table_exists(conn, schema: str, table: str) -> bool:
    sql = """
      SELECT 1
      FROM information_schema.tables
      WHERE table_schema = %s AND table_name = %s
      LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(sql, (schema, table))
        return cur.fetchone() is not None

def get_deactivated_companies_table(conn) -> Optional[str]:
    """Get the name of the deactivated companies table (preferring singular form)"""
    # Check for singular first (user created deactivated_company)
    if table_exists(conn, "public", "deactivated_company"):
        return "deactivated_company"
    # Fall back to plural if singular doesn't exist
    if table_exists(conn, "public", "deactivated_companies"):
        return "deactivated_companies"
    return None

def get_fk_references(conn, referenced_schema: str, referenced_table: str) -> List[Tuple[str, str, str]]:
    """
    Find all single-column foreign keys that reference referenced_schema.referenced_table.
    Returns list of (fk_schema, fk_table, fk_column).
    """
    sql = """
    SELECT
      nsp_child.nspname  AS fk_schema,
      rel_child.relname  AS fk_table,
      att_child.attname  AS fk_column
    FROM pg_constraint con
    JOIN pg_class rel_parent ON rel_parent.oid = con.confrelid
    JOIN pg_namespace nsp_parent ON nsp_parent.oid = rel_parent.relnamespace
    JOIN pg_class rel_child ON rel_child.oid = con.conrelid
    JOIN pg_namespace nsp_child ON nsp_child.oid = rel_child.relnamespace
    JOIN unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
    JOIN pg_attribute att_child ON att_child.attrelid = con.conrelid AND att_child.attnum = k.attnum
    WHERE con.contype = 'f'
      AND nsp_parent.nspname = %s
      AND rel_parent.relname = %s
      AND array_length(con.conkey, 1) = 1
    ORDER BY fk_schema, fk_table, fk_column
    """
    with conn.cursor() as cur:
        cur.execute(sql, (referenced_schema, referenced_table))
        return [(r[0], r[1], r[2]) for r in cur.fetchall()]

def count_dependents(conn, fk_schema: str, fk_table: str, fk_col: str, ids: List[int]) -> int:
    sql = f"SELECT COUNT(*) FROM {fk_schema}.{fk_table} WHERE {fk_col} = ANY(%s)"
    with conn.cursor() as cur:
        cur.execute(sql, (ids,))
        return int(cur.fetchone()[0])

def repoint_dependents(conn, fk_schema: str, fk_table: str, fk_col: str, old_ids: List[int], new_id: int) -> int:
    """
    Repoint foreign keys from old_ids to new_id.
    For facility table, handles unique constraint violations by skipping conflicting records.
    """
    # Special handling for facility table with unique constraint on (company_id, name, city, state)
    if fk_table == "facility" and fk_col == "company_id":
        # Check for conflicts: facilities that would violate unique constraint
        conflict_sql = """
            SELECT f1.facility_id, f1.name, f1.city, f1.state
            FROM public.facility f1
            WHERE f1.company_id = ANY(%s)
            AND EXISTS (
                SELECT 1 FROM public.facility f2
                WHERE f2.company_id = %s
                AND f2.name = f1.name
                AND COALESCE(f2.city, '') = COALESCE(f1.city, '')
                AND COALESCE(f2.state, '') = COALESCE(f1.state, '')
            )
        """
        with conn.cursor() as cur:
            cur.execute(conflict_sql, (old_ids, new_id))
            conflicts = cur.fetchall()
            
            if conflicts:
                conflict_ids = [c[0] for c in conflicts]
                print(f"    ⚠️  Warning: {len(conflicts)} facilities would violate unique constraint, skipping repoint:")
                for c in conflicts:
                    print(f"        facility_id={c[0]}: '{c[1]}', {c[2]}, {c[3]}")
                # Update only non-conflicting records
                exclude_sql = """
                    UPDATE public.facility 
                    SET company_id = %s 
                    WHERE company_id = ANY(%s) 
                    AND facility_id != ALL(%s)
                """
                cur.execute(exclude_sql, (new_id, old_ids, conflict_ids))
                return cur.rowcount
            else:
                # No conflicts, proceed normally
                sql = "UPDATE public.facility SET company_id = %s WHERE company_id = ANY(%s)"
                cur.execute(sql, (new_id, old_ids))
                return cur.rowcount
    else:
        # Normal repoint for other tables
        sql = f"UPDATE {fk_schema}.{fk_table} SET {fk_col} = %s WHERE {fk_col} = ANY(%s)"
        with conn.cursor() as cur:
            cur.execute(sql, (new_id, old_ids))
            return cur.rowcount

# ----------------------------
# Normalization
# ----------------------------
def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def normalize_value(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, str):
        t = norm_ws(v)
        return t if t else None
    return v

def clean_street(s: Optional[str]) -> str:
    if not s:
        return ""
    x = norm_ws(s)
    if x.lower() in BAD:
        return ""
    for pat, repl in CR_PATTERNS:
        x = pat.sub(repl, x)
    x = re.sub(r"\bCounty\s+Rd\b", "County Road", x, flags=re.IGNORECASE)
    return norm_ws(x)

def normalize_company_name(name: Optional[str]) -> str:
    if not name:
        return ""
    n = norm_ws(name).lower()
    n = re.sub(r"[^\w\s&-]", "", n)  # drop punctuation except word/space/&/-
    parts = [p for p in n.split() if p not in COMPANY_SUFFIXES]
    return " ".join(parts)

def names_differ_only_trivially(name1: Optional[str], name2: Optional[str]) -> bool:
    """
    Check if two names differ only by punctuation or suffixes (LLC, Co, etc.).
    Returns True if normalized names are identical.
    """
    if not name1 or not name2:
        return False
    norm1 = normalize_company_name(name1)
    norm2 = normalize_company_name(name2)
    return norm1 == norm2 and len(norm1) > 0

# ----------------------------
# Pretty display (show matches, show only changed/combined fields)
# ----------------------------
def fmt(v: Any, maxlen: int = 160) -> str:
    if v is None:
        return "∅"
    if isinstance(v, bool):
        return "true" if v else "false"
    s = str(v).replace("\r\n", "\n").strip()
    if len(s) > maxlen:
        return s[: maxlen - 3] + "..."
    return s

def ask_yes_no(prompt: str) -> bool:
    while True:
        ans = input(prompt).strip().lower()
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("Please enter y/n.")

# ----------------------------
# Company merge (phase A)
# ----------------------------
def fetch_companies(conn) -> List[Dict[str, Any]]:
    """Fetch companies, excluding those already merged (in deactivated_company/deactivated_companies)"""
    # Exclude companies that have been merged/archived
    exclude_clause = ""
    deact_table = get_deactivated_companies_table(conn)
    if deact_table:
        # Check what columns the deactivated table has
        deact_cols = table_columns(conn, "public", deact_table)
        # Try to find the ID column - could be original_company_id or company_id
        id_col = "original_company_id" if "original_company_id" in deact_cols else ("company_id" if "company_id" in deact_cols else None)
        if id_col:
            # Check if reason column exists for filtering
            if "reason" in deact_cols:
                exclude_clause = f"AND company_id NOT IN (SELECT {id_col} FROM public.{deact_table} WHERE reason = 'MERGED')"
            else:
                # If no reason column, exclude all companies in the deactivated table
                exclude_clause = f"AND company_id NOT IN (SELECT {id_col} FROM public.{deact_table})"
    
    sql = f"""
        SELECT company_id, name, website_url, phone_main, notes 
        FROM public.company 
        WHERE 1=1 {exclude_clause}
        ORDER BY company_id
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        return list(cur.fetchall())

def company_score(r: Dict[str, Any]) -> int:
    s = 0
    for k, w in [("name", 3), ("website_url", 2), ("phone_main", 2), ("notes", 2)]:
        v = r.get(k)
        if isinstance(v, str) and v.strip():
            s += w
    return s

def combine_text(a: Optional[str], b: Optional[str]) -> Optional[str]:
    a = normalize_value(a)
    b = normalize_value(b)
    if not a and not b:
        return None
    if a and not b:
        return a
    if b and not a:
        return b
    if a == b:
        return a
    # Check if one contains the other (avoid duplicates)
    a_lower = a.lower().strip() if a else ""
    b_lower = b.lower().strip() if b else ""
    if a_lower and b_lower:
        if a_lower in b_lower:
            return b  # b contains a, return the longer one
        if b_lower in a_lower:
            return a  # a contains b, return the longer one
    return f"{a}\n\n---\n\n{b}"

def propose_company_canonical(rows: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[int]]:
    # choose a base record (best completeness)
    base = max(rows, key=company_score)
    others = [r for r in rows if r["company_id"] != base["company_id"]]
    merged = dict(base)
    # prefer non-empty website/phone; notes combined
    for r in others:
        if not normalize_value(merged.get("website_url")) and normalize_value(r.get("website_url")):
            merged["website_url"] = normalize_value(r.get("website_url"))
        if not normalize_value(merged.get("phone_main")) and normalize_value(r.get("phone_main")):
            merged["phone_main"] = normalize_value(r.get("phone_main"))
        merged["notes"] = combine_text(merged.get("notes"), r.get("notes"))
    return merged, [r["company_id"] for r in rows]

def print_company_group(rows: List[Dict[str, Any]], proposed: Dict[str, Any]):
    ids = [r["company_id"] for r in rows]
    print("\n" + "=" * 86)
    print(f"Company duplicate group: {ids}")
    print("-" * 86)

    fields = ["name", "website_url", "phone_main", "notes"]
    # match if all normalized values equal and non-null
    matches = []
    diffs = []
    trivial_name_diff = False
    
    for f in fields:
        vals = [normalize_value(r.get(f)) for r in rows]
        uniq = {v for v in vals if v is not None}
        if len(uniq) <= 1 and len(uniq) == 1:
            matches.append(f)
        else:
            # Special handling for name field - check if difference is trivial
            if f == "name":
                # Check if all names normalize to the same value
                norm_names = [normalize_company_name(r.get("name")) for r in rows if r.get("name")]
                if len(norm_names) > 1:
                    uniq_norms = {n for n in norm_names if n}
                    if len(uniq_norms) == 1:
                        trivial_name_diff = True
                        matches.append(f)  # Treat as match
                        continue
            diffs.append(f)

    if matches:
        print("Matches: " + ", ".join(matches))
    else:
        print("Matches: (none)")

    if not diffs:
        print("Changes: (none)")
        return trivial_name_diff

    print("\nDifferences / proposed merge:")
    for f in diffs:
        print(f"  - {f}")
        for r in rows:
            print(f"      {r['company_id']}: {fmt(r.get(f))}")
        print(f"    merged: {fmt(proposed.get(f))}")
    
    return trivial_name_diff and len(diffs) == 0

def apply_company_merge(conn, proposed: Dict[str, Any], group_ids: List[int], apply: bool) -> List[int]:
    """
    Canonical company is proposed['company_id'].
    Repoint all FKs from other ids -> canonical.
    Update canonical record with merged fields.
    Optionally archive other company rows if public.deactivated_company or public.deactivated_companies exists.
    
    Returns: list of old company_ids that still have facilities (couldn't be repointed due to constraints)
    """
    canonical_id = proposed["company_id"]
    old_ids = [i for i in group_ids if i != canonical_id]
    if not old_ids:
        return []

    fk_refs = get_fk_references(conn, "public", "company")

    # show dependents summary
    for fk_schema, fk_table, fk_col in fk_refs:
        c = count_dependents(conn, fk_schema, fk_table, fk_col, old_ids)
        if c:
            print(f"    will repoint {c} rows in {fk_schema}.{fk_table}.{fk_col}")

    if not apply:
        print("    DRY RUN: would repoint FKs + update canonical company.")
        return old_ids  # Return all old_ids in dry run

    # repoint dependents
    for fk_schema, fk_table, fk_col in fk_refs:
        updated = repoint_dependents(conn, fk_schema, fk_table, fk_col, old_ids, canonical_id)
        if updated:
            print(f"    repointed {updated} rows in {fk_schema}.{fk_table}.{fk_col}")
    
    # After repoint, check which old company_ids still have facilities (couldn't be repointed)
    remaining_old_ids = []
    check_sql = "SELECT DISTINCT company_id FROM public.facility WHERE company_id = ANY(%s)"
    with conn.cursor() as cur:
        cur.execute(check_sql, (old_ids,))
        remaining = cur.fetchall()
        remaining_old_ids = [r[0] for r in remaining]

    # update canonical company fields
    sql = """
      UPDATE public.company
      SET website_url = %s,
          phone_main  = %s,
          notes       = %s
      WHERE company_id = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (proposed.get("website_url"), proposed.get("phone_main"), proposed.get("notes"), canonical_id))

    # Identify companies with no remaining dependents (can be safely moved to deactivated_company/deactivated_companies)
    companies_to_deactivate = [oid for oid in old_ids if oid not in remaining_old_ids]
    
    # Move companies with no dependents to deactivated_company/deactivated_companies, then delete them
    if companies_to_deactivate:
        deact_table = get_deactivated_companies_table(conn)
        if deact_table:
            deact_cols = table_columns(conn, "public", deact_table)
            company_cols = table_columns(conn, "public", "company")
            # Find common columns between company and deactivated table
            common_cols = [col for col in company_cols if col in deact_cols]
            
            if common_cols:
                # Use INSERT with common columns (simple copy structure)
                cols_str = ", ".join(common_cols)
                select_cols = ", ".join(common_cols)
                with conn.cursor() as cur:
                    # Try to insert, handling conflict if there's a unique constraint
                    try:
                        cur.execute(f"""
                          INSERT INTO public.{deact_table} ({cols_str})
                          SELECT {select_cols}
                          FROM public.company c
                          WHERE c.company_id = ANY(%s)
                        """, (companies_to_deactivate,))
                        moved_count = cur.rowcount
                    except psycopg2.errors.UniqueViolation:
                        # If unique constraint violation, use ON CONFLICT if possible
                        conn.rollback()
                        # Try with ON CONFLICT if we have a primary key or unique column
                        pk_col = "company_id" if "company_id" in deact_cols else ("original_company_id" if "original_company_id" in deact_cols else None)
                        if pk_col:
                            cur.execute(f"""
                              INSERT INTO public.{deact_table} ({cols_str})
                              SELECT {select_cols}
                              FROM public.company c
                              WHERE c.company_id = ANY(%s)
                              ON CONFLICT ({pk_col}) DO NOTHING
                            """, (companies_to_deactivate,))
                            moved_count = cur.rowcount
                        else:
                            moved_count = 0
                    
                    if moved_count > 0:
                        print(f"    📦 Moved {moved_count} company record(s) to {deact_table} (no remaining dependents)")
        
        # Delete companies that have been moved to deactivated_company/deactivated_companies
        delete_sql = "DELETE FROM public.company WHERE company_id = ANY(%s)"
        with conn.cursor() as cur:
            cur.execute(delete_sql, (companies_to_deactivate,))
            deleted_count = cur.rowcount
            if deleted_count > 0:
                print(f"    🗑️  Deleted {deleted_count} old company record(s) from company table")
    
    if remaining_old_ids:
        print(f"    ℹ️  {len(remaining_old_ids)} old company record(s) retained in company table (still have facilities: {remaining_old_ids})")

    conn.commit()
    print(f"    ✅ merged companies into company_id={canonical_id} (repointed {old_ids} -> {canonical_id})")
    return remaining_old_ids

# ----------------------------
# Facility merge (phase B)
# ----------------------------
def fetch_facilities_by_company(conn, company_ids: List[int]) -> List[Dict[str, Any]]:
    """Fetch facilities for specific company IDs"""
    cols = table_columns(conn, "public", "facility")
    
    want = [
        "facility_id",
        "company_id",
        "facility_type_id",
        "name",
        "description",
        "address_line1",
        "address_line2",
        "city",
        "county",
        "state",
        "postal_code",
        "latitude",
        "longitude",
        "geom",
        "status",
        "website_url",
        "phone_main",
        "email_main",
        "notes",
        # optional real-world extras:
        "geom_from_address",
        "imported_source",
        "updated_at",
        "created_at",
    ]
    use = [c for c in want if c in cols]
    sql = "SELECT " + ", ".join(use) + " FROM public.facility WHERE company_id = ANY(%s) ORDER BY facility_id"
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (company_ids,))
        return list(cur.fetchall())

def fetch_facilities(conn) -> List[Dict[str, Any]]:
    # pull all columns we might use; if some don't exist in your DB, select will fail
    # so we build the SELECT dynamically from actual columns present.
    cols = table_columns(conn, "public", "facility")

    want = [
        "facility_id",
        "company_id",
        "facility_type_id",
        "name",
        "description",
        "address_line1",
        "address_line2",
        "city",
        "county",
        "state",
        "postal_code",
        "latitude",
        "longitude",
        "geom",
        "status",
        "website_url",
        "phone_main",
        "email_main",
        "notes",
        # optional real-world extras:
        "geom_from_address",
        "imported_source",
        "updated_at",
        "created_at",
    ]
    use = [c for c in want if c in cols]
    sql = "SELECT " + ", ".join(use) + " FROM public.facility ORDER BY facility_id"
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        return list(cur.fetchall())

def facility_key(row: Dict[str, Any]) -> str:
    company_id = row.get("company_id")
    a1 = clean_street(row.get("address_line1"))
    city = (row.get("city") or "").strip().lower()
    state = (row.get("state") or "").strip().upper()
    postal = (row.get("postal_code") or "").strip()
    # Include company_id so facilities from different companies are never grouped together
    return f"{company_id}|{a1.lower()}|{city}|{state}|{postal}"

def geom_distance_m(conn, id1: int, id2: int) -> Optional[float]:
    sql = """
      SELECT
        CASE
          WHEN f1.geom IS NULL OR f2.geom IS NULL THEN NULL
          ELSE ST_Distance(ST_Transform(f1.geom, 3857), ST_Transform(f2.geom, 3857))
        END AS meters
      FROM public.facility f1
      JOIN public.facility f2 ON f2.facility_id = %s
      WHERE f1.facility_id = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (id2, id1))
        r = cur.fetchone()
        return r[0] if r else None

def build_facility_groups(conn, rows: List[Dict[str, Any]], max_meters: float) -> List[List[Dict[str, Any]]]:
    """
    Group facilities by address (address_line1, city, state, postal_code) AND company_id.
    Only facilities with the same company_id can be grouped together.
    """
    by_key: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        k = facility_key(r)
        # Skip if missing company_id or address info
        if not r.get("company_id") or k.split("|", 1)[1].strip("|") == "":
            continue
        by_key[k].append(r)

    groups: List[List[Dict[str, Any]]] = []
    for k, items in by_key.items():
        if len(items) < 2:
            continue
        
        # Ensure all facilities in this group have the same company_id (should be guaranteed by key, but double-check)
        company_ids = {r.get("company_id") for r in items}
        if len(company_ids) != 1:
            continue  # Skip groups with mixed company_ids (shouldn't happen, but safety check)
        
        items = sorted(items, key=lambda x: x["facility_id"])

        # If we have geoms, split into clusters by distance to cluster anchor.
        # (simple, but avoids obviously-far records with same address text)
        cluster: List[Dict[str, Any]] = []
        anchor = None
        for r in items:
            if not cluster:
                cluster = [r]
                anchor = r
                continue
            d = None
            if anchor and ("geom" in r and "geom" in anchor):
                d = geom_distance_m(conn, anchor["facility_id"], r["facility_id"])
            if d is not None and d > max_meters:
                if len(cluster) >= 2:
                    groups.append(cluster)
                cluster = [r]
                anchor = r
            else:
                cluster.append(r)

        if len(cluster) >= 2:
            groups.append(cluster)

    return groups

def build_facility_groups_by_name(conn, rows: List[Dict[str, Any]], target_company_id: int) -> List[List[Dict[str, Any]]]:
    """
    Group facilities by (company_id, name, city, state) - useful for finding exact duplicates
    that couldn't be repointed due to unique constraint violations.
    Only groups facilities with the same company_id (must match target_company_id).
    """
    by_name_key: Dict[Tuple[int, str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    
    for r in rows:
        company_id = r.get("company_id")
        name = (normalize_value(r.get("name")) or "").strip().lower()
        city = (normalize_value(r.get("city")) or "").strip().lower()
        state = (normalize_value(r.get("state")) or "").strip().upper()
        
        if not company_id or not name or not city or not state:
            continue
        
        # Include company_id in key - only facilities with same company_id can be grouped
        key = (company_id, name, city, state)
        by_name_key[key].append(r)
    
    groups: List[List[Dict[str, Any]]] = []
    for key, items in by_name_key.items():
        if len(items) < 2:
            continue
        
        # Ensure all facilities in this group have the same company_id (should be guaranteed by key, but double-check)
        company_ids = {r.get("company_id") for r in items}
        if len(company_ids) != 1:
            continue  # Skip groups with mixed company_ids (shouldn't happen, but safety check)
        
        # Sort by facility_id for consistency
        items = sorted(items, key=lambda x: x["facility_id"])
        groups.append(items)
    
    return groups

def build_facility_groups_by_unique_key(conn, rows: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """
    Group facilities by (company_id, name, city, state) - finds exact duplicates
    that would violate the unique constraint facility_company_name_city_state_uniq.
    """
    by_key: Dict[Tuple[int, str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    
    for r in rows:
        company_id = r.get("company_id")
        name = (normalize_value(r.get("name")) or "").strip()
        city = (normalize_value(r.get("city")) or "").strip()
        state = (normalize_value(r.get("state")) or "").strip().upper()
        
        if not company_id or not name or not city or not state:
            continue
        
        key = (company_id, name.lower(), city.lower(), state)
        by_key[key].append(r)
    
    groups: List[List[Dict[str, Any]]] = []
    for key, items in by_key.items():
        if len(items) >= 2:
            # Sort by facility_id for consistency
            items = sorted(items, key=lambda x: x["facility_id"])
            groups.append(items)
    
    return groups

def is_kgfaish(text: Optional[str]) -> bool:
    t = (text or "").lower()
    return "ksgrainandfeed" in t or "kgfa" in t

def score_text(v: Optional[str]) -> int:
    v = normalize_value(v)
    return len(v) if isinstance(v, str) else 0

def pick_best_name(names: List[Optional[str]]) -> Optional[str]:
    # Prefer the longest non-empty (usually the most specific)
    cleaned = [normalize_value(n) for n in names if normalize_value(n)]
    if not cleaned:
        return None
    return max(cleaned, key=lambda s: len(s))

def propose_facility_merge(conn, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Create a merged facility proposal from a group (2+).
    Heuristics:
      - name: longest
      - description/notes/imported_source: combine unique chunks, prefer longer
      - website/phone/email: first non-empty; if any looks KGFA-ish, prefer that for imported_source (not website)
      - geom_from_address (if exists): OR
      - company_id/facility_type_id: prefer the one used by the "best" record (more populated)
      - lat/lon: prefer any non-null; if multiple, keep from record that has geom_from_address true (if exists) else first
      - status: ACTIVE
    """
    cols = set(rows[0].keys())
    merged: Dict[str, Any] = {}

    # choose a "base" record by completeness
    def rec_score(r: Dict[str, Any]) -> int:
        s = 0
        for f, w in [
            ("description", 5), ("notes", 4),
            ("website_url", 2), ("phone_main", 2), ("email_main", 2),
            ("address_line1", 3), ("city", 2), ("state", 2), ("postal_code", 2),
            ("latitude", 2), ("longitude", 2), ("geom", 3),
        ]:
            if f in r and normalize_value(r.get(f)) is not None:
                s += w
        if str(r.get("status", "")).upper() == "ACTIVE":
            s += 2
        if "geom_from_address" in r and r.get("geom_from_address"):
            s += 1
        return s

    base = max(rows, key=rec_score)

    # merge core IDs
    for f in ["company_id", "facility_type_id"]:
        if f in cols:
            merged[f] = base.get(f)

    # name
    if "name" in cols:
        merged["name"] = pick_best_name([r.get("name") for r in rows]) or base.get("name")

    # address-ish
    for f in ["address_line1", "address_line2", "city", "county", "state", "postal_code"]:
        if f in cols:
            # prefer base, else first non-empty, but normalize CR in address_line1
            val = normalize_value(base.get(f))
            if val is None:
                for r in rows:
                    v = normalize_value(r.get(f))
                    if v is not None:
                        val = v
                        break
            if f == "address_line1" and val:
                val = clean_street(val)  # returns normalized (lowered); keep nicer casing:
                val = " ".join([w.capitalize() if w.lower() not in ("ks",) else w.upper() for w in val.split()])
                val = val.replace("County road", "County Road")
            merged[f] = val

    # status always ACTIVE on new
    if "status" in cols:
        merged["status"] = "ACTIVE"

    # contact-ish singletons
    for f in ["website_url", "phone_main", "email_main"]:
        if f in cols:
            v = normalize_value(base.get(f))
            if v is None:
                for r in rows:
                    rv = normalize_value(r.get(f))
                    if rv is not None:
                        v = rv
                        break
            merged[f] = v

    # text combine
    for f in ["description", "notes", "imported_source"]:
        if f in cols:
            # prefer longer, but combine distinct
            acc = None
            for r in sorted(rows, key=lambda x: score_text(x.get(f)), reverse=True):
                acc = combine_text(acc, r.get(f))
            merged[f] = acc

    # geom flags
    if "geom_from_address" in cols:
        merged["geom_from_address"] = any(bool(r.get("geom_from_address")) for r in rows)

    # lat/lon
    for f in ["latitude", "longitude"]:
        if f in cols:
            v = base.get(f)
            if v is None:
                # prefer record with geom_from_address if available
                preferred = None
                if "geom_from_address" in cols:
                    for r in rows:
                        if r.get("geom_from_address") and r.get(f) is not None:
                            preferred = r.get(f)
                            break
                if preferred is not None:
                    v = preferred
                else:
                    for r in rows:
                        if r.get(f) is not None:
                            v = r.get(f)
                            break
            merged[f] = v

    return merged

def print_facility_group(group_idx: int, total: int, rows: List[Dict[str, Any]], proposed: Dict[str, Any]):
    ids = [r["facility_id"] for r in rows]
    print("\n" + "=" * 86)
    print(f"Facility group {group_idx}/{total}: {ids}")
    print("-" * 86)

    # fields to display
    fields = [
        "company_id", "facility_type_id",
        "name",
        "address_line1", "address_line2", "city", "county", "state", "postal_code",
        "website_url", "phone_main", "email_main",
        "description", "notes", "imported_source",
        "latitude", "longitude",
        "status",
        "geom_from_address",
    ]
    fields = [f for f in fields if f in proposed]  # only those present

    matches = []
    diffs: List[str] = []
    trivial_name_diff = False
    
    for f in fields:
        vals = [normalize_value(r.get(f)) for r in rows]
        uniq = {v for v in vals if v is not None}
        if len(uniq) == 1 and len(uniq) != 0:
            matches.append(f)
        else:
            # Special handling for name field - check if difference is trivial
            if f == "name":
                # Check if all names normalize to the same value
                norm_names = [normalize_company_name(r.get("name")) for r in rows if r.get("name")]
                if len(norm_names) > 1:
                    uniq_norms = {n for n in norm_names if n}
                    if len(uniq_norms) == 1:
                        trivial_name_diff = True
                        matches.append(f)  # Treat as match
                        continue
            # only show if the merged value differs from at least one source OR combines
            mv = normalize_value(proposed.get(f))
            if any(mv != normalize_value(r.get(f)) for r in rows):
                diffs.append(f)

    if matches:
        print("Matches: " + ", ".join(matches))
    else:
        print("Matches: (none)")

    if not diffs:
        print("Changes: (none)")
        return trivial_name_diff

    print("\nFields to change / combine:")
    for f in diffs:
        print(f"  - {f}")
        for r in rows:
            print(f"      {r['facility_id']}: {fmt(r.get(f))}")
        print(f"    merged: {fmt(proposed.get(f))}")
    
    # Auto-accept if only trivial name difference and no other significant differences
    return trivial_name_diff and len(diffs) == 0

def insert_new_facility(conn, proposed: Dict[str, Any], exclude_ids: Optional[List[int]] = None) -> int:
    """
    Insert a new facility, or return existing facility_id if one with same (company_id, name, city, state) exists.
    exclude_ids: list of facility_ids to exclude from the check (e.g., the ones being merged)
    
    IMPORTANT: If one of the facilities being merged (in exclude_ids) already matches the proposed
    unique key, we should use that facility as the target instead of creating a new one.
    """
    cols_present = table_columns(conn, "public", "facility")
    # facility_id is serial
    insertable = [k for k in proposed.keys() if k in cols_present and k != "facility_id"]

    # ensure required cols exist and have values if your DB enforces NOT NULL
    # (schema doc says name/lat/lon are NOT NULL)
    if "name" in cols_present and not normalize_value(proposed.get("name")):
        raise ValueError("Cannot insert new facility: missing name")
    if "latitude" in cols_present and proposed.get("latitude") is None:
        raise ValueError("Cannot insert new facility: missing latitude")
    if "longitude" in cols_present and proposed.get("longitude") is None:
        raise ValueError("Cannot insert new facility: missing longitude")

    # First, check if one of the facilities being merged already matches the proposed unique key
    # This handles the case where facility 400 has (company_id=454, name='Tribune', ...) 
    # and we're trying to merge 400 and 407 into the same key - we should use 400 as target
    if exclude_ids:
        check_existing_in_group_sql = """
            SELECT facility_id 
            FROM public.facility 
            WHERE facility_id = ANY(%s)
            AND company_id = %s 
            AND name = %s 
            AND COALESCE(city, '') = COALESCE(%s, '')
            AND COALESCE(state, '') = COALESCE(%s, '')
            LIMIT 1
        """
        with conn.cursor() as cur:
            cur.execute(check_existing_in_group_sql, (
                exclude_ids,
                proposed.get("company_id"),
                proposed.get("name"),
                proposed.get("city"),
                proposed.get("state")
            ))
            existing_in_group = cur.fetchone()
            if existing_in_group:
                existing_id = existing_in_group[0]
                print(f"    ℹ️  One of the facilities being merged already matches the unique key: facility_id={existing_id}")
                print(f"       Will use this facility as the merge target instead of creating new one")
                return existing_id

    # Check if facility with same (company_id, name, city, state) already exists elsewhere
    # (excluding the ones we're merging)
    exclude_clause = ""
    params = [
        proposed.get("company_id"),
        proposed.get("name"),
        proposed.get("city"),
        proposed.get("state")
    ]
    if exclude_ids:
        exclude_clause = "AND facility_id != ALL(%s)"
        params.append(exclude_ids)
    
    check_sql = f"""
        SELECT facility_id 
        FROM public.facility 
        WHERE company_id = %s 
        AND name = %s 
        AND COALESCE(city, '') = COALESCE(%s, '')
        AND COALESCE(state, '') = COALESCE(%s, '')
        {exclude_clause}
        LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(check_sql, tuple(params))
        existing = cur.fetchone()
        
        if existing:
            existing_id = existing[0]
            print(f"    ℹ️  Facility with same (company_id, name, city, state) already exists: facility_id={existing_id}")
            print(f"       Will merge into existing facility instead of creating new one")
            return existing_id

    # No existing facility, create new one
    cols_sql = ", ".join(insertable)
    ph = ", ".join(["%s"] * len(insertable))
    vals = [proposed.get(k) for k in insertable]

    sql = f"INSERT INTO public.facility ({cols_sql}) VALUES ({ph}) RETURNING facility_id"
    with conn.cursor() as cur:
        try:
            cur.execute(sql, vals)
            return int(cur.fetchone()[0])
        except psycopg2.errors.UniqueViolation as e:
            # If we still hit the constraint (race condition), rollback and try to find existing
            if "facility_company_name_city_state_uniq" in str(e):
                conn.rollback()
                # Re-execute the check query after rollback with a fresh cursor
                with conn.cursor() as check_cur:
                    check_cur.execute(check_sql, tuple(params))
                    existing = check_cur.fetchone()
                    if existing:
                        print(f"    ℹ️  Facility with same (company_id, name, city, state) already exists: facility_id={existing[0]}")
                        return existing[0]
            raise

def archive_facility(conn, old_id: int, new_id: int, reason_detail: str):
    sql = """
      INSERT INTO public.deactivated_facilities
        (original_facility_id, reason, merged_to_facility_id, reason_detail, facility_snapshot)
      SELECT
        f.facility_id, 'MERGED', %s, %s, to_jsonb(f)
      FROM public.facility f
      WHERE f.facility_id = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (new_id, reason_detail, old_id))

def deactivate_facility(conn, old_id: int):
    # schema says facility.status exists with ACTIVE/INACTIVE
    with conn.cursor() as cur:
        cur.execute("UPDATE public.facility SET status = 'INACTIVE' WHERE facility_id = %s", (old_id,))

def apply_facility_merge(conn, rows: List[Dict[str, Any]], proposed: Dict[str, Any], apply: bool):
    old_ids = [r["facility_id"] for r in rows]

    # Discover all tables that FK -> facility (facility_contact, facility_service, facility_product, facility_transport_mode, etc.)
    fk_refs = get_fk_references(conn, "public", "facility")

    # show dependent counts
    for fk_schema, fk_table, fk_col in fk_refs:
        c = count_dependents(conn, fk_schema, fk_table, fk_col, old_ids)
        if c:
            print(f"    will repoint {c} rows in {fk_schema}.{fk_table}.{fk_col}")

    if not apply:
        print("    DRY RUN: would insert new facility + repoint FKs + archive + deactivate.")
        return

    reason_detail = f"Merged facilities into canonical record. Originals: {old_ids}"

    # transaction
    try:
        # Check if we're creating a new facility or using an existing one
        # Pass old_ids to exclude them from the conflict check
        new_id = insert_new_facility(conn, proposed, exclude_ids=old_ids)
        is_new = new_id not in old_ids
        
        # If using existing facility, update it with merged data (except the unique constraint fields)
        if not is_new:
            # Update the existing facility with merged data
            cols_present = table_columns(conn, "public", "facility")
            updateable = [k for k in proposed.keys() 
                         if k in cols_present 
                         and k not in ("facility_id", "company_id", "name", "city", "state")]  # Don't update unique constraint fields
            
            if updateable:
                set_clauses = [f"{k} = %s" for k in updateable]
                vals = [proposed.get(k) for k in updateable] + [new_id]
                update_sql = f"UPDATE public.facility SET {', '.join(set_clauses)} WHERE facility_id = %s"
                with conn.cursor() as cur:
                    cur.execute(update_sql, vals)
                    print(f"    updated existing facility_id={new_id} with merged data")

        # repoint children first (safer if any FKs are non-nullable)
        for fk_schema, fk_table, fk_col in fk_refs:
            updated = repoint_dependents(conn, fk_schema, fk_table, fk_col, old_ids, new_id)
            if updated:
                print(f"    repointed {updated} rows in {fk_schema}.{fk_table}.{fk_col}")

        # archive and deactivate originals (but not if one of them is the target)
        for oid in old_ids:
            if oid != new_id:  # Don't archive/deactivate the target facility
                if table_exists(conn, "public", "deactivated_facilities"):
                    archive_facility(conn, oid, new_id, reason_detail)
                deactivate_facility(conn, oid)

        conn.commit()
        if is_new:
            print(f"    ✅ merged into new facility_id={new_id}; archived+deactivated {old_ids}")
        else:
            print(f"    ✅ merged into existing facility_id={new_id}; archived+deactivated {[oid for oid in old_ids if oid != new_id]}")
    except Exception as e:
        conn.rollback()
        # Ensure connection is ready for next transaction by resetting state
        if not conn.closed:
            try:
                # Create a new cursor to reset the connection state
                with conn.cursor() as reset_cur:
                    reset_cur.execute("SELECT 1")
            except:
                # If that fails, connection is likely broken - caller should handle
                pass
        raise

# ----------------------------
# Main runner with progress
# ----------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Apply changes (otherwise dry run)")
    ap.add_argument("--max-meters", type=float, default=250.0, help="Max distance to keep in same facility group")
    ap.add_argument("--limit-companies", type=int, default=0, help="Limit company groups reviewed (0=all)")
    ap.add_argument("--limit-facilities", type=int, default=0, help="Limit facility groups reviewed (0=all)")
    args = ap.parse_args()

    conn = db_connect()
    conn.autocommit = False

    try:
        # -------------------------
        # Phase A: companies first
        # -------------------------
        companies = fetch_companies(conn)
        comp_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for c in companies:
            k = normalize_company_name(c.get("name"))
            if not k:
                continue
            comp_groups[k].append(c)

        company_dupe_groups = [g for g in comp_groups.values() if len(g) >= 2]
        company_dupe_groups.sort(key=lambda g: (len(g), g[0]["company_id"]), reverse=True)

        if args.limit_companies and args.limit_companies > 0:
            company_dupe_groups = company_dupe_groups[: args.limit_companies]

        print(f"\nProcessing {len(company_dupe_groups)} company groups (one at a time with facilities).")
        for i, g in enumerate(company_dupe_groups, start=1):
            proposed, ids = propose_company_canonical(g)
            print(f"\n{'='*86}")
            print(f"[Company group {i}/{len(company_dupe_groups)}]")
            print(f"{'='*86}")
            auto_accept = print_company_group(g, proposed)

            if auto_accept:
                print("    ✓ Auto-accepting: names differ only by punctuation/suffixes, no other differences")
                do_it = True
            else:
                do_it = ask_yes_no("Merge companies (repoint all FKs to canonical company)? (y/n): ")
            
            if not do_it:
                print("    skipped.")
                continue

            # Merge the company (this commits internally if --apply)
            # Returns list of old company_ids that still have facilities (couldn't be repointed)
            remaining_old_ids = apply_company_merge(conn, proposed, ids, apply=args.apply)
            
            # Now process facilities for this company
            # Include canonical company_id and any old company_ids that still have facilities
            canonical_id = proposed["company_id"]
            all_company_ids = [canonical_id]
            if remaining_old_ids:
                all_company_ids.extend(remaining_old_ids)
                print(f"\n    Note: Some facilities still have old company_ids {remaining_old_ids} (couldn't be repointed)")
            
            print(f"\n    Processing facilities for company_id={canonical_id} (including facilities with old company_ids: {remaining_old_ids})")
            facilities = fetch_facilities_by_company(conn, all_company_ids)
            
            if not facilities:
                print(f"    No facilities found for this company.")
                continue
            
            print(f"    Found {len(facilities)} total facilities for this company.")
            
            # Build facility groups from these facilities
            groups = build_facility_groups(conn, facilities, max_meters=args.max_meters)
            
            # Also check for duplicates by (name, city, state) - handles cases where facilities
            # couldn't be repointed due to unique constraint violations
            if remaining_old_ids:
                name_based_groups = build_facility_groups_by_name(conn, facilities, canonical_id)
                # Merge groups - if a facility is in both, prefer the address-based group
                for name_group in name_based_groups:
                    # Check if any facility in name_group is already in an address-based group
                    name_group_ids = {r["facility_id"] for r in name_group}
                    found_in_existing = False
                    for addr_group in groups:
                        addr_group_ids = {r["facility_id"] for r in addr_group}
                        if name_group_ids & addr_group_ids:  # Intersection
                            found_in_existing = True
                            break
                    if not found_in_existing and len(name_group) >= 2:
                        groups.append(name_group)
            
            if not groups:
                print(f"    No duplicate facility groups found for this company.")
                continue
            
            print(f"    Found {len(groups)} duplicate facility groups for this company.")
            
            # Process each facility group
            for j, facility_group in enumerate(groups, start=1):
                proposed_fac = propose_facility_merge(conn, facility_group)
                auto_accept_fac = print_facility_group(j, len(groups), facility_group, proposed_fac)

                if auto_accept_fac:
                    print("    ✓ Auto-accepting: names differ only by punctuation/suffixes, no other differences")
                    do_fac = True
                else:
                    do_fac = ask_yes_no("    Merge facilities into NEW record + archive originals? (y/n): ")
                
                if not do_fac:
                    print("    skipped.")
                    continue

                try:
                    # apply_facility_merge commits internally if --apply
                    apply_facility_merge(conn, facility_group, proposed_fac, apply=args.apply)
                except Exception as e:
                    print(f"    ❌ merge failed for group { [r['facility_id'] for r in facility_group] }: {e}")
                    # Ensure transaction is rolled back and connection is ready
                    try:
                        if not conn.closed:
                            conn.rollback()
                            # Reset connection state
                            with conn.cursor() as reset_cur:
                                reset_cur.execute("SELECT 1")
                    except Exception as reset_error:
                        print(f"    ⚠️  Warning: Could not reset connection state: {reset_error}")
                    continue
            
            print(f"\n    ✅ Completed processing company_id={canonical_id} and its facilities")

        # -------------------------
        # Phase B: facility duplicates (independent of companies)
        # -------------------------
        print(f"\n{'='*86}")
        print(f"[Phase B: Processing facility duplicates independently]")
        print(f"{'='*86}")
        
        # Fetch all active facilities (exclude those already deactivated/merged)
        all_facilities = fetch_facilities(conn)
        # Filter to only active facilities (if status column exists)
        cols = table_columns(conn, "public", "facility")
        if "status" in cols:
            all_facilities = [f for f in all_facilities if f.get("status") != "INACTIVE"]
        
        if not all_facilities:
            print("No active facilities found to process.")
        else:
            print(f"Found {len(all_facilities)} active facilities to check for duplicates.")
            
            # Build facility groups by address (geographic proximity)
            address_groups = build_facility_groups(conn, all_facilities, max_meters=args.max_meters)
            
            # Also check for exact duplicates by (company_id, name, city, state)
            unique_key_groups = build_facility_groups_by_unique_key(conn, all_facilities)
            
            # Merge groups - if a facility is in both, prefer the address-based group
            all_facility_groups = list(address_groups)
            for unique_group in unique_key_groups:
                unique_group_ids = {r["facility_id"] for r in unique_group}
                found_in_existing = False
                for addr_group in all_facility_groups:
                    addr_group_ids = {r["facility_id"] for r in addr_group}
                    if unique_group_ids & addr_group_ids:  # Intersection
                        found_in_existing = True
                        break
                if not found_in_existing:
                    all_facility_groups.append(unique_group)
            
            # Remove duplicates from groups (if a facility appears in multiple groups, keep it in the first one)
            seen_facility_ids = set()
            deduplicated_groups = []
            for group in all_facility_groups:
                group_ids = {r["facility_id"] for r in group}
                if not (group_ids & seen_facility_ids):  # No overlap with already processed facilities
                    deduplicated_groups.append(group)
                    seen_facility_ids.update(group_ids)
            
            if args.limit_facilities and args.limit_facilities > 0:
                deduplicated_groups = deduplicated_groups[: args.limit_facilities]
            
            print(f"\nProcessing {len(deduplicated_groups)} facility duplicate groups.")
            
            for i, facility_group in enumerate(deduplicated_groups, start=1):
                proposed_fac = propose_facility_merge(conn, facility_group)
                auto_accept_fac = print_facility_group(i, len(deduplicated_groups), facility_group, proposed_fac)

                if auto_accept_fac:
                    print("    ✓ Auto-accepting: names differ only by punctuation/suffixes, no other differences")
                    do_fac = True
                else:
                    do_fac = ask_yes_no("    Merge facilities into NEW record + archive originals? (y/n): ")
                
                if not do_fac:
                    print("    skipped.")
                    continue

                try:
                    # apply_facility_merge commits internally if --apply
                    apply_facility_merge(conn, facility_group, proposed_fac, apply=args.apply)
                except Exception as e:
                    print(f"    ❌ merge failed for group { [r['facility_id'] for r in facility_group] }: {e}")
                    # Ensure transaction is rolled back and connection is ready
                    try:
                        if not conn.closed:
                            conn.rollback()
                            # Reset connection state
                            with conn.cursor() as reset_cur:
                                reset_cur.execute("SELECT 1")
                    except Exception as reset_error:
                        print(f"    ⚠️  Warning: Could not reset connection state: {reset_error}")
                    continue

        print("\nAll done.")
        if not args.apply:
            print("Ran in DRY RUN mode (no DB writes). Re-run with --apply to execute.")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
