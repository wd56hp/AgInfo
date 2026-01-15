#!/usr/bin/env python3
"""
Merge duplicate companies only.

Process:
1. Find duplicate companies (by normalized name)
2. For each duplicate group:
   - Create a NEW company record with merged data
   - Repoint all foreign keys from old companies to new company
   - Move old companies to deactivated_companies table

Requires:
  pip install psycopg2-binary python-dotenv

.env expects:
  POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGIS_HOST_PORT
Optional:
  PGHOST (default localhost)

Safety:
  Default is DRY RUN unless you pass --apply
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
# Company name normalization
# ----------------------------
COMPANY_SUFFIXES = [
    "inc", "inc.", "incorporated",
    "corp", "corp.", "corporation",
    "llc", "l.l.c", "l.l.c.", "ltd", "ltd.",
    "co", "co.", "company",
]

def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def normalize_value(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, str):
        t = norm_ws(v)
        return t if t else None
    return v

def normalize_company_name(name: Optional[str]) -> str:
    """Normalize company name by removing suffixes and punctuation"""
    if not name:
        return ""
    n = norm_ws(name).lower()
    n = re.sub(r"[^\w\s&-]", "", n)  # drop punctuation except word/space/&/-
    parts = [p for p in n.split() if p not in COMPANY_SUFFIXES]
    return " ".join(parts)

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
    """Repoint foreign keys from old_ids to new_id"""
    sql = f"UPDATE {fk_schema}.{fk_table} SET {fk_col} = %s WHERE {fk_col} = ANY(%s)"
    with conn.cursor() as cur:
        cur.execute(sql, (new_id, old_ids))
        return cur.rowcount

# ----------------------------
# Company operations
# ----------------------------
def fetch_companies(conn) -> List[Dict[str, Any]]:
    sql = "SELECT company_id, name, website_url, phone_main, notes FROM public.company ORDER BY company_id"
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        return list(cur.fetchall())

def company_score(r: Dict[str, Any]) -> int:
    """Score company by data completeness"""
    s = 0
    for k, w in [("name", 3), ("website_url", 2), ("phone_main", 2), ("notes", 2)]:
        v = r.get(k)
        if isinstance(v, str) and v.strip():
            s += w
    return s

def combine_text(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Combine two text fields, avoiding duplicates"""
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
    # Check if one contains the other
    a_lower = a.lower().strip() if a else ""
    b_lower = b.lower().strip() if b else ""
    if a_lower and b_lower:
        if a_lower in b_lower:
            return b
        if b_lower in a_lower:
            return a
    return f"{a}\n\n---\n\n{b}"

def create_merged_company(conn, rows: List[Dict[str, Any]]) -> int:
    """
    Create a NEW company record with merged data from duplicate companies.
    Returns the new company_id.
    """
    # Choose base record with best completeness
    base = max(rows, key=company_score)
    
    # Build merged record
    merged = {
        "name": base.get("name"),  # Use base name
        "website_url": normalize_value(base.get("website_url")),
        "phone_main": normalize_value(base.get("phone_main")),
        "notes": base.get("notes"),
    }
    
    # Merge data from all other records
    for r in rows:
        if r["company_id"] == base["company_id"]:
            continue
        # Prefer non-empty values
        if not merged["website_url"] and normalize_value(r.get("website_url")):
            merged["website_url"] = normalize_value(r.get("website_url"))
        if not merged["phone_main"] and normalize_value(r.get("phone_main")):
            merged["phone_main"] = normalize_value(r.get("phone_main"))
        # Combine notes
        merged["notes"] = combine_text(merged.get("notes"), r.get("notes"))
    
    # Insert new company
    sql = """
        INSERT INTO public.company (name, website_url, phone_main, notes)
        VALUES (%s, %s, %s, %s)
        RETURNING company_id
    """
    with conn.cursor() as cur:
        cur.execute(sql, (
            merged["name"],
            merged["website_url"],
            merged["phone_main"],
            merged["notes"]
        ))
        return int(cur.fetchone()[0])

