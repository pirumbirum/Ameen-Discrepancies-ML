#!/usr/bin/env python3
"""
Filter CourtListener bulk dockets CSV for federal corporate litigation.
Reads from stdin (piped from decompressor), writes filtered results to cases/.
Stream-processes — never loads full file into memory.
"""

import csv
import json
import os
import sys
import time
from datetime import datetime
from io import TextIOWrapper

# --- Target NOS codes (PACER standard) ---
# Key = NOS numeric prefix, Value = (label, tier)
TARGET_NOS = {
    "850": ("Securities", 1),
    "830": ("Patent", 1),
    "840": ("Trademark", 1),
    "410": ("Antitrust", 1),
    "160": ("Stockholders", 1),
    "470": ("RICO", 1),
    "880": ("Trade Secret", 1),
    "190": ("Other Contract", 2),
    "110": ("Insurance", 2),
    "430": ("Banks", 2),
    "893": ("Environmental", 2),
}

DATE_START = "2015-01-01"
DATE_END = "2025-12-31"

# Fields to keep in output (matching what we pulled from API)
KEEP_FIELDS = [
    "id", "case_name", "case_name_full", "docket_number",
    "docket_number_core", "court_id", "nature_of_suit", "cause",
    "jurisdiction_type", "date_filed", "date_terminated",
    "date_last_filing", "assigned_to_str", "referred_to_str",
    "pacer_case_id", "source", "slug", "federal_dn_case_type",
]

OUTPUT_DIR = "cases"
METADATA_DIR = f"{OUTPUT_DIR}/metadata"


def match_nos(nos_value):
    """Check if a nature_of_suit value matches our target NOS codes."""
    if not nos_value:
        return None
    nos_stripped = nos_value.strip()
    for code, (label, tier) in TARGET_NOS.items():
        if nos_stripped.startswith(code):
            return code
        # Also match text-only values like "Antitrust" (no numeric prefix)
        if label.lower() in nos_stripped.lower():
            return code
    return None


def in_date_range(date_str):
    """Check if date_filed is in our target range."""
    if not date_str or date_str.strip() == "":
        return False
    d = date_str.strip()[:10]  # Take YYYY-MM-DD portion
    return DATE_START <= d <= DATE_END


def is_federal_district(court_id, jurisdiction_type):
    """Check if this is a federal district court case."""
    # Federal district court IDs end in 'd' (nysd, cacd, txed, etc.)
    # Exclude bankruptcy ('b'), appellate ('ca1', 'ca2'), and other courts
    cid = (court_id or "").strip().lower()
    jtype = (jurisdiction_type or "").strip().lower()

    # If jurisdiction_type is set and looks federal, accept it
    if jtype and any(x in jtype for x in ["federal", "diversity", "u.s. government"]):
        return True

    # Federal district courts end in 'd' and are 3-5 chars
    if len(cid) >= 3 and cid.endswith("d") and not cid.endswith("bd"):
        return True

    return False


