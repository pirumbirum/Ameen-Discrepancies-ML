#!/usr/bin/env python3
"""
Pass 1: Metadata Sweep
Pull lightweight metadata for federal corporate litigation dockets.
Self-contained -- no external imports beyond requests.
"""

import requests
import json
import os
import sys
import time
from datetime import datetime


# --- Config from environment ---
TOKEN = os.environ.get("COURTLISTENER_TOKEN", "")
if not TOKEN:
    print("ERROR: COURTLISTENER_TOKEN not set")
    sys.exit(1)

DATE_START = os.environ.get("DATE_START", "2015-01-01")
DATE_END = os.environ.get("DATE_END", "2025-12-31")
NOS_TIER = os.environ.get("NOS_TIER", "all")
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"

BASE_URL = "https://www.courtlistener.com/api/rest/v4"
HEADERS = {"Authorization": f"Token {TOKEN}"}
MAX_PAGES_PER_NOS = 2 if DRY_RUN else None

FIELDS = ",".join([
    "id", "case_name", "case_name_full", "docket_number",
    "docket_number_core", "court_id", "nature_of_suit", "cause",
    "jurisdiction_type", "date_filed", "date_terminated",
    "date_last_filing", "assigned_to_str", "referred_to_str",
    "pacer_case_id", "source", "slug", "federal_dn_case_type",
])

TIER1_NOS = [
    "Securities", "Patent", "Trademark", "Antitrust",
    "Stockholders", "RICO", "Trade Secret",
]
TIER2_NOS = [
    "Other Contract", "Insurance", "Banks", "Environmental",
]

if NOS_TIER == "tier1":
    NOS_LIST = TIER1_NOS
elif NOS_TIER == "tier2":
    NOS_LIST = TIER2_NOS
else:
    NOS_LIST = TIER1_NOS + TIER2_NOS


# --- Helpers ---

def save_json(data, filepath):
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def load_json(filepath, default=None):
    if os.path.exists(filepath):
        with open(filepath) as f:
            return json.load(f)
    return default if default is not None else {}


def api_get(url, params=None, max_retries=3):
    """Make a GET request with retry logic."""
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=30)

            if resp.status_code == 429:
                wait = min(60 * (2 ** attempt), 300)
                print(f"  [429] Rate limited. Waiting {wait}s (attempt {attempt+1})")
                time.sleep(wait)
                continue

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code in (500, 502, 503, 504):
                wait = 5 * (2 ** attempt)
                print(f"  [{resp.status_code}] Server error. Waiting {wait}s")
                time.sleep(wait)
                continue

            print(f"  ERROR: {resp.status_code} - {resp.text[:300]}")
            return None

        except requests.RequestException as e:
            wait = 5 * (2 ** attempt)
            print(f"  [NETWORK] {e}. Waiting {wait}s")
            time.sleep(wait)

    print(f"  FAILED after {max_retries} attempts")
    return None


# --- Rate limiter ---
call_timestamps = []
RATE_LIMIT = 4800  # leave 200 buffer from 5000/hr


def rate_limited_get(url, params=None):
    """API get with rate limit tracking."""
    global call_timestamps
    now = time.time()
    one_hour_ago = now - 3600
    call_timestamps = [t for t in call_timestamps if t > one_hour_ago]

    if len(call_timestamps) >= RATE_LIMIT:
        oldest = call_timestamps[0]
        wait = (oldest + 3600) - now + 1
        if wait > 0:
            print(f"  [RATE LIMIT] {len(call_timestamps)} calls/hr. Sleeping {wait:.0f}s...")
            time.sleep(wait)

    call_timestamps.append(time.time())
    return api_get(url, params=params)


# --- Main ---

