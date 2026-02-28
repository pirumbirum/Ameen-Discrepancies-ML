#!/usr/bin/env python3
"""
Diagnostic + data collection for the 326 trade_secret BOTH cases.

Key improvements over previous version:
  - Aggressive retry: 8 attempts, backoff up to 120s
  - Diagnostic: captures rate-limit headers, response times, error details
  - 15-minute progress reports via git commit + push
  - Multiple approaches: per-case search, docket API, full pagination
  - Throttle: configurable delay between requests
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
PROGRESS_DIR = "research/test326_progress"
LOG_FILE = "research/test_326_log.txt"

if not TOKEN:
    print("FATAL: No token (set CL_API_TOKEN or COURTLISTENER_TOKEN)")
    sys.exit(1)

os.makedirs(PROGRESS_DIR, exist_ok=True)

stats = {
    "api_calls": 0,
    "rate_limits_hit": 0,
    "errors": [],
    "start_time": time.time(),
    "diagnostics": [],
}
last_commit_time = time.time()
COMMIT_INTERVAL = 15 * 60  # 15 minutes
REQUEST_DELAY = 0.5  # seconds between normal requests
MAX_RETRIES = 8
INITIAL_BACKOFF = 3  # seconds


def log(msg):
    print(msg, flush=True)


def api(url, params=None, label=""):
    """Make API call with robust retry, diagnostic headers, and long backoff."""
    stats["api_calls"] += 1
    if params:
        qs = urllib.parse.urlencode(params)
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{qs}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Token {TOKEN}",
        "User-Agent": "Ameen-Test326-Diag/2.0",
    })

    for attempt in range(MAX_RETRIES):
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = resp.read().decode()
                elapsed_ms = int((time.time() - t0) * 1000)

                # Capture rate-limit headers for diagnostics
                headers = dict(resp.headers)
                rl_info = {
                    "status": resp.status,
                    "elapsed_ms": elapsed_ms,
                    "x-ratelimit-remaining": headers.get("X-RateLimit-Remaining", "?"),
                    "x-ratelimit-limit": headers.get("X-RateLimit-Limit", "?"),
                    "retry-after": headers.get("Retry-After", "?"),
                    "x-ratelimit-reset": headers.get("X-RateLimit-Reset", "?"),
                }

                # Log first few diagnostics and any interesting ones
                if stats["api_calls"] <= 3 or label == "diag":
                    stats["diagnostics"].append({
                        "call": stats["api_calls"],
                        "label": label,
                        "url_short": url[:120],
                        **rl_info,
                        "all_headers": {k: v for k, v in headers.items()
                                        if any(x in k.lower() for x in
                                               ["rate", "limit", "retry", "throttle",
                                                "remaining", "x-"])},
                    })

                return json.loads(body), None, rl_info

        except urllib.error.HTTPError as e:
            elapsed_ms = int((time.time() - t0) * 1000)
            err_headers = dict(e.headers) if hasattr(e, 'headers') else {}
            err_body = ""
            try:
                err_body = e.read().decode()[:500]
            except Exception:
                pass

            if e.code == 429:
                stats["rate_limits_hit"] += 1
                # Use Retry-After header if available
                retry_after = err_headers.get("Retry-After", "")
                if retry_after and retry_after.isdigit():
                    wait = int(retry_after) + 1
                else:
                    wait = INITIAL_BACKOFF * (2 ** attempt)
                    wait = min(wait, 120)

                diag = {
                    "call": stats["api_calls"],
                    "label": label,
                    "type": "RATE_LIMITED",
                    "attempt": attempt + 1,
                    "wait_s": wait,
                    "elapsed_ms": elapsed_ms,
                    "retry-after": err_headers.get("Retry-After", "?"),
                    "x-ratelimit-remaining": err_headers.get("X-RateLimit-Remaining", "?"),
                    "x-ratelimit-limit": err_headers.get("X-RateLimit-Limit", "?"),
                    "x-ratelimit-reset": err_headers.get("X-RateLimit-Reset", "?"),
                    "err_body": err_body[:200],
                    "all_rate_headers": {k: v for k, v in err_headers.items()
                                         if any(x in k.lower() for x in
                                                ["rate", "limit", "retry", "throttle",
                                                 "remaining", "x-"])},
                }
                stats["diagnostics"].append(diag)
                log(f"  RATE LIMITED (attempt {attempt+1}/{MAX_RETRIES}), "
                    f"waiting {wait}s... [Retry-After={err_headers.get('Retry-After','?')}]")
                time.sleep(wait)
                continue

            elif e.code == 403:
                stats["errors"].append({
                    "call": stats["api_calls"], "label": label,
                    "type": "FORBIDDEN", "code": 403, "body": err_body[:200],
                })
                return None, f"HTTP 403 FORBIDDEN", None

            else:
                stats["errors"].append({
                    "call": stats["api_calls"], "label": label,
                    "type": f"HTTP_{e.code}", "body": err_body[:200],
                })
                if attempt < MAX_RETRIES - 1:
                    wait = INITIAL_BACKOFF * (2 ** attempt)
                    wait = min(wait, 60)
                    time.sleep(wait)
                    continue
                return None, f"HTTP {e.code}", None

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait = INITIAL_BACKOFF * (2 ** attempt)
                wait = min(wait, 60)
                time.sleep(wait)
                continue
            return None, str(e), None

    return None, "MAX_RETRIES", None


def commit_progress(message, force=False):
    """Git commit + push progress if 15 minutes have passed."""
    global last_commit_time
    elapsed_since = time.time() - last_commit_time
    if not force and elapsed_since < COMMIT_INTERVAL:
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
        log(f"  [COMMITTED @ {elapsed/60:.0f}min] {message}")
    except Exception as e:
        log(f"  [commit skipped: {e}]")


def save_snapshot(data, label):
    """Save progress snapshot."""
    data["_meta"] = {
        "api_calls": stats["api_calls"],
        "rate_limits_hit": stats["rate_limits_hit"],
        "elapsed_seconds": round(time.time() - stats["start_time"]),
        "elapsed_minutes": round((time.time() - stats["start_time"]) / 60, 1),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    }
    with open(f"{PROGRESS_DIR}/{label}.json", "w") as f:
        json.dump(data, f, indent=2, default=str)


# ============================================================
# Load the 326 BOTH cases
# ============================================================
with open("research/sweep_trade_secret_results.json") as f:
    results = json.load(f)

both_cases = results["both_case_details"]
log(f"Loaded {len(both_cases)} BOTH cases from trade_secret sweep\n")

# ============================================================
# PHASE 0: DIAGNOSTIC — test API rate limit status
# ============================================================
log("=" * 70)
log("  PHASE 0: DIAGNOSTIC — checking API status & rate limits")
log("=" * 70)

# Simple ping to see current rate limit state
log("  Testing with a lightweight clusters query...")
data, err, rl = api(f"{BASE}/clusters/", {"page_size": "1", "fields": "id"}, label="diag")
if data:
    log(f"  API is responsive. Rate limit info:")
    if rl:
        for k, v in rl.items():
            log(f"    {k}: {v}")
else:
    log(f"  WARNING: First API call failed: {err}")
    log(f"  Will proceed with extra caution (longer delays)...")
    REQUEST_DELAY = 2.0  # slow down

time.sleep(1)

# Second diagnostic: test search API
log("\n  Testing search API (type=r)...")
data, err, rl = api(f"{BASE}/search/", {"type": "r", "q": "suitNature:880", "page_size": "1"}, label="diag")
if data:
    recap_total = data.get("count", 0)
    log(f"  Search API OK. RECAP total for NOS 880: {recap_total}")
    if rl:
        for k, v in rl.items():
            log(f"    {k}: {v}")
    first_result = (data.get("results") or [{}])[0]
    log(f"  First result keys: {sorted(first_result.keys())}")
    recap_docs = first_result.get("recap_documents", [])
    log(f"  First result recap_documents count: {len(recap_docs)}")
    if recap_docs:
        log(f"  Sample doc keys: {sorted(recap_docs[0].keys()) if isinstance(recap_docs[0], dict) else type(recap_docs[0])}")
else:
    log(f"  Search API failed: {err}")

time.sleep(1)

# Third diagnostic: test docket endpoint
log("\n  Testing docket endpoint...")
sample_did = both_cases[0]["docket_id"]
data, err, rl = api(f"{BASE}/dockets/{sample_did}/", label="diag")
if data:
    docket_keys = sorted(data.keys())
    log(f"  Docket API OK. Keys: {docket_keys[:20]}...")
    recap_fields = [k for k in docket_keys if "recap" in k.lower() or "document" in k.lower() or "entry" in k.lower()]
    log(f"  RECAP-related fields: {recap_fields}")
    for rf in recap_fields:
        val = data.get(rf)
        if isinstance(val, (int, float, str, bool)):
            log(f"    {rf}: {val}")
        elif isinstance(val, list):
            log(f"    {rf}: list[{len(val)}]")
        elif isinstance(val, dict):
            log(f"    {rf}: dict with keys {sorted(val.keys())[:10]}")
        else:
            log(f"    {rf}: {type(val).__name__}")
else:
    log(f"  Docket API failed: {err}")

time.sleep(1)

# Save diagnostics
save_snapshot({
    "phase": "diagnostic",
    "diagnostics": stats["diagnostics"],
    "errors": stats["errors"],
}, "phase0_diagnostic")
commit_progress("326 test: Phase 0 diagnostics complete", force=True)

# ============================================================
# PHASE 1: Per-case RECAP doc counts via search API
# ============================================================
log(f"\n{'=' * 70}")
log(f"  PHASE 1: Per-case RECAP doc lookup for {len(both_cases)} cases")
log(f"  Approach: search API type=r with docket_id per case")
log(f"{'=' * 70}")

enriched = []
failed_cases = []
approach_a_works = None  # will set on first result

for i, case in enumerate(both_cases):
    did = str(case["docket_id"])

    # Try search API per-case: type=r filtered by docket_id
    data, err, rl = api(
        f"{BASE}/search/",
        {"type": "r", "q": f"docket_id:{did}"},
        label=f"search_r_{did}",
    )

    if data is not None:
        if approach_a_works is None:
            approach_a_works = True
            log(f"  Approach A (search per-case) is working!")
            # Show structure of first result
            results_list = data.get("results", [])
            log(f"  First case ({did}): {data.get('count', '?')} results, "
                f"{len(results_list)} in page")
            if results_list:
                r0 = results_list[0]
                docs = r0.get("recap_documents", [])
                log(f"    recap_documents in result: {len(docs)}")
                if docs and isinstance(docs[0], dict):
                    log(f"    First doc keys: {sorted(docs[0].keys())}")
                    log(f"    First doc sample: {json.dumps(docs[0], indent=2)[:400]}")

        # Count documents across all result pages (usually just 1 for per-case)
        doc_count = 0
        for r in data.get("results", []):
            doc_count += len(r.get("recap_documents", []))

        enriched.append({
            "docket_id": did,
            "case_name": case.get("case_name", ""),
            "court_id": case.get("court_id", ""),
            "date_filed": case.get("date_filed", ""),
            "opinion_count": case.get("opinion_count", 0),
            "recap_doc_count": doc_count,
            "search_result_count": data.get("count", 0),
        })
    else:
        if approach_a_works is None and err == "MAX_RETRIES":
            approach_a_works = False
            log(f"  Approach A failed on first case: {err}")
            log(f"  Switching to Approach B (docket API)...")
            break

        failed_cases.append({"docket_id": did, "error": str(err)})
        enriched.append({
            "docket_id": did,
            "case_name": case.get("case_name", ""),
            "court_id": case.get("court_id", ""),
            "date_filed": case.get("date_filed", ""),
            "opinion_count": case.get("opinion_count", 0),
            "recap_doc_count": -1,  # unknown
            "error": str(err),
        })

    # Progress reporting
    if (i + 1) % 25 == 0 or (i + 1) == len(both_cases):
        elapsed = time.time() - stats["start_time"]
        done = len([c for c in enriched if c.get("recap_doc_count", -1) >= 0])
        has_docs = len([c for c in enriched if c.get("recap_doc_count", 0) > 0])
        log(f"  [{i+1}/{len(both_cases)}] {done} OK, {len(failed_cases)} failed, "
            f"{has_docs} have docs, {stats['rate_limits_hit']} rate limits "
            f"({stats['api_calls']} calls, {elapsed/60:.1f}min)")

        save_snapshot({
            "phase": "per_case_search",
            "processed": i + 1,
            "total": len(both_cases),
            "ok": done,
            "failed": len(failed_cases),
            "has_docs": has_docs,
            "enriched_so_far": enriched,
        }, "phase1_progress")
        commit_progress(
            f"326 test progress: {i+1}/{len(both_cases)} cases, {has_docs} have docs"
        )

    time.sleep(REQUEST_DELAY)

# ============================================================
# PHASE 1B: Fallback — docket API approach if search failed
# ============================================================
if approach_a_works is False:
    log(f"\n{'=' * 70}")
    log(f"  PHASE 1B: Fallback — trying docket API for each case")
    log(f"{'=' * 70}")

    enriched = []
    failed_cases = []

    for i, case in enumerate(both_cases):
        did = str(case["docket_id"])

        data, err, rl = api(f"{BASE}/dockets/{did}/", label=f"docket_{did}")

        if data is not None:
            # Look for any count-like fields
            entry_count = 0
            if "docket_entries" in data:
                val = data["docket_entries"]
                if isinstance(val, list):
                    entry_count = len(val)
                elif isinstance(val, str) and val.startswith("http"):
                    # It's a URL — would need to follow it
                    entry_count = -1
                elif isinstance(val, int):
                    entry_count = val

            recap_docs_count = data.get("recap_documents_count", 0)
            if isinstance(recap_docs_count, str):
                recap_docs_count = 0

            enriched.append({
                "docket_id": did,
                "case_name": case.get("case_name", data.get("case_name", "")),
                "court_id": case.get("court_id", ""),
                "date_filed": case.get("date_filed", ""),
                "opinion_count": case.get("opinion_count", 0),
                "docket_entry_count": entry_count,
                "recap_documents_count": recap_docs_count,
                "source": data.get("source", ""),
                "ia_needs_upload": data.get("ia_needs_upload", ""),
                "ia_date_first_change": data.get("ia_date_first_change", ""),
            })

            if i == 0:
                log(f"  Approach B working. Sample fields for {did}:")
                log(f"    docket_entries type: {type(data.get('docket_entries', 'N/A')).__name__}")
                log(f"    recap_documents_count: {recap_docs_count}")
                log(f"    source: {data.get('source', '?')}")
        else:
            failed_cases.append({"docket_id": did, "error": str(err)})

        if (i + 1) % 25 == 0 or (i + 1) == len(both_cases):
            elapsed = time.time() - stats["start_time"]
            done = len(enriched)
            log(f"  [{i+1}/{len(both_cases)}] {done} OK, {len(failed_cases)} failed, "
                f"{stats['rate_limits_hit']} rate limits "
                f"({stats['api_calls']} calls, {elapsed/60:.1f}min)")

            save_snapshot({
                "phase": "docket_api_fallback",
                "processed": i + 1,
                "total": len(both_cases),
                "ok": done,
                "failed": len(failed_cases),
                "enriched_so_far": enriched,
            }, "phase1b_progress")
            commit_progress(
                f"326 test 1B: {i+1}/{len(both_cases)} via docket API"
            )

        time.sleep(REQUEST_DELAY)

# ============================================================
# PHASE 1C: Fallback — full RECAP pagination with heavy throttle
# ============================================================
if approach_a_works is False and not enriched:
    log(f"\n{'=' * 70}")
    log(f"  PHASE 1C: Last resort — full RECAP pagination (slow, throttled)")
    log(f"{'=' * 70}")

    both_ids = {str(c["docket_id"]) for c in both_cases}
    recap_doc_counts = {}

    data, err, rl = api(
        f"{BASE}/search/",
        {"type": "r", "q": "suitNature:880", "available_only": "on",
         "order_by": "dateFiled asc"},
        label="pagination_start",
    )

    if data:
        for r in data.get("results", []):
            did = str(r.get("docket_id", ""))
            if did:
                recap_doc_counts[did] = recap_doc_counts.get(did, 0) + len(r.get("recap_documents", []))

        next_url = data.get("next")
        page = 1

        while next_url:
            page += 1
            data, err, rl = api(next_url, label=f"page_{page}")
            if not data:
                log(f"  Page {page} failed: {err}, stopping")
                break

            for r in data.get("results", []):
                did = str(r.get("docket_id", ""))
                if did:
                    recap_doc_counts[did] = recap_doc_counts.get(did, 0) + len(r.get("recap_documents", []))

            next_url = data.get("next")

            if page % 10 == 0:
                matched = len(set(recap_doc_counts.keys()) & both_ids)
                elapsed = time.time() - stats["start_time"]
                log(f"  Page {page}: {len(recap_doc_counts)} dockets, {matched}/{len(both_ids)} matched "
                    f"({stats['api_calls']} calls, {elapsed/60:.1f}min)")
                save_snapshot({
                    "phase": "full_pagination",
                    "page": page,
                    "dockets_seen": len(recap_doc_counts),
                    "matched": matched,
                }, "phase1c_progress")
                commit_progress(f"326 test 1C: page {page}, {matched} matched")

            time.sleep(1.0)  # heavy throttle

        # Merge
        enriched = []
        for case in both_cases:
            did = str(case["docket_id"])
            enriched.append({
                "docket_id": did,
                "case_name": case.get("case_name", ""),
                "court_id": case.get("court_id", ""),
                "date_filed": case.get("date_filed", ""),
                "opinion_count": case.get("opinion_count", 0),
                "recap_doc_count": recap_doc_counts.get(did, 0),
            })

# ============================================================
# PHASE 2: RESULTS — rank and report
# ============================================================
log(f"\n{'=' * 70}")
log(f"  PHASE 2: RESULTS")
log(f"{'=' * 70}")

# Sort by opinion count desc
enriched.sort(key=lambda x: (-(x.get("opinion_count", 0)), x.get("case_name", "")))

# Doc count field name depends on which approach worked
doc_field = "recap_doc_count"
if enriched and "docket_entry_count" in enriched[0]:
    doc_field = "docket_entry_count"

# Stats
ok_cases = [c for c in enriched if c.get(doc_field, -1) >= 0]
has_docs = [c for c in enriched if c.get(doc_field, 0) > 0]

log(f"\n  Total cases processed: {len(enriched)}")
log(f"  Successfully queried: {len(ok_cases)}")
log(f"  Failed: {len(failed_cases)}")
log(f"  Cases with documents > 0: {len(has_docs)}")

if has_docs:
    max_docs = max(c[doc_field] for c in has_docs)
    avg_docs = sum(c[doc_field] for c in has_docs) / len(has_docs)
    log(f"  Max {doc_field}: {max_docs}")
    log(f"  Avg {doc_field} (non-zero): {avg_docs:.1f}")

log(f"\n  {'Rank':>4} {'Opinions':>8} {doc_field:>14}  {'Case Name'}")
log(f"  {'-'*4} {'-'*8} {'-'*14}  {'-'*50}")
for i, c in enumerate(enriched[:50], 1):
    log(f"  {i:>4} {c.get('opinion_count', 0):>8} {c.get(doc_field, '?'):>14}  "
        f"{c.get('case_name', '')[:50]}")

# ============================================================
# PHASE 3: SAVE EVERYTHING
# ============================================================
elapsed = time.time() - stats["start_time"]

output = {
    "total": len(enriched),
    "ok": len(ok_cases),
    "failed": len(failed_cases),
    "with_docs": len(has_docs),
    "without_docs": len(ok_cases) - len(has_docs),
    "doc_field": doc_field,
    "approach": "search_per_case" if approach_a_works else ("docket_api" if enriched else "pagination"),
    "api_calls": stats["api_calls"],
    "rate_limits_hit": stats["rate_limits_hit"],
    "elapsed_minutes": round(elapsed / 60, 1),
    "cases": enriched,
    "failed_cases": failed_cases,
    "diagnostics": stats["diagnostics"],
    "errors": stats["errors"],
}

with open("research/test_326_with_doc_counts.json", "w") as f:
    json.dump(output, f, indent=2)

# ============================================================
# FINAL SUMMARY
# ============================================================
log(f"\n{'=' * 70}")
log(f"  FINAL SUMMARY")
log(f"{'=' * 70}")
log(f"  Approach used: {output['approach']}")
log(f"  Cases: {output['total']} total, {output['ok']} OK, {output['failed']} failed")
log(f"  With docs: {output['with_docs']}")
log(f"  Rate limits hit: {stats['rate_limits_hit']}")
log(f"  API calls: {stats['api_calls']}")
log(f"  Elapsed: {elapsed/60:.1f} minutes")
log(f"  Saved to: research/test_326_with_doc_counts.json")
log(f"\n  Diagnostics ({len(stats['diagnostics'])} entries):")
for d in stats["diagnostics"][:10]:
    log(f"    {json.dumps(d, default=str)[:200]}")

# Final commit
save_snapshot(output, "final")
commit_progress("326 test: COMPLETE — doc counts + diagnostics", force=True)
