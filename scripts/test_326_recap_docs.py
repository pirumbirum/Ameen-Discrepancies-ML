#!/usr/bin/env python3
"""
Quick test: re-check the 326 trade_secret BOTH cases via search API type=r
to capture recap_doc_count from the recap_documents array in results.
Then re-rank by opinion count with doc counts surfaced.
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

stats = {"api_calls": 0, "start_time": time.time()}


def api(url, params=None):
    stats["api_calls"] += 1
    if params:
        qs = urllib.parse.urlencode(params)
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{qs}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Token {TOKEN}",
        "User-Agent": "Ameen-Test326/1.0",
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


# Load the 326 BOTH cases
with open("research/sweep_trade_secret_results.json") as f:
    results = json.load(f)

both_cases = results["both_case_details"]
print(f"Loaded {len(both_cases)} BOTH cases from trade_secret sweep\n", flush=True)

# Step 1: Re-paginate search API type=r for NOS 880 to capture recap_documents per docket
print("=" * 70, flush=True)
print("  STAGE 1: Re-paginating RECAP search to capture doc counts", flush=True)
print("=" * 70, flush=True)

both_ids = {str(c["docket_id"]) for c in both_cases}

first_params = {
    "type": "r",
    "q": "suitNature:880",
    "available_only": "on",
    "order_by": "dateFiled asc",
}
data, err = api(f"{BASE}/search/", first_params)
if not data:
    print(f"FATAL: {err}", flush=True)
    sys.exit(1)

recap_total = data.get("count", 0)
recap_doc_global = data.get("document_count", 0)
print(f"  Total RECAP results: {recap_total}", flush=True)
print(f"  Global document_count: {recap_doc_global}", flush=True)

# Capture doc counts
recap_doc_counts = {}  # docket_id -> doc count
matched = 0

# Also peek at what fields each result actually has
first_result = data.get("results", [{}])[0] if data.get("results") else {}
print(f"\n  First result keys: {sorted(first_result.keys())}", flush=True)
recap_docs_sample = first_result.get("recap_documents", [])
print(f"  First result recap_documents count: {len(recap_docs_sample)}", flush=True)
if recap_docs_sample:
    print(f"  Sample recap_document[0] keys: {sorted(recap_docs_sample[0].keys()) if isinstance(recap_docs_sample[0], dict) else type(recap_docs_sample[0])}", flush=True)
    print(f"  Sample recap_document[0]: {json.dumps(recap_docs_sample[0], indent=2)[:500]}", flush=True)

for r in data.get("results", []):
    did = str(r.get("docket_id", ""))
    if did:
        doc_count = len(r.get("recap_documents", []))
        recap_doc_counts[did] = recap_doc_counts.get(did, 0) + doc_count
        if did in both_ids:
            matched += 1

next_url = data.get("next")
page = 1

while next_url:
    page += 1
    data, err = api(next_url)
    if not data:
        time.sleep(2)
        data, err = api(next_url)
        if not data:
            print(f"    Page {page} failed, stopping", flush=True)
            break

    for r in data.get("results", []):
        did = str(r.get("docket_id", ""))
        if did:
            doc_count = len(r.get("recap_documents", []))
            recap_doc_counts[did] = recap_doc_counts.get(did, 0) + doc_count
            if did in both_ids:
                matched += 1

    next_url = data.get("next")

    if page % 20 == 0:
        elapsed = time.time() - stats["start_time"]
        print(f"    Page {page}: {len(recap_doc_counts)} dockets, {matched} matched to 326 "
              f"({stats['api_calls']} calls, {elapsed/60:.1f}min)", flush=True)

    time.sleep(0.15)

print(f"\n  Pagination done: {page} pages, {len(recap_doc_counts)} dockets", flush=True)
print(f"  Matched to 326 BOTH cases: {matched}", flush=True)

# Stats on doc counts
all_counts = list(recap_doc_counts.values())
nonzero = [c for c in all_counts if c > 0]
print(f"\n  Doc count stats (all {len(all_counts)} RECAP dockets):", flush=True)
print(f"    Non-zero: {len(nonzero)}/{len(all_counts)} ({len(nonzero)/max(len(all_counts),1)*100:.1f}%)", flush=True)
if nonzero:
    print(f"    Min: {min(nonzero)}, Max: {max(nonzero)}, Avg: {sum(nonzero)/len(nonzero):.1f}", flush=True)

# Step 2: Merge doc counts into 326 and re-rank
print(f"\n{'='*70}", flush=True)
print(f"  STAGE 2: Re-ranking 326 with doc counts", flush=True)
print(f"{'='*70}", flush=True)

enriched = []
for c in both_cases:
    did = str(c["docket_id"])
    enriched.append({
        "docket_id": did,
        "case_name": c.get("case_name", ""),
        "court_id": c.get("court_id", ""),
        "date_filed": c.get("date_filed", ""),
        "opinion_count": c.get("opinion_count", 0),
        "recap_doc_count": recap_doc_counts.get(did, 0),
    })

# Sort by opinion count desc
enriched.sort(key=lambda x: (-x["opinion_count"], x["case_name"]))

# Print top 50
print(f"\n  {'Rank':>4} {'Opinions':>8} {'RECAP Docs':>10}  {'Case Name'}", flush=True)
print(f"  {'-'*4} {'-'*8} {'-'*10}  {'-'*50}", flush=True)
for i, c in enumerate(enriched[:50], 1):
    print(f"  {i:>4} {c['opinion_count']:>8} {c['recap_doc_count']:>10}  {c['case_name'][:50]}", flush=True)

# Summary stats
has_docs = [c for c in enriched if c["recap_doc_count"] > 0]
print(f"\n  Of 326 BOTH cases:", flush=True)
print(f"    With recap_doc_count > 0: {len(has_docs)}", flush=True)
print(f"    With recap_doc_count = 0: {len(enriched) - len(has_docs)}", flush=True)
if has_docs:
    print(f"    Max doc count: {max(c['recap_doc_count'] for c in has_docs)}", flush=True)
    print(f"    Avg doc count (non-zero): {sum(c['recap_doc_count'] for c in has_docs)/len(has_docs):.1f}", flush=True)

# Save
with open("research/test_326_with_doc_counts.json", "w") as f:
    json.dump({
        "total": len(enriched),
        "with_docs": len(has_docs),
        "without_docs": len(enriched) - len(has_docs),
        "recap_doc_global": recap_doc_global,
        "recap_total": recap_total,
        "cases": enriched,
        "api_calls": stats["api_calls"],
        "elapsed_minutes": round((time.time() - stats["start_time"]) / 60, 1),
    }, f, indent=2)

elapsed = time.time() - stats["start_time"]
print(f"\n  Done. {stats['api_calls']} API calls, {elapsed/60:.1f} min", flush=True)
print(f"  Saved to research/test_326_with_doc_counts.json", flush=True)
