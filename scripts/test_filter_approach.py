#!/usr/bin/env python3
"""
Test run: check a small sample of cases for BOTH opinions AND RECAP data.

For ~50 cases from 3 NOS categories, check:
  1. /clusters/?docket={id}&page_size=1  -> opinion cluster count
  2. search/?type=r&docket_id:{id}&available_only=on -> RECAP availability

Report hit rates and timing to validate the approach before scaling.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
import random

TOKEN = os.environ.get("CL_API_TOKEN", "") or os.environ.get("COURTLISTENER_TOKEN", "")
BASE = "https://www.courtlistener.com/api/rest/v4"
CASES_DIR = "cases2/metadata"

if not TOKEN:
    print("FATAL: No token")
    sys.exit(1)

_calls = 0


def api(url, params=None):
    global _calls
    _calls += 1
    if params:
        qs = urllib.parse.urlencode(params)
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{qs}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Token {TOKEN}",
        "User-Agent": "Ameen-TestFilter/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as e:
        return None, e.code
    except Exception as e:
        return None, str(e)


def check_opinions(docket_id):
    """Check opinion cluster count for a docket."""
    data, err = api(f"{BASE}/clusters/", {
        "docket": docket_id,
        "page_size": "1",
        "fields": "id,date_filed,precedential_status",
    })
    if data:
        count = data.get("count", 0)
        # If count is a URL (count=on style), it means there are results
        if isinstance(count, str):
            # Paginated response — has results
            count = len(data.get("results", []))
            if data.get("next"):
                count = "1+"  # at least 1
        return count, data.get("results", [])
    return 0, []


def check_recap(docket_id):
    """Check RECAP availability via search API."""
    data, err = api(f"{BASE}/search/", {
        "type": "r",
        "q": f"docket_id:{docket_id}",
        "available_only": "on",
    })
    if data:
        count = data.get("count", 0)
        doc_count = data.get("document_count", 0)
        results = data.get("results", [])
        # Extract nested recap docs from search results
        recap_docs = []
        for r in results:
            for doc in r.get("recap_documents", []):
                recap_docs.append({
                    "id": doc.get("id"),
                    "short_description": doc.get("short_description", "")[:60],
                    "document_number": doc.get("document_number"),
                    "page_count": doc.get("page_count"),
                    "is_available": doc.get("is_available"),
                })
        return count, doc_count, recap_docs
    return 0, 0, []


# Pick test samples: 20 cases from 3 different categories
test_categories = ["securities", "antitrust", "trade_secret"]
sample_size = 20

results = {}
totals = {"tested": 0, "has_opinions": 0, "has_recap": 0, "has_both": 0}

for cat in test_categories:
    path = os.path.join(CASES_DIR, f"{cat}.json")
    with open(path) as f:
        cases = json.load(f)

    # Sample: first 10 + 10 random from the rest
    sample = cases[:10]
    if len(cases) > 20:
        sample += random.sample(cases[10:], min(10, len(cases) - 10))
    else:
        sample = cases[:sample_size]

    print(f"\n{'='*60}")
    print(f"  {cat.upper()} — testing {len(sample)} / {len(cases)} cases")
    print(f"{'='*60}\n")

    cat_results = []
    cat_opinions = 0
    cat_recap = 0
    cat_both = 0

    for i, case in enumerate(sample):
        did = case["id"]
        name = case.get("case_name", "")[:50]

        # Check opinions
        op_count, op_results = check_opinions(did)
        has_opinions = (op_count if isinstance(op_count, int) else 1) > 0

        # Check RECAP
        recap_count, recap_doc_count, recap_docs = check_recap(did)
        has_recap = recap_count > 0

        has_both = has_opinions and has_recap

        totals["tested"] += 1
        if has_opinions:
            totals["has_opinions"] += 1
            cat_opinions += 1
        if has_recap:
            totals["has_recap"] += 1
            cat_recap += 1
        if has_both:
            totals["has_both"] += 1
            cat_both += 1

        status = "BOTH" if has_both else ("OPINIONS" if has_opinions else ("RECAP" if has_recap else "NEITHER"))

        result = {
            "docket_id": did,
            "case_name": case.get("case_name", ""),
            "court_id": case.get("court_id", ""),
            "date_filed": case.get("date_filed", ""),
            "opinion_clusters": op_count,
            "opinion_samples": op_results[:2],
            "recap_docket_count": recap_count,
            "recap_doc_count": recap_doc_count,
            "recap_doc_samples": recap_docs[:3],
            "has_opinions": has_opinions,
            "has_recap": has_recap,
            "has_both": has_both,
        }
        cat_results.append(result)

        print(f"  [{i+1:2d}/{len(sample)}] {did:>10s} {status:8s} "
              f"opinions={op_count} recap_docs={recap_doc_count} "
              f"— {name}")

        time.sleep(0.25)

    results[cat] = cat_results
    print(f"\n  {cat} summary: {cat_opinions}/{len(sample)} opinions, "
          f"{cat_recap}/{len(sample)} recap, {cat_both}/{len(sample)} BOTH")

# Overall summary
print(f"\n{'='*60}")
print(f"  OVERALL RESULTS")
print(f"{'='*60}")
print(f"  Total tested: {totals['tested']}")
print(f"  Has opinions: {totals['has_opinions']} ({totals['has_opinions']/max(totals['tested'],1)*100:.0f}%)")
print(f"  Has RECAP:    {totals['has_recap']} ({totals['has_recap']/max(totals['tested'],1)*100:.0f}%)")
print(f"  Has BOTH:     {totals['has_both']} ({totals['has_both']/max(totals['tested'],1)*100:.0f}%)")
print(f"  API calls:    {_calls}")

# Estimate for full run
calls_per_case = _calls / max(totals["tested"], 1)
total_cases = 275094
est_calls = int(calls_per_case * total_cases)
est_hours = est_calls / 5000
print(f"\n  Estimated for 275K cases:")
print(f"    Calls per case: {calls_per_case:.1f}")
print(f"    Total calls:    {est_calls:,}")
print(f"    At 5000/hr:     {est_hours:.1f} hours")
print(f"    Both rate:      ~{totals['has_both']/max(totals['tested'],1)*100:.0f}% => ~{int(275094 * totals['has_both']/max(totals['tested'],1)):,} cases with BOTH")

# Show sample BOTH cases
print(f"\n{'='*60}")
print(f"  SAMPLE CASES WITH BOTH")
print(f"{'='*60}")
for cat, cat_results in results.items():
    for r in cat_results:
        if r["has_both"]:
            print(f"\n  [{cat}] Docket {r['docket_id']}: {r['case_name'][:60]}")
            print(f"    Court: {r['court_id']}, Filed: {r['date_filed']}")
            print(f"    Opinion clusters: {r['opinion_clusters']}")
            print(f"    RECAP docs: {r['recap_doc_count']}")
            for doc in r["recap_doc_samples"][:2]:
                print(f"      Doc {doc['id']}: {doc['short_description']} "
                      f"(pages={doc['page_count']})")

# Save
os.makedirs("research", exist_ok=True)
with open("research/test_filter_results.json", "w") as f:
    json.dump({"totals": totals, "results": results}, f, indent=2, default=str)
print(f"\nSaved to research/test_filter_results.json")
