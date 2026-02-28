#!/usr/bin/env python3
"""
Full two-stage sweep for trade_secret (NOS 880):
  Stage 1: Paginate ALL RECAP results for NOS 880, cross-ref with our 2,395 cases
  Stage 2: For cases WITH RECAP, check opinions via /clusters/?docket={id}

Commits progress updates every ~15 minutes.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

TOKEN = os.environ.get("CL_API_TOKEN", "") or os.environ.get("COURTLISTENER_TOKEN", "")
BASE = "https://www.courtlistener.com/api/rest/v4"
PROGRESS_DIR = "research/sweep_progress"
RESULTS_FILE = "research/sweep_trade_secret_results.json"

if not TOKEN:
    print("FATAL: No token set")
    sys.exit(1)

os.makedirs(PROGRESS_DIR, exist_ok=True)

# Stats
stats = {"api_calls": 0, "start_time": time.time(), "stage": "init"}
last_commit_time = time.time()
COMMIT_INTERVAL = 15 * 60  # 15 minutes


def api(url, params=None):
    stats["api_calls"] += 1
    if params:
        qs = urllib.parse.urlencode(params)
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{qs}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Token {TOKEN}",
        "User-Agent": "Ameen-Sweep/1.0",
    })
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode()), None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 2 * (2 ** attempt)
                print(f"  RATE LIMITED, waiting {wait}s...", flush=True)
                time.sleep(wait)
                continue
            return None, f"HTTP {e.code}"
        except Exception as e:
            if attempt < 3:
                time.sleep(2)
                continue
            return None, str(e)
    return None, "MAX_RETRIES"


def commit_progress(message, force=False):
    """Git add + commit + push progress files if enough time has passed."""
    global last_commit_time
    elapsed_since_commit = time.time() - last_commit_time
    if not force and elapsed_since_commit < COMMIT_INTERVAL:
        return
    try:
        subprocess.run(["git", "add", "research/"], check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", message],
            check=True, capture_output=True
        )
        subprocess.run(
            ["git", "push"], check=True, capture_output=True, timeout=30
        )
        last_commit_time = time.time()
        elapsed = time.time() - stats["start_time"]
        print(f"  [COMMITTED @ {elapsed/60:.0f}min] {message}", flush=True)
    except Exception as e:
        print(f"  [commit skipped: {e}]", flush=True)


def save_progress(data, label):
    """Save progress snapshot to disk."""
    elapsed = time.time() - stats["start_time"]
    data["_meta"] = {
        "api_calls": stats["api_calls"],
        "elapsed_seconds": round(elapsed),
        "elapsed_minutes": round(elapsed / 60, 1),
        "stage": stats["stage"],
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    }
    with open(f"{PROGRESS_DIR}/{label}.json", "w") as f:
        json.dump(data, f, indent=2, default=str)


# ============================================================
# Load our cases
# ============================================================
print("Loading trade_secret cases...", flush=True)
with open("cases2/metadata/trade_secret.json") as f:
    our_cases = json.load(f)
our_ids = {c["id"] for c in our_cases}
our_map = {c["id"]: c for c in our_cases}
print(f"  Loaded {len(our_ids)} cases", flush=True)

# ============================================================
# STAGE 1: Full RECAP sweep
# ============================================================
stats["stage"] = "stage1_recap_sweep"
print(f"\n{'='*60}", flush=True)
print(f"  STAGE 1: Full RECAP sweep (NOS 880, q=suitNature:880)", flush=True)
print(f"{'='*60}", flush=True)

# First request to get total count
first_params = {
    "type": "r",
    "q": "suitNature:880",
    "available_only": "on",
    "order_by": "dateFiled asc",
}
data, err = api(f"{BASE}/search/", first_params)
if not data:
    print(f"FATAL: Initial RECAP request failed: {err}", flush=True)
    sys.exit(1)

recap_total = data.get("count", 0)
recap_doc_total = data.get("document_count", 0)
print(f"  Total RECAP results: {recap_total}", flush=True)
print(f"  Total documents: {recap_doc_total}", flush=True)

# Collect all results
all_recap_docket_ids = set()
all_recap_results = []
page = 1

for r in data.get("results", []):
    did = str(r.get("docket_id", ""))
    if did:
        all_recap_docket_ids.add(did)
    all_recap_results.append({
        "docket_id": did,
        "caseName": r.get("caseName", ""),
        "suitNature": r.get("suitNature", ""),
        "dateFiled": r.get("dateFiled", ""),
        "court": r.get("court", ""),
    })

next_url = data.get("next")

while next_url:
    page += 1
    data, err = api(next_url)
    if not data:
        print(f"  Page {page} failed: {err}, retrying...", flush=True)
        time.sleep(2)
        data, err = api(next_url)
        if not data:
            print(f"  Page {page} failed again, stopping pagination", flush=True)
            break

    for r in data.get("results", []):
        did = str(r.get("docket_id", ""))
        if did:
            all_recap_docket_ids.add(did)
        all_recap_results.append({
            "docket_id": did,
            "caseName": r.get("caseName", ""),
            "suitNature": r.get("suitNature", ""),
            "dateFiled": r.get("dateFiled", ""),
            "court": r.get("court", ""),
        })

    next_url = data.get("next")

    if page % 20 == 0:
        elapsed = time.time() - stats["start_time"]
        print(f"  Page {page}: {len(all_recap_docket_ids)} unique docket IDs "
              f"({stats['api_calls']} calls, {elapsed/60:.1f}min)", flush=True)
        # Save + maybe commit progress
        our_with_recap = our_ids & all_recap_docket_ids
        save_progress({
            "recap_total_reported": recap_total,
            "pages_so_far": page,
            "unique_docket_ids": len(all_recap_docket_ids),
            "our_cases_with_recap": len(our_with_recap),
            "our_cases_total": len(our_ids),
            "percent_with_recap": round(len(our_with_recap) / len(our_ids) * 100, 1),
        }, "stage1_progress")
        commit_progress(f"Stage 1 progress: page {page}, {len(our_with_recap)} matches")

    time.sleep(0.15)

# Stage 1 final
our_with_recap = our_ids & all_recap_docket_ids
our_without_recap = our_ids - all_recap_docket_ids

elapsed = time.time() - stats["start_time"]
print(f"\n  STAGE 1 COMPLETE:", flush=True)
print(f"    Pages: {page}", flush=True)
print(f"    Unique RECAP docket IDs: {len(all_recap_docket_ids)}", flush=True)
print(f"    Our cases WITH RECAP: {len(our_with_recap)} ({len(our_with_recap)/len(our_ids)*100:.1f}%)", flush=True)
print(f"    Our cases WITHOUT RECAP: {len(our_without_recap)} ({len(our_without_recap)/len(our_ids)*100:.1f}%)", flush=True)
print(f"    API calls: {stats['api_calls']}, elapsed: {elapsed/60:.1f}min", flush=True)

stage1_result = {
    "recap_total_reported": recap_total,
    "recap_doc_total": recap_doc_total,
    "pages": page,
    "unique_recap_docket_ids": len(all_recap_docket_ids),
    "our_with_recap": len(our_with_recap),
    "our_without_recap": len(our_without_recap),
    "our_with_recap_pct": round(len(our_with_recap) / len(our_ids) * 100, 1),
    "our_with_recap_ids": sorted(our_with_recap),
    "our_without_recap_ids": sorted(our_without_recap),
}
save_progress(stage1_result, "stage1_final")
commit_progress("Stage 1 complete: RECAP sweep done", force=True)

# ============================================================
# STAGE 2: Opinion check for RECAP-positive cases
# ============================================================
stats["stage"] = "stage2_opinion_check"
print(f"\n{'='*60}", flush=True)
print(f"  STAGE 2: Opinion check for {len(our_with_recap)} RECAP-positive cases", flush=True)
print(f"{'='*60}", flush=True)

cases_with_both = []
cases_recap_only = []
opinion_errors = []

recap_list = sorted(our_with_recap)
total_to_check = len(recap_list)

for i, did in enumerate(recap_list):
    case = our_map.get(did, {})

    data, err = api(f"{BASE}/clusters/", {
        "docket": did,
        "page_size": "1",
        "fields": "id",
    })

    if data is None:
        opinion_errors.append({"docket_id": did, "error": str(err)})
        print(f"  [{i+1}/{total_to_check}] {did}: ERROR {err}", flush=True)
    else:
        count = data.get("count", 0)
        # count can be a URL string if no count=on param — check type
        if isinstance(count, str):
            # Means count wasn't returned as int, check results
            has_opinions = len(data.get("results", [])) > 0
            opinion_count = 1 if has_opinions else 0
        else:
            opinion_count = count
            has_opinions = count > 0

        if has_opinions:
            cases_with_both.append({
                "docket_id": did,
                "case_name": case.get("case_name", ""),
                "court_id": case.get("court_id", ""),
                "date_filed": case.get("date_filed", ""),
                "opinion_count": opinion_count,
            })
            print(f"  [{i+1}/{total_to_check}] {did}: {opinion_count} opinions -> BOTH", flush=True)
        else:
            cases_recap_only.append(did)

    # Progress update every 50 cases
    if (i + 1) % 50 == 0 or (i + 1) == total_to_check:
        elapsed = time.time() - stats["start_time"]
        print(f"  -- Progress: {i+1}/{total_to_check} checked, "
              f"{len(cases_with_both)} BOTH, {len(cases_recap_only)} RECAP-only, "
              f"{len(opinion_errors)} errors, {elapsed/60:.1f}min", flush=True)
        save_progress({
            "checked": i + 1,
            "total_to_check": total_to_check,
            "both_count": len(cases_with_both),
            "recap_only_count": len(cases_recap_only),
            "error_count": len(opinion_errors),
            "both_cases": cases_with_both,
        }, "stage2_progress")
        commit_progress(
            f"Stage 2 progress: {i+1}/{total_to_check} checked, {len(cases_with_both)} BOTH"
        )

    time.sleep(0.2)

# ============================================================
# FINAL RESULTS
# ============================================================
stats["stage"] = "complete"
elapsed = time.time() - stats["start_time"]

print(f"\n{'='*60}", flush=True)
print(f"  FINAL RESULTS — trade_secret (NOS 880)", flush=True)
print(f"{'='*60}", flush=True)
print(f"  Total cases: {len(our_ids)}", flush=True)
print(f"  Cases with RECAP: {len(our_with_recap)} ({len(our_with_recap)/len(our_ids)*100:.1f}%)", flush=True)
print(f"  Cases with BOTH (RECAP + opinions): {len(cases_with_both)} ({len(cases_with_both)/len(our_ids)*100:.1f}%)", flush=True)
print(f"  Cases RECAP-only (no opinions): {len(cases_recap_only)} ({len(cases_recap_only)/len(our_ids)*100:.1f}%)", flush=True)
print(f"  Cases without RECAP: {len(our_without_recap)} ({len(our_without_recap)/len(our_ids)*100:.1f}%)", flush=True)
print(f"  Errors: {len(opinion_errors)}", flush=True)
print(f"  Total API calls: {stats['api_calls']}", flush=True)
print(f"  Total time: {elapsed/60:.1f} minutes", flush=True)

# Breakdown for cases without RECAP — we need opinions check too
# Actually, a case could have opinions but NO recap
# Let's check a sample of 20 no-recap cases for opinions
print(f"\n  BONUS: Checking 20 no-RECAP cases for opinions...", flush=True)
no_recap_with_opinions = []
no_recap_sample = sorted(our_without_recap)[:20]
for did in no_recap_sample:
    data, err = api(f"{BASE}/clusters/", {"docket": did, "page_size": "1", "fields": "id"})
    if data:
        count = data.get("count", 0)
        if isinstance(count, int) and count > 0:
            no_recap_with_opinions.append(did)
            print(f"    {did}: {count} opinions (no RECAP)", flush=True)
        elif isinstance(count, str) and len(data.get("results", [])) > 0:
            no_recap_with_opinions.append(did)
            print(f"    {did}: has opinions (no RECAP)", flush=True)
    time.sleep(0.2)

print(f"  Of 20 no-RECAP cases, {len(no_recap_with_opinions)} have opinions", flush=True)

# Save final
final = {
    "category": "trade_secret",
    "nos": "880",
    "total_cases": len(our_ids),
    "recap_sweep_total": recap_total,
    "cases_with_recap": len(our_with_recap),
    "cases_with_recap_pct": round(len(our_with_recap) / len(our_ids) * 100, 1),
    "cases_with_both": len(cases_with_both),
    "cases_with_both_pct": round(len(cases_with_both) / len(our_ids) * 100, 1),
    "cases_recap_only": len(cases_recap_only),
    "cases_without_recap": len(our_without_recap),
    "opinion_errors": len(opinion_errors),
    "api_calls": stats["api_calls"],
    "elapsed_minutes": round(elapsed / 60, 1),
    "both_case_details": cases_with_both,
    "recap_only_ids": cases_recap_only,
    "without_recap_ids": sorted(our_without_recap),
    "error_details": opinion_errors,
    "no_recap_opinion_sample": {
        "checked": len(no_recap_sample),
        "with_opinions": len(no_recap_with_opinions),
        "ids": no_recap_with_opinions,
    },
}

with open(RESULTS_FILE, "w") as f:
    json.dump(final, f, indent=2, default=str)
print(f"\nSaved to {RESULTS_FILE}", flush=True)

# Final commit
save_progress({"status": "complete"}, "complete")
commit_progress("COMPLETE: trade_secret sweep — RECAP + opinions", force=True)
