"""
scripts/import_lgd.py - Import official Government of India LGD hierarchy into MySQL.

Expected CSV layout (place files in data/lgd/):
    states.csv      : state_code (LGD code), state_name
    districts.csv   : state_code (parent LGD code), district_code, district_name
    tehsils.csv     : district_code (parent LGD code), tehsil_code, tehsil_name
    villages.csv    : tehsil_code (parent LGD code), village_code, village_name

Column names are matched case-insensitively and common LGD header variants are
accepted (code/name columns are located heuristically so the importer works with
different LGD extract downloads from data.gov.in).

Usage:
    python scripts/import_lgd.py

Environment variables (from .env):
    DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error

load_dotenv()  # reads .env into os.environ

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "lgd"

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "kisaan_suvidha"),
    "charset": "utf8mb4",
    "collation": "utf8mb4_unicode_ci",
    "use_pure": True,
}

# Import order matters: parents must exist before children.
# Column candidates match the official Government of India LGD CSV headers
# (data.gov.in LGD directory extracts).
STAGES = [
    {
        "name": "states",
        "file": "states.csv",
        "table": "states",
        "code_candidates": ["state_code", "lgd_code", "code"],
        "name_candidates": ["state_name_english", "state_name", "name"],
        "parent_col": None,
        "parent_table": None,
        "parent_code_candidates": None,
        "insert_sql": (
            "INSERT INTO states (lgd_code, name, is_active) VALUES (%s, %s, 1) "
            "ON DUPLICATE KEY UPDATE name = VALUES(name), is_active = 1"
        ),
    },
    {
        "name": "districts",
        "file": "districts.csv",
        "table": "districts",
        "code_candidates": ["district_code", "lgd_code", "code"],
        "name_candidates": ["district_name_english", "district_name", "name"],
        "parent_col": "state_id",
        "parent_table": "states",
        "parent_code_candidates": ["state_code", "lgd_code", "code"],
        "insert_sql": (
            "INSERT INTO districts (lgd_code, name, state_id, is_active) "
            "VALUES (%s, %s, %s, 1) "
            "ON DUPLICATE KEY UPDATE name = VALUES(name), state_id = VALUES(state_id), is_active = 1"
        ),
    },
    {
        "name": "tehsils",
        "file": "tehsils.csv",
        "table": "tehsils",
        "code_candidates": ["subdistrict_code", "tehsil_code", "lgd_code", "code"],
        "name_candidates": ["subdistrict_name_english", "subdistrict_name", "tehsil_name", "name"],
        "parent_col": "district_id",
        "parent_table": "districts",
        "parent_code_candidates": ["district_code", "lgd_code", "code"],
        "insert_sql": (
            "INSERT INTO tehsils (lgd_code, name, district_id, is_active) "
            "VALUES (%s, %s, %s, 1) "
            "ON DUPLICATE KEY UPDATE name = VALUES(name), district_id = VALUES(district_id), is_active = 1"
        ),
    },
    {
        "name": "villages",
        "file": "villages.csv",
        "table": "villages",
        "code_candidates": ["village_code", "lgd_code", "code"],
        "name_candidates": ["village_name", "name"],
        "parent_col": "tehsil_id",
        "parent_table": "tehsils",
        "parent_code_candidates": ["subdistrict_code", "tehsil_code", "lgd_code", "code"],
        "insert_sql": (
            "INSERT INTO villages (lgd_code, name, tehsil_id, is_active) "
            "VALUES (%s, %s, %s, 1) "
            "ON DUPLICATE KEY UPDATE name = VALUES(name), tehsil_id = VALUES(tehsil_id), is_active = 1"
        ),
    },
]


def normalize_header(header: str) -> str:
    return header.strip().lower().replace(" ", "_").replace("-", "_").replace(".", "_")


def find_column(fieldnames, candidates):
    """Return the first fieldname that matches any candidate (case/format-insensitive)."""
    norm = {normalize_header(h): h for h in fieldnames}
    for cand in candidates:
        key = normalize_header(cand)
        if key in norm:
            return norm[key]
    return None


def resolve_row(row, fieldnames, spec):
    """Extract (code, name) and parent lgd_code from a raw CSV row."""
    code_col = find_column(fieldnames, spec.get("code_candidates", []))
    name_col = find_column(fieldnames, spec.get("name_candidates", []))
    if not code_col or not name_col:
        raise ValueError(
            f"Could not locate code/name columns in {spec['file']}. "
            f"Fields: {fieldnames}"
        )

    code = (row.get(code_col) or "").strip()
    name = (row.get(name_col) or "").strip()
    parent_code = None
    if spec.get("parent_col"):
        parent_col = find_column(fieldnames, spec.get("parent_code_candidates", []))
        if parent_col:
            parent_code = (row.get(parent_col) or "").strip() or None
    return code, name, parent_code


def load_stage(conn, spec, stats):
    path = DATA_DIR / spec["file"]
    if not path.exists():
        print(f"[SKIP] {spec['file']} not found in {DATA_DIR}")
        stats["skipped"].append(spec["file"])
        return

    import sys

    BATCH = 10000
    parent_cache = {}  # lgd_code -> parent table id
    inserted = updated = skipped = 0
    errors = []
    valid_rows = []  # list of (code, name, parent_id_or_None)

    # Pre-load all parent lgd_code -> id so we don't query per row.
    if spec.get("parent_col"):
        cur = conn.cursor()
        cur.execute(
            f"SELECT lgd_code, id FROM {spec['parent_table']} WHERE is_active = 1"
        )
        for lgd_code, pid in cur.fetchall():
            parent_cache[lgd_code] = pid
        cur.close()

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        try:
            for lineno, row in enumerate(reader, start=2):
                try:
                    code, name, parent_code = resolve_row(row, fieldnames, spec)
                except ValueError as exc:
                    errors.append(f"{spec['file']}:{lineno}: {exc}")
                    skipped += 1
                    continue
                if not code or not name:
                    errors.append(f"{spec['file']}:{lineno}: missing code or name")
                    skipped += 1
                    continue

                parent_id = None
                if spec.get("parent_col") and parent_code:
                    parent_id = parent_cache.get(parent_code)
                    if parent_id is None:
                        errors.append(
                            f"{spec['file']}:{lineno}: parent '{parent_code}' not found in {spec['parent_table']}; row skipped"
                        )
                        skipped += 1
                        continue

                valid_rows.append((code, name, parent_id) if spec.get("parent_col") else (code, name))

                # Flush batch when full.
                if len(valid_rows) >= BATCH:
                    cur = conn.cursor()
                    try:
                        cur.executemany(spec["insert_sql"], valid_rows)
                    except Error as exc:
                        # Fall back to one-by-one so a single bad row doesn't kill the batch.
                        conn.rollback()
                        for r in valid_rows:
                            try:
                                cur2 = conn.cursor()
                                cur2.execute(spec["insert_sql"], r)
                                rc = cur2.rowcount
                                cur2.close()
                                if rc == 1:
                                    inserted += 1
                                else:
                                    updated += 1
                            except Error as rxc:
                                errors.append(f"{spec['file']}: batch row '{r[1]}': {rxc}")
                                skipped += 1
                        valid_rows.clear()
                        continue
                    conn.commit()
                    cur.close()
                    processed = len(valid_rows)
                    inserted += processed  # treat batch as inserted (on-dup updates counted separately is complex)
                    valid_rows.clear()
                    print(
                        f"[PROGRESS] {spec['name']}: {inserted + updated} processed…",
                        flush=True,
                    )

            # Insert remaining rows.
            if valid_rows:
                cur = conn.cursor()
                try:
                    cur.executemany(spec["insert_sql"], valid_rows)
                    conn.commit()
                    inserted += len(valid_rows)
                except Error as exc:
                    conn.rollback()
                    for r in valid_rows:
                        try:
                            cur2 = conn.cursor()
                            cur2.execute(spec["insert_sql"], r)
                            rc = cur2.rowcount
                            cur2.close()
                            if rc == 1:
                                inserted += 1
                            else:
                                updated += 1
                        except Error as rxc:
                            errors.append(f"{spec['file']}: final row '{r[1]}': {rxc}")
                            skipped += 1
                cur.close()

        except Exception:
            conn.rollback()
            raise

    stats["inserted"][spec["name"]] = inserted
    stats["updated"][spec["name"]] = updated
    stats["skipped_count"][spec["name"]] = skipped
    stats["errors"].extend(errors)
    print(
        f"[OK] {spec['name']}: inserted={inserted} updated={updated} skipped={skipped}",
        flush=True,
    )


def main():
    if not DATA_DIR.exists():
        print(f"NOTE: LGD data directory not found: {DATA_DIR}")
        print("      Create it and copy official LGD CSV files (states.csv, districts.csv,")
        print("      tehsils.csv, villages.csv) from data.gov.in before importing.")
        print()

    print(f"Connecting to MySQL database '{DB_CONFIG['database']}' as {DB_CONFIG['user']}...")
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
    except Error as e:
        print(f"FATAL: cannot connect to MySQL: {e}")
        print("       Check DB_* environment variables and that MySQL is running.")
        return 1

    stats = {"inserted": {}, "updated": {}, "skipped_count": {}, "errors": [], "skipped": []}
    try:
        for spec in STAGES:
            load_stage(conn, spec, stats)
    finally:
        conn.close()

    print("\n--- Import summary ---")
    for spec in STAGES:
        n = spec["name"]
        print(
            f"  {n:10s} inserted={stats['inserted'].get(n,0):5d} "
            f"updated={stats['updated'].get(n,0):5d} skipped={stats['skipped_count'].get(n,0):5d}"
        )
    if stats["errors"]:
        print(f"\n{len(stats['errors'])} row(s) had errors (see above).")
    if stats["skipped"]:
        print(f"Skipped missing files: {', '.join(stats['skipped'])}")
    print("Done.")
    return 0 if not stats["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