def main():
    os.makedirs("output/metadata", exist_ok=True)

    # Load checkpoint
    checkpoint = load_json("output/pass1_checkpoint.json", {})

    # Master index
    master_index = load_json("output/pass1_index.json", {"dockets": {}, "stats": {}})
    total_collected = len(master_index["dockets"])

    total_api_calls = 0
    start_time = time.time()
    last_report = time.time()

    print("=" * 60)
    print(f"PASS 1: METADATA SWEEP")
    print(f"Date range: {DATE_START} to {DATE_END}")
    print(f"NOS tier:   {NOS_TIER} ({len(NOS_LIST)} codes)")
    print(f"Dry run:    {DRY_RUN}")
    print(f"Resuming:   {total_collected} already collected")
    print("=" * 60)

    for nos_text in NOS_LIST:
        nos_key = nos_text.lower().replace(" ", "_")

        # Skip completed NOS codes
        if checkpoint.get(f"{nos_key}_completed"):
            print(f"\n[SKIP] {nos_text} -- already completed")
            continue

        print(f"\n{'=' * 60}")
        print(f"[NOS] {nos_text}")
        print("=" * 60)

        # Load existing data for this NOS
        nos_file = f"output/metadata/{nos_key}.json"
        nos_data = load_json(nos_file, [])
        nos_count = len(nos_data)

        params = {
            "court__jurisdiction": "FD",
            "date_filed__gte": DATE_START,
            "date_filed__lte": DATE_END,
            "nature_of_suit__contains": nos_text,
            "order_by": "date_filed,id",
            "fields": FIELDS,
        }

        page = 0
        next_url = None

        while True:
            page += 1
            if MAX_PAGES_PER_NOS and page > MAX_PAGES_PER_NOS:
                print(f"  [DRY RUN] Stopping after {MAX_PAGES_PER_NOS} pages")
                break

            # Fetch page
            if next_url:
                data = rate_limited_get(next_url)
            else:
                data = rate_limited_get(f"{BASE_URL}/dockets/", params=params)

            total_api_calls += 1

            if not data:
                print(f"  [ERROR] Failed to fetch page {page}, moving to next NOS")
                break

            results = data.get("results", [])
            nos_count += len(results)
            nos_data.extend(results)

            # Add to master index
            new_this_page = 0
            for r in results:
                did = str(r["id"])
                if did not in master_index["dockets"]:
                    master_index["dockets"][did] = {
                        "case_name": r.get("case_name", ""),
                        "court_id": r.get("court_id", ""),
                        "nos": r.get("nature_of_suit", ""),
                        "date_filed": r.get("date_filed", ""),
                    }
                    total_collected += 1
                    new_this_page += 1

            print(f"  Page {page}: +{len(results)} results ({new_this_page} new) | NOS total: {nos_count} | Grand total: {total_collected}")

            # Save every 5 pages
            if page % 5 == 0:
                save_json(nos_data, nos_file)

            # Progress report every 15 min
            if time.time() - last_report >= 900:
                save_json(nos_data, nos_file)
                save_json(master_index, "output/pass1_index.json")
                elapsed = time.time() - start_time
                rate = total_collected / max(elapsed, 1) * 3600
                print(f"\n  === PROGRESS REPORT @ {datetime.utcnow().strftime('%H:%M:%S UTC')} ===")
                print(f"  Collected: {total_collected:,}")
                print(f"  API calls: {total_api_calls:,}")
                print(f"  Rate: {rate:,.0f}/hr")
                print(f"  Elapsed: {elapsed/60:.1f} min")
                print(f"  Current NOS: {nos_text}, page {page}\n")
                last_report = time.time()

            # Next page
            next_url = data.get("next")
            if not next_url:
                break

        # Save NOS results
        save_json(nos_data, nos_file)
        checkpoint[f"{nos_key}_completed"] = True
        checkpoint[f"{nos_key}_total"] = nos_count
        checkpoint[f"{nos_key}_completed_at"] = datetime.utcnow().isoformat()
        save_json(checkpoint, "output/pass1_checkpoint.json")

        print(f"  => {nos_text}: {nos_count} cases collected")

    # Final save
    master_index["stats"] = {
        "total_dockets": len(master_index["dockets"]),
        "completed_at": datetime.utcnow().isoformat(),
        "date_range": {"start": DATE_START, "end": DATE_END},
        "nos_tier": NOS_TIER,
        "dry_run": DRY_RUN,
        "total_api_calls": total_api_calls,
    }
    save_json(master_index, "output/pass1_index.json")
    save_json(checkpoint, "output/pass1_checkpoint.json")

    # Final summary
    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"PASS 1 {'DRY RUN ' if DRY_RUN else ''}COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Total unique dockets: {len(master_index['dockets']):,}")
    print(f"  Total API calls:      {total_api_calls:,}")
    print(f"  Elapsed:              {elapsed/60:.1f} min")
    print(f"  Files in output/metadata/")
    print("=" * 60)


if __name__ == "__main__":
    main()
