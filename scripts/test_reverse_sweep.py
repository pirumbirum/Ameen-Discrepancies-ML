#!/usr/bin/env python3
"""
Test reverse sweep on ONE NOS category (trade_secret, NOS 880).
Trade_secret had 40% BOTH rate in our sample, so it's a good test.

1. Paginate /clusters/ filtered by NOS to collect all docket IDs with opinions
2. Paginate search/?type=r&available_only=on&suitNature=880 to collect docket IDs with RECAP
3. Load our cases2/metadata/trade_secret.json docket IDs
4. Intersect all three locally
5. Report results + timing + API calls
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

if not TOKEN:
    print("FATAL: No token")
    sys.exit(1)

_calls = 0
_start = time.time()


def api(url, params=None):
    global _calls
    _calls += 1
    if params:
        qs = urllib.parse.urlencode(params)
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{qs}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Token {TOKEN}",
        "User-Agent": "Ameen-ReverseSweep/1.0",
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode()), None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 2 * (2 ** attempt)
                print(f"    RATE LIMITED, waiting {wait}s...")
                time.sleep(wait)
            else:
                return None, e.code
        except Exception as e:
            time.sleep(1)
    return None, "MAX_RETRIES"


def paginate_next(first_url, params, label, max_pages=None):
    """Paginate using cursor-based 'next' links. Returns all results."""
    all_results = []
    data, err = api(first_url, params)
    if not data:
        print(f"    {label}: initial request failed: {err}")
        return all_results, 0

    total = data.get("count", "?")
    all_results.extend(data.get("results", []))
    page = 1

    next_url = data.get("next")
    while next_url and (max_pages is None or page < max_pages):
        page += 1
        data, err = api(next_url)
        if not data:
            print(f"    {label}: page {page} failed: {err}")
            break
        all_results.extend(data.get("results", []))
        next_url = data.get("next")

        if page % 50 == 0:
            print(f"    {label}: page {page}, collected {len(all_results)} so far...")
            sys.stdout.flush()
        time.sleep(0.15)

    print(f"    {label}: DONE — {len(all_results)} results in {page} pages "
          f"(reported total: {total})")
    return all_results, total


# ============================================================
print("=" * 60)
print("  REVERSE SWEEP TEST — trade_secret (NOS 880)")
print("=" * 60)

NOS = "880"
CAT = "trade_secret"

# ============================================================
# STEP 1: Sweep opinion clusters for this NOS
# ============================================================
print(f"\nSTEP 1: Sweeping opinion clusters (NOS {NOS})...")

# We need to get clusters where the parent docket has this NOS.
# /clusters/ doesn't have a direct NOS filter, so we use search API type=o
# which returns cluster_id and docket_id for opinions matching a NOS.
opinion_results, op_total = paginate_next(
    f"{BASE}/search/",
    {"type": "o", "suitNature": NOS, "order_by": "dateFiled asc"},
    "opinions",
    max_pages=500,  # safety limit
)

# Collect docket IDs from opinion search results
opinion_docket_ids = set()
cluster_ids = set()
for r in opinion_results:
    did = r.get("docket_id")
    cid = r.get("cluster_id")
    if did:
        opinion_docket_ids.add(str(did))
    if cid:
        cluster_ids.add(str(cid))

print(f"  Unique docket IDs with opinions: {len(opinion_docket_ids)}")
print(f"  Unique cluster IDs: {len(cluster_ids)}")
elapsed = time.time() - _start
print(f"  API calls so far: {_calls}, elapsed: {elapsed:.0f}s")

# ============================================================
# STEP 2: Sweep RECAP-available dockets for this NOS
# ============================================================
print(f"\nSTEP 2: Sweeping RECAP-available dockets (NOS {NOS})...")

recap_results, recap_total = paginate_next(
    f"{BASE}/search/",
    {"type": "r", "suitNature": NOS, "available_only": "on",
     "order_by": "dateFiled asc"},
    "recap",
    max_pages=500,
)

# Collect docket IDs from RECAP search results
recap_docket_ids = set()
recap_doc_counts = {}
for r in recap_results:
    did = r.get("docket_id")
    if did:
        did_str = str(did)
        recap_docket_ids.add(did_str)
        # Count nested docs
        n_docs = len(r.get("recap_documents", []))
        more = r.get("more_docs", False)
        recap_doc_counts[did_str] = {"nested_count": n_docs, "more_docs": more}

print(f"  Unique docket IDs with RECAP: {len(recap_docket_ids)}")
elapsed = time.time() - _start
print(f"  API calls so far: {_calls}, elapsed: {elapsed:.0f}s")

# ============================================================
# STEP 3: Load our cases and intersect
# ============================================================
print(f"\nSTEP 3: Loading our {CAT} cases and intersecting...")

with open(f"cases2/metadata/{CAT}.json") as f:
    our_cases = json.load(f)

our_ids = {c["id"] for c in our_cases}
our_cases_map = {c["id"]: c for c in our_cases}

print(f"  Our cases: {len(our_ids)}")

# Intersections
has_opinions = our_ids & opinion_docket_ids
has_recap = our_ids & recap_docket_ids
has_both = has_opinions & has_recap
has_either = has_opinions | has_recap
has_neither = our_ids - has_either

print(f"\n  Results:")
print(f"    Has opinions:  {len(has_opinions):>6} ({len(has_opinions)/len(our_ids)*100:.1f}%)")
print(f"    Has RECAP:     {len(has_recap):>6} ({len(has_recap)/len(our_ids)*100:.1f}%)")
print(f"    Has BOTH:      {len(has_both):>6} ({len(has_both)/len(our_ids)*100:.1f}%)")
print(f"    Has neither:   {len(has_neither):>6} ({len(has_neither)/len(our_ids)*100:.1f}%)")

# ============================================================
# STEP 4: Validate against per-case method
# ============================================================
print(f"\nSTEP 4: Validating against per-case method (5 BOTH cases)...")

validation = []
both_list = sorted(has_both)[:5]
for did in both_list:
    case = our_cases_map[did]

    # Per-case opinion check
    data, err = api(f"{BASE}/clusters/", {
        "docket": did, "page_size": "1",
        "fields": "id",
    })
    direct_opinions = 0
    if data:
        count = data.get("count", 0)
        if isinstance(count, int):
            direct_opinions = count
        elif isinstance(count, str):
            direct_opinions = max(len(data.get("results", [])), 1)

    # Per-case RECAP check
    data, err = api(f"{BASE}/search/", {
        "type": "r", "q": f"docket_id:{did}", "available_only": "on",
    })
    direct_recap = 0
    if data:
        direct_recap = data.get("document_count", 0)

    match = direct_opinions > 0 and direct_recap > 0
    validation.append({
        "docket_id": did,
        "case_name": case.get("case_name", "")[:60],
        "sweep_says_both": True,
        "direct_opinions": direct_opinions,
        "direct_recap": direct_recap,
        "direct_confirms_both": match,
    })
    print(f"  {did}: opinions={direct_opinions}, recap={direct_recap} -> {'CONFIRMED' if match else 'MISMATCH'}")
    time.sleep(0.25)

# Also validate 5 NEITHER cases
print(f"\n  Validating 5 NEITHER cases...")
neither_list = sorted(has_neither)[:5]
for did in neither_list:
    case = our_cases_map[did]

    data, _ = api(f"{BASE}/clusters/", {"docket": did, "page_size": "1", "fields": "id"})
    direct_opinions = 0
    if data:
        count = data.get("count", 0)
        if isinstance(count, int):
            direct_opinions = count
        elif isinstance(count, str):
            direct_opinions = max(len(data.get("results", [])), 1)

    data, _ = api(f"{BASE}/search/", {"type": "r", "q": f"docket_id:{did}", "available_only": "on"})
    direct_recap = data.get("document_count", 0) if data else 0

    match = direct_opinions == 0 or direct_recap == 0
    validation.append({
        "docket_id": did,
        "case_name": case.get("case_name", "")[:60],
        "sweep_says_neither": True,
        "direct_opinions": direct_opinions,
        "direct_recap": direct_recap,
        "direct_confirms_no_both": match,
    })
    print(f"  {did}: opinions={direct_opinions}, recap={direct_recap} -> {'CONFIRMED' if match else 'MISMATCH'}")
    time.sleep(0.25)

# ============================================================
# SUMMARY
# ============================================================
elapsed = time.time() - _start
print(f"\n{'='*60}")
print(f"  SUMMARY")
print(f"{'='*60}")
print(f"  Category: {CAT} (NOS {NOS})")
print(f"  Our cases: {len(our_ids)}")
print(f"  Opinions sweep found: {len(opinion_docket_ids)} docket IDs")
print(f"  RECAP sweep found: {len(recap_docket_ids)} docket IDs")
print(f"  Our cases with BOTH: {len(has_both)}")
print(f"  Total API calls: {_calls}")
print(f"  Elapsed time: {elapsed:.0f}s ({elapsed/60:.1f} min)")
print(f"  Calls per our-case: {_calls/len(our_ids):.2f}")

# Project to full 275K
print(f"\n  Projection for all 11 NOS categories (275K cases):")
# Assume similar ratio of sweep pages needed
calls_per_nos = _calls  # rough estimate
total_est = calls_per_nos * 11
hours_est = total_est / 5000
print(f"    ~{calls_per_nos} calls per NOS x 11 = ~{total_est:,} calls")
print(f"    At 5000/hr = ~{hours_est:.1f} hours")

# Sample BOTH cases
print(f"\n  Sample BOTH cases:")
for did in sorted(has_both)[:10]:
    c = our_cases_map[did]
    recap_info = recap_doc_counts.get(did, {})
    print(f"    {did}: {c.get('case_name','')[:55]} "
          f"(court={c.get('court_id')}, filed={c.get('date_filed')}, "
          f"recap_nested={recap_info.get('nested_count',0)}, more={recap_info.get('more_docs',False)})")

# Save
os.makedirs("research", exist_ok=True)
output = {
    "category": CAT,
    "nos": NOS,
    "our_case_count": len(our_ids),
    "opinion_sweep_dockets": len(opinion_docket_ids),
    "recap_sweep_dockets": len(recap_docket_ids),
    "has_opinions": len(has_opinions),
    "has_recap": len(has_recap),
    "has_both": len(has_both),
    "has_neither": len(has_neither),
    "api_calls": _calls,
    "elapsed_seconds": round(elapsed),
    "validation": validation,
    "both_docket_ids": sorted(has_both),
}
with open("research/test_reverse_sweep.json", "w") as f:
    json.dump(output, f, indent=2, default=str)
print(f"\nSaved to research/test_reverse_sweep.json")