def main():
    os.makedirs(METADATA_DIR, exist_ok=True)

    # Storage per NOS code
    nos_buckets = {}
    for code, (label, tier) in TARGET_NOS.items():
        nos_buckets[code] = {
            "label": label,
            "tier": tier,
            "cases": [],
        }

    # Master index for dedup
    seen_ids = set()

    # Stats
    total_rows = 0
    matched_rows = 0
    start_time = time.time()
    last_report = time.time()

    print("=" * 60)
    print("BULK DOCKETS FILTER")
    print(f"Date range: {DATE_START} to {DATE_END}")
    print(f"Target NOS codes: {len(TARGET_NOS)}")
    print("=" * 60)
    sys.stdout.flush()

    # Read CSV from stdin
    reader = csv.DictReader(TextIOWrapper(sys.stdin.buffer, encoding='utf-8', errors='replace'))

    # Log available columns
    if reader.fieldnames:
        print(f"\nCSV columns ({len(reader.fieldnames)}): {reader.fieldnames[:10]}...")
        sys.stdout.flush()

    for row in reader:
        total_rows += 1

        # Progress every 1M rows
        if total_rows % 1_000_000 == 0:
            elapsed = time.time() - start_time
            rate = total_rows / max(elapsed, 1)
            print(f"  [{total_rows/1e6:.0f}M rows] {matched_rows:,} matched | {rate:,.0f} rows/s | {elapsed/60:.1f} min")
            sys.stdout.flush()

        # Filter 1: NOS code match
        nos_value = row.get("nature_of_suit", "")
        nos_code = match_nos(nos_value)
        if not nos_code:
            continue

        # Filter 2: Date range
        date_filed = row.get("date_filed", "")
        if not in_date_range(date_filed):
            continue

        # Filter 3: Federal district court
        court_id = row.get("court_id", "")
        jurisdiction_type = row.get("jurisdiction_type", "")
        if not is_federal_district(court_id, jurisdiction_type):
            continue

        # Dedup by ID
        docket_id = row.get("id", "")
        if docket_id in seen_ids:
            continue
        seen_ids.add(docket_id)

        # Extract fields we want
        case_data = {}
        for field in KEEP_FIELDS:
            case_data[field] = row.get(field, "")

        nos_buckets[nos_code]["cases"].append(case_data)
        matched_rows += 1

    elapsed = time.time() - start_time

    # Save results
    print(f"\n{'=' * 60}")
    print(f"FILTERING COMPLETE")
    print(f"{'=' * 60}")
    print(f"Total rows scanned: {total_rows:,}")
    print(f"Matched cases:      {matched_rows:,}")
    print(f"Time:               {elapsed/60:.1f} min")
    print(f"\nPer NOS breakdown:")

    master_index = {"dockets": {}, "stats": {}}

    for code in sorted(nos_buckets.keys()):
        bucket = nos_buckets[code]
        label = bucket["label"]
        tier = bucket["tier"]
        cases = bucket["cases"]
        count = len(cases)

        print(f"  {code} {label:25s} (Tier {tier}): {count:>8,}")

        # Save per-NOS file
        nos_key = label.lower().replace(" ", "_")
        filepath = f"{METADATA_DIR}/{nos_key}.json"
        with open(filepath, "w") as f:
            json.dump(cases, f, indent=2)

        # Add to master index
        for c in cases:
            did = str(c.get("id", ""))
            master_index["dockets"][did] = {
                "case_name": c.get("case_name", ""),
                "court_id": c.get("court_id", ""),
                "nos": c.get("nature_of_suit", ""),
                "date_filed": c.get("date_filed", ""),
            }

    # Save master index
    master_index["stats"] = {
        "total_dockets": len(master_index["dockets"]),
        "source": "bulk_csv",
        "bulk_file": "dockets-2025-12-31.csv.bz2",
        "completed_at": datetime.utcnow().isoformat(),
        "date_range": {"start": DATE_START, "end": DATE_END},
        "total_rows_scanned": total_rows,
        "processing_time_seconds": round(elapsed, 1),
    }
    with open(f"{OUTPUT_DIR}/pass1_index.json", "w") as f:
        json.dump(master_index, f, indent=2)

    # Save checkpoint
    checkpoint = {}
    for code, bucket in nos_buckets.items():
        nos_key = bucket["label"].lower().replace(" ", "_")
        checkpoint[f"{nos_key}_completed"] = True
        checkpoint[f"{nos_key}_total"] = len(bucket["cases"])
        checkpoint[f"{nos_key}_nos_code"] = code
    with open(f"{OUTPUT_DIR}/pass1_checkpoint.json", "w") as f:
        json.dump(checkpoint, f, indent=2)

    print(f"\n  TOTAL: {matched_rows:,} federal corporate litigation cases")
    print(f"  Saved to {OUTPUT_DIR}/")
    print("DONE")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
