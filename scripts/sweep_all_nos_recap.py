#!/usr/bin/env python3
"""
Sweep ALL NOS categories to find cases with BOTH opinions AND RECAP.
Outputs to golden_set_recap/ ranked by opinion count.

Two stages per NOS:
  Stage 1: Paginate search API type=r for each NOS, cross-ref with our cases
  Stage 2: For RECAP matches, check opinion clusters via /clusters/?docket={id}

Then build golden_set_recap/ with all BOTH cases ranked by opinion count.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

TOKEN = os.environ.get("CL_API_TOKEN", "") or os.environ.get("COURTLISTENER_TOKEN", "")
BASE = "https://www.courtlistener.com/api/rest/v4"
OUTPUT_DIR = "golden_set_recap"
RESULTS_DIR = "research"

NOS_CODES = {
    "securities": "850",
    "patent": "830",
    "trademark": "840",
    "antitrust": "410",
    "stockholders": "160",
    "rico": "470",
    "trade_secret": "880",
    "insurance": "110",
    "other_contract": "190",
    "banks": "430",
    "environmental": "893",
}

if not TOKEN:
    print("FATAL: No token (set CL_API_TOKEN or COURTLISTENER_TOKEN)")
    sys.exit(1)

stats = {"api_calls": 0, "start_time": time.time()}


def api(url, params=None):
    stats["api_calls"] += 1
    if params:
        qs = urllib.parse.urlencode(params)
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{qs}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Token {TOKEN}",
        "User-Agent": "Ameen-AllNOS-Sweep/1.0",
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


# ============================================================
# Load ALL our cases across all NOS categories
# ============================================================
print("Loading all NOS categories...", flush=True)
all_cases_by_nos = {}  # nos_label -> {docket_id: case_data}
all_our_ids = set()

for nos_label, nos_code in sorted(NOS_CODES.items()):
    filepath = f"cases2/metadata/{nos_label}.json"
    if not os.path.exists(filepath):
        print(f"  WARNING: {filepath} not found, skipping", flush=True)
        continue
    with open(filepath) as f:
        cases = json.load(f)
    case_map = {}
    for c in cases:
        did = str(c.get("id", ""))
        if did:
            case_map[did] = c
            all_our_ids.add(did)
    all_cases_by_nos[nos_label] = case_map
    print(f"  {nos_label:20s} (NOS {nos_code}): {len(case_map):>8,} cases", flush=True)

print(f"  {'TOTAL':>24s}: {len(all_our_ids):>8,} unique docket IDs\n", flush=True)


# ============================================================
# SWEEP EACH NOS: Stage 1 (RECAP) + Stage 2 (opinions)
# ============================================================
all_both_cases = []  # master list across all NOS
per_nos_summary = {}

for nos_label, nos_code in sorted(NOS_CODES.items()):
    case_map = all_cases_by_nos.get(nos_label, {})
    our_ids = set(case_map.keys())
    if not our_ids:
        continue

    print(f"\n{'='*70}", flush=True)
    print(f"  {nos_label.upper()} (NOS {nos_code}) — {len(our_ids):,} cases", flush=True)
    print(f"{'='*70}", flush=True)

    # ── Stage 1: RECAP sweep ──
    print(f"  Stage 1: Paginating RECAP search...", flush=True)

    first_params = {
        "type": "r",
        "q": f"suitNature:{nos_code}",
        "available_only": "on",
        "order_by": "dateFiled asc",
    }
    data, err = api(f"{BASE}/search/", first_params)
    if not data:
        print(f"  RECAP search failed: {err}, skipping {nos_label}", flush=True)
        per_nos_summary[nos_label] = {"error": str(err)}
        continue

    recap_total = data.get("count", 0)
    print(f"  Total RECAP results for NOS {nos_code}: {recap_total}", flush=True)

    recap_docket_ids = set()
    for r in data.get("results", []):
        did = str(r.get("docket_id", ""))
        if did:
            recap_docket_ids.add(did)

    next_url = data.get("next")
    page = 1

    while next_url:
        page += 1
        data, err = api(next_url)
        if not data:
            print(f"    Page {page} failed: {err}, retrying...", flush=True)
            time.sleep(2)
            data, err = api(next_url)
            if not data:
                print(f"    Page {page} failed again, stopping", flush=True)
                break

        for r in data.get("results", []):
            did = str(r.get("docket_id", ""))
            if did:
                recap_docket_ids.add(did)

        next_url = data.get("next")

        if page % 50 == 0:
            elapsed = time.time() - stats["start_time"]
            print(f"    Page {page}: {len(recap_docket_ids)} RECAP IDs "
                  f"({stats['api_calls']} calls, {elapsed/60:.1f}min)", flush=True)

        time.sleep(0.15)

    # Cross-reference
    our_with_recap = our_ids & recap_docket_ids

    print(f"  Stage 1 done: {len(recap_docket_ids)} RECAP IDs, "
          f"{len(our_with_recap)} match our cases ({len(our_with_recap)/len(our_ids)*100:.1f}%)", flush=True)

    # ── Stage 2: Opinion check ──
    print(f"  Stage 2: Checking opinions for {len(our_with_recap)} RECAP cases...", flush=True)

    both_cases = []
    recap_only = 0
    errors = 0

    for i, did in enumerate(sorted(our_with_recap)):
        case = case_map.get(did, {})

        data, err = api(f"{BASE}/clusters/", {
            "docket": did,
            "page_size": "1",
            "fields": "id",
        })

        if data is None:
            errors += 1
        else:
            count = data.get("count", 0)
            if isinstance(count, str):
                has_opinions = len(data.get("results", [])) > 0
                opinion_count = 1 if has_opinions else 0
            else:
                opinion_count = count
                has_opinions = count > 0

            if has_opinions:
                both_cases.append({
                    "docket_id": did,
                    "case_name": case.get("case_name", ""),
                    "court_id": case.get("court_id", ""),
                    "date_filed": case.get("date_filed", ""),
                    "nos_category": nos_label,
                    "nos_code": nos_code,
                    "opinion_count": opinion_count,
                })
            else:
                recap_only += 1

        if (i + 1) % 100 == 0:
            elapsed = time.time() - stats["start_time"]
            print(f"    [{i+1}/{len(our_with_recap)}] {len(both_cases)} BOTH, "
                  f"{recap_only} recap-only, {errors} errors ({elapsed/60:.1f}min)", flush=True)

        time.sleep(0.2)

    print(f"  Stage 2 done: {len(both_cases)} BOTH, {recap_only} recap-only, {errors} errors", flush=True)

    per_nos_summary[nos_label] = {
        "nos_code": nos_code,
        "total_cases": len(our_ids),
        "recap_total_search": recap_total,
        "our_with_recap": len(our_with_recap),
        "our_with_recap_pct": round(len(our_with_recap) / len(our_ids) * 100, 1),
        "cases_with_both": len(both_cases),
        "cases_with_both_pct": round(len(both_cases) / len(our_ids) * 100, 1) if our_ids else 0,
        "recap_only": recap_only,
        "errors": errors,
    }

    all_both_cases.extend(both_cases)
    print(f"  Running total BOTH: {len(all_both_cases)}", flush=True)


# ============================================================
# RANK BY OPINION COUNT + BUILD golden_set_recap/
# ============================================================
print(f"\n{'='*70}", flush=True)
print(f"  BUILDING golden_set_recap/ — {len(all_both_cases)} total BOTH cases", flush=True)
print(f"{'='*70}", flush=True)

# Sort by opinion count descending, then by case name for ties
all_both_cases.sort(key=lambda x: (-x["opinion_count"], x["case_name"]))

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Also group by NOS for per-category subfolders
by_nos = {}
for case in all_both_cases:
    cat = case["nos_category"]
    by_nos.setdefault(cat, []).append(case)

# Build per-NOS subfolders
for cat, cases in sorted(by_nos.items()):
    cat_dir = os.path.join(OUTPUT_DIR, cat)
    os.makedirs(cat_dir, exist_ok=True)

    # Rank within this NOS category
    cases.sort(key=lambda x: -x["opinion_count"])

    cat_index = []
    for rank, case in enumerate(cases, 1):
        cat_index.append({
            "rank": rank,
            "docket_id": case["docket_id"],
            "case_name": case["case_name"],
            "court_id": case["court_id"],
            "date_filed": case["date_filed"],
            "opinion_count": case["opinion_count"],
        })

    with open(os.path.join(cat_dir, "index.json"), "w") as f:
        json.dump(cat_index, f, indent=2)

    print(f"  {cat:20s}: {len(cases):>5} cases (top opinion count: "
          f"{cases[0]['opinion_count'] if cases else 0})", flush=True)


# Master index — all cases ranked globally by opinion count
master_index = []
for rank, case in enumerate(all_both_cases, 1):
    master_index.append({
        "global_rank": rank,
        "docket_id": case["docket_id"],
        "case_name": case["case_name"],
        "court_id": case["court_id"],
        "date_filed": case["date_filed"],
        "nos_category": case["nos_category"],
        "nos_code": case["nos_code"],
        "opinion_count": case["opinion_count"],
    })

with open(os.path.join(OUTPUT_DIR, "master_index.json"), "w") as f:
    json.dump(master_index, f, indent=2)

# Summary
with open(os.path.join(OUTPUT_DIR, "summary.json"), "w") as f:
    json.dump({
        "total_both_cases": len(all_both_cases),
        "per_nos": per_nos_summary,
        "top_20": master_index[:20],
        "api_calls": stats["api_calls"],
        "elapsed_minutes": round((time.time() - stats["start_time"]) / 60, 1),
    }, f, indent=2)

# Also save detailed results for research
with open(os.path.join(RESULTS_DIR, "all_nos_both_cases.json"), "w") as f:
    json.dump({
        "total_both_cases": len(all_both_cases),
        "per_nos_summary": per_nos_summary,
        "all_both_cases": all_both_cases,
        "api_calls": stats["api_calls"],
        "elapsed_minutes": round((time.time() - stats["start_time"]) / 60, 1),
    }, f, indent=2)

# ============================================================
# FINAL REPORT
# ============================================================
elapsed = time.time() - stats["start_time"]
print(f"\n{'='*70}", flush=True)
print(f"  FINAL REPORT", flush=True)
print(f"{'='*70}", flush=True)
print(f"  Total cases with BOTH (opinions + RECAP): {len(all_both_cases)}", flush=True)
print(f"\n  Per NOS breakdown:", flush=True)
for cat, info in sorted(per_nos_summary.items()):
    if isinstance(info, dict) and "cases_with_both" in info:
        print(f"    {cat:20s}: {info['cases_with_both']:>5} BOTH out of "
              f"{info['total_cases']:>6} total ({info['cases_with_both_pct']:.1f}%)", flush=True)

print(f"\n  Top 20 by opinion count:", flush=True)
print(f"  {'Rank':>4} {'Opinions':>8} {'NOS':>14} {'Case Name'}", flush=True)
print(f"  {'-'*4} {'-'*8} {'-'*14} {'-'*45}", flush=True)
for entry in master_index[:20]:
    print(f"  {entry['global_rank']:>4} {entry['opinion_count']:>8} "
          f"{entry['nos_category']:>14} {entry['case_name'][:45]}", flush=True)

print(f"\n  Total API calls: {stats['api_calls']}", flush=True)
print(f"  Total time: {elapsed/60:.1f} minutes", flush=True)
print(f"\n  Output saved to: {OUTPUT_DIR}/", flush=True)
print(f"  Research saved to: {RESULTS_DIR}/all_nos_both_cases.json", flush=True)