def create_deactivated_companies_table(conn):
    """Create deactivated_companies table if it doesn't exist"""
    sql = """
        CREATE TABLE IF NOT EXISTS public.deactivated_companies (
            original_company_id INT PRIMARY KEY,
            reason VARCHAR(100),
            merged_to_company_id INT REFERENCES public.company(company_id),
            reason_detail TEXT,
            company_snapshot JSONB,
            deactivated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    with conn.cursor() as cur:
        cur.execute(sql)

def move_to_deactivated(conn, old_company_ids: List[int], new_company_id: int, reason_detail: str):
    """Move old companies to deactivated_companies table"""
    sql = """
        INSERT INTO public.deactivated_companies
            (original_company_id, reason, merged_to_company_id, reason_detail, company_snapshot)
        SELECT
            company_id, 'MERGED', %s, %s, to_jsonb(c.*)
        FROM public.company c
        WHERE c.company_id = ANY(%s)
        ON CONFLICT (original_company_id) DO NOTHING
    """
    with conn.cursor() as cur:
        cur.execute(sql, (new_company_id, reason_detail, old_company_ids))

def delete_old_companies(conn, old_company_ids: List[int]):
    """Delete old company records (after FKs have been repointed)"""
    sql = "DELETE FROM public.company WHERE company_id = ANY(%s)"
    with conn.cursor() as cur:
        cur.execute(sql, (old_company_ids,))
        return cur.rowcount

# ----------------------------
# Display and interaction
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

def print_company_group(group_num: int, total: int, rows: List[Dict[str, Any]], canonical_id: int, merged: Dict[str, Any]):
    """Display company group and proposed merge"""
    ids = [r["company_id"] for r in rows]
    print("\n" + "=" * 86)
    print(f"Company group {group_num}/{total}: {ids}")
    print("-" * 86)
    
    print("\nExisting companies:")
    for r in rows:
        marker = " (canonical)" if r["company_id"] == canonical_id else ""
        print(f"  company_id={r['company_id']}: {fmt(r.get('name'))}{marker}")
        print(f"    website: {fmt(r.get('website_url'))}")
        print(f"    phone: {fmt(r.get('phone_main'))}")
        print(f"    notes: {fmt(r.get('notes'))}")
    
    print(f"\nCanonical company (company_id={canonical_id}) will be updated with merged data:")
    print(f"  website: {fmt(merged.get('website_url'))}")
    print(f"  phone: {fmt(merged.get('phone_main'))}")
    print(f"  notes: {fmt(merged.get('notes'))}")

def ask_yes_no(prompt: str) -> bool:
    while True:
        ans = input(prompt).strip().lower()
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("Please enter y/n.")

# ----------------------------
# Main merge logic
# ----------------------------
def merge_company_group(conn, rows: List[Dict[str, Any]], apply: bool) -> bool:
    """
    Merge a group of duplicate companies:
    1. Select canonical company (best completeness)
    2. Update canonical company with merged data
    3. Repoint all FKs from other companies to canonical
    4. Move old companies to deactivated_companies
    5. Delete old companies
    
    Returns True if merged, False if skipped
    """
    # Select canonical company (best completeness)
    canonical = max(rows, key=company_score)
    canonical_id = canonical["company_id"]
    old_ids = [r["company_id"] for r in rows if r["company_id"] != canonical_id]
    
    # Build merged company data
    merged = {
        "website_url": normalize_value(canonical.get("website_url")),
        "phone_main": normalize_value(canonical.get("phone_main")),
        "notes": canonical.get("notes"),
    }
    # Merge data from other companies
    for r in rows:
        if r["company_id"] == canonical_id:
            continue
        if not merged["website_url"] and normalize_value(r.get("website_url")):
            merged["website_url"] = normalize_value(r.get("website_url"))
        if not merged["phone_main"] and normalize_value(r.get("phone_main")):
            merged["phone_main"] = normalize_value(r.get("phone_main"))
        merged["notes"] = combine_text(merged.get("notes"), r.get("notes"))
    
    if not apply:
        print(f"    DRY RUN: would use company_id={canonical_id} as canonical and repoint FKs")
        return False
    
    try:
        # Step 1: Update canonical company with merged data
        print(f"    Using company_id={canonical_id} as canonical company")
        sql = """
            UPDATE public.company
            SET website_url = %s,
                phone_main  = %s,
                notes       = %s
            WHERE company_id = %s
        """
        with conn.cursor() as cur:
            cur.execute(sql, (merged.get("website_url"), merged.get("phone_main"), merged.get("notes"), canonical_id))
        
        # Step 2: Repoint all foreign keys
        fk_refs = get_fk_references(conn, "public", "company")
        for fk_schema, fk_table, fk_col in fk_refs:
            # Special handling for facility table with unique constraint
            if fk_table == "facility" and fk_col == "company_id":
                # Check for conflicts
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
                    cur.execute(conflict_sql, (old_ids, canonical_id))
                    conflicts = cur.fetchall()
                    if conflicts:
                        conflict_ids = [c[0] for c in conflicts]
                        print(f"    ⚠️  Warning: {len(conflicts)} facilities would violate unique constraint (duplicate facilities), deleting:")
                        for c in conflicts:
                            print(f"        facility_id={c[0]}: '{c[1]}', {c[2]}, {c[3]}")
                        # Delete conflicting facilities (they're duplicates of facilities already on canonical company)
                        delete_sql = "DELETE FROM public.facility WHERE facility_id = ANY(%s)"
                        cur.execute(delete_sql, (conflict_ids,))
                        deleted_count = cur.rowcount
                        if deleted_count > 0:
                            print(f"    🗑️  Deleted {deleted_count} duplicate facility record(s)")
                        # Update non-conflicting facilities
                        exclude_sql = """
                            UPDATE public.facility 
                            SET company_id = %s 
                            WHERE company_id = ANY(%s) 
                            AND facility_id != ALL(%s)
                        """
                        cur.execute(exclude_sql, (canonical_id, old_ids, conflict_ids))
                        updated = cur.rowcount
                        if updated:
                            print(f"    ✓ Repointed {updated} facilities to canonical company")
                    else:
                        updated = repoint_dependents(conn, fk_schema, fk_table, fk_col, old_ids, canonical_id)
                        if updated:
                            print(f"    ✓ Repointed {updated} rows in {fk_schema}.{fk_table}.{fk_col}")
            else:
                updated = repoint_dependents(conn, fk_schema, fk_table, fk_col, old_ids, canonical_id)
                if updated:
                    print(f"    ✓ Repointed {updated} rows in {fk_schema}.{fk_table}.{fk_col}")
        
        # After repoint, check which old company_ids still have facilities (couldn't be repointed)
        remaining_old_ids = []
        check_sql = "SELECT DISTINCT company_id FROM public.facility WHERE company_id = ANY(%s)"
        with conn.cursor() as cur:
            cur.execute(check_sql, (old_ids,))
            remaining = cur.fetchall()
            remaining_old_ids = [r[0] for r in remaining]
        
        # Step 3: Move old companies with no remaining facilities to deactivated_companies, then delete them
        companies_to_deactivate = [oid for oid in old_ids if oid not in remaining_old_ids]
        if companies_to_deactivate:
            print(f"    Moving {len(companies_to_deactivate)} old companies to deactivated_companies...")
            create_deactivated_companies_table(conn)
            reason_detail = f"Merged companies {companies_to_deactivate} into canonical company_id={canonical_id}"
            move_to_deactivated(conn, companies_to_deactivate, canonical_id, reason_detail)
            print(f"    ✓ Moved {len(companies_to_deactivate)} companies to deactivated_companies")
            
            # Step 4: Delete old companies that have been moved to deactivated_companies
            print(f"    Deleting old company records (no remaining facilities)...")
            deleted = delete_old_companies(conn, companies_to_deactivate)
            print(f"    ✓ Deleted {deleted} old company records")
        
        if remaining_old_ids:
            print(f"    ℹ️  {len(remaining_old_ids)} old company record(s) retained (still have facilities: {remaining_old_ids})")
        
        conn.commit()
        print(f"    ✅ Successfully merged into company_id={canonical_id}")
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"    ❌ Error: {e}")
        raise

# ----------------------------
# Main
# ----------------------------
def main():
    ap = argparse.ArgumentParser(description="Merge duplicate companies only")
    ap.add_argument("--apply", action="store_true", help="Apply changes (otherwise dry run)")
    ap.add_argument("--limit", type=int, default=0, help="Limit number of groups to process (0=all)")
    args = ap.parse_args()

    conn = db_connect()
    conn.autocommit = False

    try:
        # Find duplicate companies
        companies = fetch_companies(conn)
        comp_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for c in companies:
            k = normalize_company_name(c.get("name"))
            if not k:
                continue
            comp_groups[k].append(c)

        company_dupe_groups = [g for g in comp_groups.values() if len(g) >= 2]
        company_dupe_groups.sort(key=lambda g: (len(g), g[0]["company_id"]), reverse=True)

        if args.limit and args.limit > 0:
            company_dupe_groups = company_dupe_groups[: args.limit]

        print(f"\nFound {len(company_dupe_groups)} duplicate company groups")
        print(f"Mode: {'APPLY' if args.apply else 'DRY RUN'}\n")

        for i, group in enumerate(company_dupe_groups, start=1):
            # Select canonical company (best completeness)
            canonical = max(group, key=company_score)
            canonical_id = canonical["company_id"]
            old_ids = [r["company_id"] for r in group if r["company_id"] != canonical_id]
            
            # Build merged company data for display
            merged_display = {
                "website_url": normalize_value(canonical.get("website_url")),
                "phone_main": normalize_value(canonical.get("phone_main")),
                "notes": canonical.get("notes"),
            }
            for r in group:
                if r["company_id"] == canonical_id:
                    continue
                if not merged_display["website_url"] and normalize_value(r.get("website_url")):
                    merged_display["website_url"] = normalize_value(r.get("website_url"))
                if not merged_display["phone_main"] and normalize_value(r.get("phone_main")):
                    merged_display["phone_main"] = normalize_value(r.get("phone_main"))
                merged_display["notes"] = combine_text(merged_display.get("notes"), r.get("notes"))

            print_company_group(i, len(company_dupe_groups), group, canonical_id, merged_display)

            # Show what will be repointed
            fk_refs = get_fk_references(conn, "public", "company")
            print("\nDependents that will be repointed:")
            for fk_schema, fk_table, fk_col in fk_refs:
                c = count_dependents(conn, fk_schema, fk_table, fk_col, old_ids)
                if c:
                    print(f"  - {c} rows in {fk_schema}.{fk_table}.{fk_col}")

            do_it = ask_yes_no("\nMerge these companies? (y/n): ")
            if not do_it:
                print("    skipped.\n")
                continue

            merge_company_group(conn, group, apply=args.apply)
            print()

        print("\nAll done.")
        if not args.apply:
            print("Ran in DRY RUN mode. Re-run with --apply to execute changes.")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
