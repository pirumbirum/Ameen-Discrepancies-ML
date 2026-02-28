#!/usr/bin/env python3
"""
For the 326 BOTH cases (RECAP + opinions), get actual counts:
  - Opinion cluster count via /clusters/?docket={id}&count=on
  - RECAP document count via /recap-documents/?docket={id}&count=on
Rank by combined score, output top 100.
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

calls = 0

def api(url, params=None):
    global calls
    calls += 1
    if params:
        qs = urllib.parse.urlencode(params)
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{qs}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Token {TOKEN}",
        "User-Agent": "Ameen-Rank/1.0",
    })
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode()), None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 * (2 ** attempt))
                continue
            return None, f"HTTP {e.code}"
        except Exception as e:
            if attempt < 3:
                time.sleep(2)
                continue
            return None, str(e)
    return None, "MAX_RETRIES"


# Load BOTH cases
with open("research/sweep_trade_secret_results.json") as f:
    results = json.load(f)
both_cases = results["both_case_details"]
print(f"Ranking {len(both_cases)} BOTH cases...\n", flush=True)

# Load full metadata for extra info
with open("cases2/metadata/trade_secret.json") as f:
    all_cases = {c["id"]: c for c in json.load(f)}

ranked = []
start = time.time()

for i, case in enumerate(both_cases):
    did = case["docket_id"]

    # Get opinion cluster count
    data, err = api(f"{BASE}/clusters/", {
        "docket": did, "count": "on", "page_size": "1", "fields": "id",
    })
    if data and isinstance(data.get("count"), int):
        opinion_count = data["count"]
    elif data:
        opinion_count = len(data.get("results", []))
    else:
        opinion_count = 0

    time.sleep(0.15)

    # Get RECAP document count
    data, err = api(f"{BASE}/recap-documents/", {
        "docket_entry__docket": did, "count": "on", "page_size": "1",
        "fields": "id",
    })
    if data and isinstance(data.get("count"), int):
        recap_count = data["count"]
    elif data:
        recap_count = len(data.get("results", []))
    else:
        recap_count = 0

    time.sleep(0.15)

    meta = all_cases.get(did, {})
    entry = {
        "docket_id": did,
        "case_name": case.get("case_name", ""),
        "court_id": case.get("court_id", ""),
        "date_filed": case.get("date_filed", ""),
        "opinion_count": opinion_count,
        "recap_doc_count": recap_count,
        "combined_score": opinion_count + recap_count,
    }
    ranked.append(entry)

    if (i + 1) % 50 == 0:
        elapsed = time.time() - start
        print(f"  [{i+1}/{len(both_cases)}] {elapsed:.0f}s, {calls} API calls", flush=True)

# Sort by combined score descending
ranked.sort(key=lambda x: x["combined_score"], reverse=True)

# Print top 100
print(f"\n{'='*80}", flush=True)
print(f"  TOP 100 CASES — BOTH RECAP + OPINIONS (ranked by combined count)", flush=True)
print(f"{'='*80}", flush=True)
print(f"{'Rank':>4} {'Docket ID':>10} {'Opinions':>8} {'RECAP Docs':>10} {'Combined':>8}  {'Case Name'}", flush=True)
print(f"{'-'*4} {'-'*10} {'-'*8} {'-'*10} {'-'*8}  {'-'*40}", flush=True)

top100 = ranked[:100]
for i, c in enumerate(top100):
    print(f"{i+1:>4} {c['docket_id']:>10} {c['opinion_count']:>8} {c['recap_doc_count']:>10} "
          f"{c['combined_score']:>8}  {c['case_name'][:55]}", flush=True)

# Stats
print(f"\n  Stats for top 100:", flush=True)
avg_opinions = sum(c["opinion_count"] for c in top100) / len(top100)
avg_recap = sum(c["recap_doc_count"] for c in top100) / len(top100)
max_opinions = max(c["opinion_count"] for c in top100)
max_recap = max(c["recap_doc_count"] for c in top100)
print(f"    Avg opinions: {avg_opinions:.1f}, max: {max_opinions}", flush=True)
print(f"    Avg RECAP docs: {avg_recap:.1f}, max: {max_recap}", flush=True)

# Stats for all 326
print(f"\n  Stats for all {len(ranked)}:", flush=True)
avg_opinions_all = sum(c["opinion_count"] for c in ranked) / len(ranked)
avg_recap_all = sum(c["recap_doc_count"] for c in ranked) / len(ranked)
print(f"    Avg opinions: {avg_opinions_all:.1f}", flush=True)
print(f"    Avg RECAP docs: {avg_recap_all:.1f}", flush=True)

elapsed = time.time() - start
print(f"\n  Total: {calls} API calls in {elapsed:.0f}s ({elapsed/60:.1f}min)", flush=True)

# Save
os.makedirs("research", exist_ok=True)
output = {
    "top_100": top100,
    "all_ranked": ranked,
    "stats": {
        "total_both_cases": len(ranked),
        "top100_avg_opinions": round(avg_opinions, 1),
        "top100_avg_recap": round(avg_recap, 1),
        "top100_max_opinions": max_opinions,
        "top100_max_recap": max_recap,
        "all_avg_opinions": round(avg_opinions_all, 1),
        "all_avg_recap": round(avg_recap_all, 1),
        "api_calls": calls,
        "elapsed_seconds": round(elapsed),
    }
}
with open("research/top100_trade_secret.json", "w") as f:
    json.dump(output, f, indent=2)
print(f"\nSaved to research/top100_trade_secret.json", flush=True)
