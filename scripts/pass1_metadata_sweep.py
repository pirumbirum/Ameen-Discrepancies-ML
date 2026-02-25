#!/usr/bin/env python3
"""
Pass 1: Metadata Sweep
Pull lightweight metadata for federal corporate litigation dockets.
Commits to cases/ folder every 15 minutes.
Self-contained -- no external imports beyond requests.
"""

import requests
import json
import os
import sys
import time
import subprocess
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

# Save to cases/ folder in repo
OUTPUT_DIR = "cases"
METADATA_DIR = f"{OUTPUT_DIR}/metadata"
SAVE_INTERVAL = 900  # 15 minutes

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


def git_commit_and_push(message):
    """Commit cases/ folder and push to remote."""
    try:
        subprocess.run(["git", "add", "cases/"], check=True, capture_output=True)
        # Check if there's anything to commit
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True
        )
        if result.returncode != 0:  # There are staged changes
            subprocess.run(
                ["git", "commit", "-m", message],
                check=True, capture_output=True
            )
            subprocess.run(
                ["git", "push"],
                check=True, capture_output=True
            )
            print(f"  [GIT] Committed and pushed: {message}")
        else:
            print(f"  [GIT] No changes to commit")
    except subprocess.CalledProcessError as e:
        print(f"  [GIT ERROR] {e.stderr.decode() if e.stderr else e}")


def api_get(url, params=None, max_retries=5):
    """Make a GET request with retry logic."""
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=120)

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

        except requests.exceptions.Timeout:
            wait = 15 * (2 ** attempt)
            print(f"  [TIMEOUT] Request timed out. Waiting {wait}s (attempt {attempt+1})")
            time.sleep(wait)
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


# --- Progress report ---

def print_report(total_collected, total_api_calls, start_time, current_nos, current_page, nos_counts):
    elapsed = time.time() - start_time
    rate = total_collected / max(elapsed, 1) * 3600

    print(f"\n{'=' * 60}")
    print(f"  PROGRESS REPORT @ {datetime.utcnow().strftime('%H:%M:%S UTC')}")
    print(f"{'=' * 60}")
    print(f"  Total collected:  {total_collected:>8,}")
    print(f"  API calls made:   {total_api_calls:>8,}")
    print(f"  Rate:             {rate:>8,.0f} dockets/hr")
    print(f"  Elapsed:          {elapsed/60:>8.1f} min")
    print(f"  Current NOS:      {current_nos}")
    print(f"  Current page:     {current_page}")
    print(f"  ---")
    print(f"  Per NOS breakdown:")
    for nos, count in nos_counts.items():
        print(f"    {nos:30s} => {count:>6,}")
    print(f"{'=' * 60}\n")


# --- Main ---

def main():
    os.makedirs(METADATA_DIR, exist_ok=True)

    # Load checkpoint
    checkpoint = load_json(f"{OUTPUT_DIR}/pass1_checkpoint.json", {})

    # Master index
    master_index = load_json(f"{OUTPUT_DIR}/pass1_index.json", {"dockets": {}, "stats": {}})
    total_collected = len(master_index["dockets"])

    total_api_calls = 0
    start_time = time.time()
    last_save_time = time.time()
    nos_counts = {}

    # Restore NOS counts from checkpoint
    for nos_text in NOS_LIST:
        nos_key = nos_text.lower().replace(" ", "_")
        nos_counts[nos_text] = checkpoint.get(f"{nos_key}_total", 0)

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
        nos_file = f"{METADATA_DIR}/{nos_key}.json"
        nos_data = load_json(nos_file, [])
        nos_count = len(nos_data)
        nos_counts[nos_text] = nos_count

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
            nos_counts[nos_text] = nos_count
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

            print(f"  Page {page}: +{len(results)} ({new_this_page} new) | NOS: {nos_count:,} | Total: {total_collected:,}")

            # Save every 5 pages
            if page % 5 == 0:
                save_json(nos_data, nos_file)

            # Every 15 minutes: save, report, commit & push
            if time.time() - last_save_time >= SAVE_INTERVAL:
                save_json(nos_data, nos_file)
                save_json(master_index, f"{OUTPUT_DIR}/pass1_index.json")
                save_json(checkpoint, f"{OUTPUT_DIR}/pass1_checkpoint.json")

                print_report(total_collected, total_api_calls, start_time, nos_text, page, nos_counts)

                git_commit_and_push(
                    f"Pass 1 progress: {total_collected:,} dockets | "
                    f"{nos_text} page {page} | "
                    f"{datetime.utcnow().strftime('%H:%M UTC')}"
                )
                last_save_time = time.time()

            # Next page
            next_url = data.get("next")
            if not next_url:
                break

        # Save NOS results
        save_json(nos_data, nos_file)
        checkpoint[f"{nos_key}_completed"] = True
        checkpoint[f"{nos_key}_total"] = nos_count
        checkpoint[f"{nos_key}_completed_at"] = datetime.utcnow().isoformat()
        save_json(checkpoint, f"{OUTPUT_DIR}/pass1_checkpoint.json")

        print(f"\n  => {nos_text}: {nos_count:,} cases collected")

    # Final save
    master_index["stats"] = {
        "total_dockets": len(master_index["dockets"]),
        "completed_at": datetime.utcnow().isoformat(),
        "date_range": {"start": DATE_START, "end": DATE_END},
        "nos_tier": NOS_TIER,
        "dry_run": DRY_RUN,
        "total_api_calls": total_api_calls,
    }
    save_json(master_index, f"{OUTPUT_DIR}/pass1_index.json")
    save_json(checkpoint, f"{OUTPUT_DIR}/pass1_checkpoint.json")

    # Final report
    print_report(total_collected, total_api_calls, start_time, "DONE", 0, nos_counts)

    # Final commit
    git_commit_and_push(
        f"Pass 1 COMPLETE: {total_collected:,} dockets | "
        f"{total_api_calls} API calls | "
        f"{datetime.utcnow().strftime('%H:%M UTC')}"
    )

    print(f"\nTotal unique dockets: {total_collected:,}")
    print(f"Saved to {OUTPUT_DIR}/")
    print("PASS 1 COMPLETE")


if __name__ == "__main__":
    main()
