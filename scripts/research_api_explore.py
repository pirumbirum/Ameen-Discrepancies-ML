#!/usr/bin/env python3
"""
Research-only script: Explore CourtListener API capabilities for RECAP + opinions strategy.
Does NOT modify any data. Outputs a comprehensive report to stdout + JSON file.

Explores:
  1. recap-documents endpoint (filters, count, fields)
  2. clusters endpoint (opinions per docket)
  3. search API (type=r, type=rd, type=d)
  4. count=on efficiency
  5. Sample our 275K dockets for RECAP + opinion availability
  6. OPTIONS requests to discover all available filters
"""

import json
import os
import sys
import time
import requests

TOKEN = os.environ.get("COURTLISTENER_TOKEN", "")
if not TOKEN:
    print("ERROR: COURTLISTENER_TOKEN not set")
    sys.exit(1)

BASE = "https://www.courtlistener.com/api/rest/v4"
HEADERS = {"Authorization": f"Token {TOKEN}", "User-Agent": "Ameen-Research/1.0"}
OUTPUT_DIR = "research"

_calls = 0


def api(url, params=None, method="GET"):
    global _calls
    _calls += 1
    if method == "OPTIONS":
        resp = requests.options(url, headers=HEADERS, timeout=60)
    else:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=60)
    time.sleep(0.2)
    return resp


def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def save_json(name, data):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, name)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  -> Saved to {path}")


report = {}

# ─────────────────────────────────────────────────────────
# 1. OPTIONS on recap-documents — discover all filters
# ─────────────────────────────────────────────────────────
section("1. OPTIONS /recap-documents/ — Discover filters & fields")

resp = api(f"{BASE}/recap-documents/", method="OPTIONS")
print(f"  Status: {resp.status_code}")
if resp.status_code == 200:
    opts = resp.json()
    filters = opts.get("filters", {})
    ordering = opts.get("ordering", [])
    fields = list(opts.get("fields", {}).keys()) if "fields" in opts else []
    print(f"  Available filters: {json.dumps(list(filters.keys()), indent=4)}")
    print(f"  Ordering options: {ordering}")
    print(f"  Fields: {fields[:20]}...")
    report["recap_documents_options"] = {
        "filters": filters,
        "ordering": ordering,
        "field_count": len(fields),
        "fields": fields,
    }
    save_json("recap_documents_options.json", opts)
else:
    print(f"  Error: {resp.status_code} - {resp.text[:300]}")
    report["recap_documents_options"] = {"error": resp.status_code}

# ─────────────────────────────────────────────────────────
# 2. OPTIONS on docket-entries — discover filters
# ─────────────────────────────────────────────────────────
section("2. OPTIONS /docket-entries/ — Discover filters & fields")

resp = api(f"{BASE}/docket-entries/", method="OPTIONS")
print(f"  Status: {resp.status_code}")
if resp.status_code == 200:
    opts = resp.json()
    filters = opts.get("filters", {})
    print(f"  Available filters: {json.dumps(list(filters.keys()), indent=4)}")
    report["docket_entries_options"] = {"filters": filters}
    save_json("docket_entries_options.json", opts)
else:
    report["docket_entries_options"] = {"error": resp.status_code}

# ─────────────────────────────────────────────────────────
# 3. OPTIONS on clusters — discover filters
# ─────────────────────────────────────────────────────────
section("3. OPTIONS /clusters/ — Discover filters & fields")

resp = api(f"{BASE}/clusters/", method="OPTIONS")
print(f"  Status: {resp.status_code}")
if resp.status_code == 200:
    opts = resp.json()
    filters = opts.get("filters", {})
    print(f"  Available filters: {json.dumps(list(filters.keys()), indent=4)}")
    report["clusters_options"] = {"filters": filters}
    save_json("clusters_options.json", opts)
else:
    report["clusters_options"] = {"error": resp.status_code}

# ─────────────────────────────────────────────────────────
# 4. OPTIONS on dockets — discover filters
# ─────────────────────────────────────────────────────────
section("4. OPTIONS /dockets/ — Discover filters & fields")

resp = api(f"{BASE}/dockets/", method="OPTIONS")
print(f"  Status: {resp.status_code}")
if resp.status_code == 200:
    opts = resp.json()
    filters = opts.get("filters", {})
    print(f"  Available filters: {json.dumps(list(filters.keys()), indent=4)}")
    report["dockets_options"] = {"filters": filters}
    save_json("dockets_options.json", opts)
else:
    report["dockets_options"] = {"error": resp.status_code}

# ─────────────────────────────────────────────────────────
# 5. Test recap-documents count for a sample docket
# ─────────────────────────────────────────────────────────
section("5. Test recap-documents count for sample dockets")

# Load a few sample docket IDs from our cases2 data
sample_dockets = []
for nos_file in ["securities.json", "patent.json", "antitrust.json"]:
    path = f"cases2/metadata/{nos_file}"
    if os.path.exists(path):
        with open(path) as f:
            cases = json.load(f)
        # Take first 5 and last 5 per category
        for c in cases[:5] + cases[-5:]:
            sample_dockets.append({
                "id": str(c["id"]),
                "case_name": c.get("case_name", ""),
                "nos": nos_file.replace(".json", ""),
            })

print(f"  Testing {len(sample_dockets)} sample dockets...")
recap_results = []

for s in sample_dockets:
    did = s["id"]

    # Count available RECAP docs
    resp = api(f"{BASE}/recap-documents/", params={
        "docket_entry__docket": did,
        "is_available": "true",
        "page_size": 1,
    })
    recap_count = 0
    if resp.status_code == 200:
        data = resp.json()
        recap_count = data.get("count", len(data.get("results", [])))

    # Count ALL recap docs (including unavailable)
    resp2 = api(f"{BASE}/recap-documents/", params={
        "docket_entry__docket": did,
        "page_size": 1,
    })
    total_recap = 0
    if resp2.status_code == 200:
        data2 = resp2.json()
        total_recap = data2.get("count", len(data2.get("results", [])))

    # Count clusters (opinions)
    resp3 = api(f"{BASE}/clusters/", params={
        "docket": did,
        "page_size": 1,
    })
    cluster_count = 0
    if resp3.status_code == 200:
        data3 = resp3.json()
        cluster_count = data3.get("count", len(data3.get("results", [])))

    # Count docket entries
    resp4 = api(f"{BASE}/docket-entries/", params={
        "docket": did,
        "page_size": 1,
    })
    entry_count = 0
    if resp4.status_code == 200:
        data4 = resp4.json()
        entry_count = data4.get("count", len(data4.get("results", [])))

    result = {
        "docket_id": did,
        "case_name": s["case_name"][:60],
        "nos": s["nos"],
        "recap_available": recap_count,
        "recap_total": total_recap,
        "clusters": cluster_count,
        "entries": entry_count,
    }
    recap_results.append(result)
    print(f"  {did}: recap_avail={recap_count} recap_total={total_recap} "
          f"clusters={cluster_count} entries={entry_count} — {s['case_name'][:40]}")

report["sample_recap_counts"] = recap_results
save_json("sample_recap_counts.json", recap_results)

# ─────────────────────────────────────────────────────────
# 6. Test count=on parameter efficiency
# ─────────────────────────────────────────────────────────
section("6. Test count=on parameter on various endpoints")

count_tests = {}
for endpoint, params in [
    ("recap-documents", {"is_available": "true"}),
    ("recap-documents", {}),
    ("docket-entries", {}),
    ("clusters", {}),
    ("dockets", {"nature_of_suit__contains": "Securities"}),
    ("dockets", {"nature_of_suit__contains": "Patent"}),
]:
    p = dict(params)
    p["count"] = "on"
    resp = api(f"{BASE}/{endpoint}/", params=p)
    if resp.status_code == 200:
        data = resp.json()
        count_val = data.get("count", "N/A")
        label = f"{endpoint} ({', '.join(f'{k}={v}' for k,v in params.items()) or 'all'})"
        count_tests[label] = count_val
        print(f"  {label}: {count_val:,}" if isinstance(count_val, int) else f"  {label}: {count_val}")
    else:
        print(f"  {endpoint}: HTTP {resp.status_code}")

report["global_counts"] = count_tests
save_json("global_counts.json", count_tests)

# ─────────────────────────────────────────────────────────
# 7. Search API: type=r (dockets with RECAP docs)
# ─────────────────────────────────────────────────────────
section("7. Search API type=r — Dockets with RECAP documents")

search_r_results = {}
for nos in ["850", "830", "410", "160", "470"]:
    resp = api(f"{BASE}/search/", params={
        "type": "r",
        "suitNature": nos,
        "order_by": "dateFiled desc",
    })
    if resp.status_code == 200:
        data = resp.json()
        docket_count = data.get("count", 0)
        doc_count = data.get("document_count", 0)
        results = data.get("results", [])
        # Examine first result
        first = {}
        if results:
            r = results[0]
            first = {
                "docket_id": r.get("docket_id"),
                "caseName": r.get("caseName", ""),
                "dateFiled": r.get("dateFiled", ""),
                "recap_doc_count_nested": len(r.get("recap_documents", [])),
                "more_docs": r.get("more_docs", False),
            }
        info = {
            "docket_count": docket_count,
            "document_count": doc_count,
            "first_result": first,
        }
        search_r_results[f"NOS_{nos}"] = info
        print(f"  NOS {nos}: ~{docket_count:,} dockets, ~{doc_count:,} documents")
        if first:
            print(f"    First: {first.get('caseName','')[:50]} (docs nested: {first.get('recap_doc_count_nested')})")
    else:
        print(f"  NOS {nos}: HTTP {resp.status_code}")

report["search_type_r"] = search_r_results
save_json("search_type_r.json", search_r_results)

# ─────────────────────────────────────────────────────────
# 8. Search API: type=rd (flat RECAP documents)
# ─────────────────────────────────────────────────────────
section("8. Search API type=rd — Flat RECAP document search")

search_rd_results = {}
for nos in ["850", "830", "410"]:
    resp = api(f"{BASE}/search/", params={
        "type": "rd",
        "suitNature": nos,
        "order_by": "dateFiled desc",
    })
    if resp.status_code == 200:
        data = resp.json()
        count = data.get("count", 0)
        results = data.get("results", [])
        first = {}
        if results:
            r = results[0]
            first = {
                "docket_id": r.get("docket_id"),
                "short_description": r.get("short_description", ""),
                "document_number": r.get("document_number", ""),
                "page_count": r.get("page_count"),
                "is_available": r.get("is_available"),
            }
        search_rd_results[f"NOS_{nos}"] = {"count": count, "first_result": first}
        print(f"  NOS {nos} type=rd: ~{count:,} documents")
        if first:
            print(f"    First: doc#{first.get('document_number','')} pages={first.get('page_count')} avail={first.get('is_available')}")
    else:
        print(f"  NOS {nos}: HTTP {resp.status_code}")

report["search_type_rd"] = search_rd_results
save_json("search_type_rd.json", search_rd_results)

# ─────────────────────────────────────────────────────────
# 9. Search API: type=d (docket only, fastest)
# ─────────────────────────────────────────────────────────
section("9. Search API type=d — Docket-only search (fast)")

search_d_results = {}
for nos in ["850", "830", "410", "160", "470", "880", "190", "110", "430", "893", "840"]:
    resp = api(f"{BASE}/search/", params={
        "type": "d",
        "suitNature": nos,
    })
    if resp.status_code == 200:
        data = resp.json()
        count = data.get("count", 0)
        search_d_results[f"NOS_{nos}"] = count
        print(f"  NOS {nos}: ~{count:,} dockets")
    else:
        print(f"  NOS {nos}: HTTP {resp.status_code}")

report["search_type_d_counts"] = search_d_results
save_json("search_type_d_counts.json", search_d_results)

# ─────────────────────────────────────────────────────────
# 10. Test: Can we search for cases with BOTH opinions AND RECAP docs?
# ─────────────────────────────────────────────────────────
section("10. Search for cases with BOTH opinions AND RECAP docs")

# Search type=r with q parameter to filter for available docs
combo_results = {}
for nos in ["850", "830", "410"]:
    # type=r with is_available:true means cases that have available RECAP docs
    resp = api(f"{BASE}/search/", params={
        "type": "r",
        "suitNature": nos,
        "q": "is_available:true",
        "order_by": "dateFiled desc",
    })
    if resp.status_code == 200:
        data = resp.json()
        combo_results[f"NOS_{nos}_recap_available"] = {
            "docket_count": data.get("count", 0),
            "document_count": data.get("document_count", 0),
        }
        print(f"  NOS {nos} (is_available:true): ~{data.get('count',0):,} dockets, "
              f"~{data.get('document_count',0):,} docs")

    # Also try type=o for opinions count
    resp2 = api(f"{BASE}/search/", params={
        "type": "o",
        "q": f"suitNature:{nos}",
    })
    if resp2.status_code == 200:
        data2 = resp2.json()
        combo_results[f"NOS_{nos}_opinions"] = data2.get("count", 0)
        print(f"  NOS {nos} opinions (type=o): ~{data2.get('count',0):,}")

report["combo_search"] = combo_results
save_json("combo_search.json", combo_results)

# ─────────────────────────────────────────────────────────
# 11. Fetch CourtListener website pages for strategy info
# ─────────────────────────────────────────────────────────
section("11. Fetch key website pages")

pages_to_fetch = [
    ("https://www.courtlistener.com/help/api/bulk-data/", "bulk_data_page.html"),
    ("https://www.courtlistener.com/help/api/rest/pacer/", "pacer_api_page.html"),
    ("https://www.courtlistener.com/help/api/rest/case-law/", "case_law_api_page.html"),
    ("https://www.courtlistener.com/help/api/rest/search/", "search_api_page.html"),
    ("https://www.courtlistener.com/coverage/recap/", "recap_coverage_page.html"),
    ("https://www.courtlistener.com/help/api/rest/", "rest_api_overview.html"),
]

for url, filename in pages_to_fetch:
    try:
        resp = requests.get(url, headers={"User-Agent": "Ameen-Research/1.0"}, timeout=30)
        path = os.path.join(OUTPUT_DIR, filename)
        with open(path, "w") as f:
            f.write(resp.text)
        print(f"  {url} -> {path} ({len(resp.text):,} bytes, HTTP {resp.status_code})")
    except Exception as e:
        print(f"  {url} -> ERROR: {e}")

# ─────────────────────────────────────────────────────────
# 12. Deep dive: Sample a high-activity docket
# ─────────────────────────────────────────────────────────
section("12. Deep dive into a data-rich sample docket")

# Find a docket with many entries via search
resp = api(f"{BASE}/search/", params={
    "type": "r",
    "suitNature": "850",
    "q": "is_available:true",
    "order_by": "dateFiled asc",
})
if resp.status_code == 200:
    results = resp.json().get("results", [])
    if results:
        sample_did = results[0].get("docket_id")
        print(f"  Sample docket ID: {sample_did}")
        print(f"  Case: {results[0].get('caseName','')[:60]}")

        # Fetch full docket detail
        resp2 = api(f"{BASE}/dockets/{sample_did}/", params={
            "fields": "id,case_name,date_filed,date_terminated,date_last_filing,"
                      "nature_of_suit,court_id,clusters,source,slug,"
                      "docket_number,assigned_to_str"
        })
        if resp2.status_code == 200:
            docket = resp2.json()
            cluster_urls = docket.get("clusters", [])
            print(f"  Clusters (opinion groups): {len(cluster_urls)}")
            print(f"  Court: {docket.get('court_id')}")
            print(f"  Filed: {docket.get('date_filed')}")
            print(f"  Terminated: {docket.get('date_terminated')}")
            print(f"  Last filing: {docket.get('date_last_filing')}")
            print(f"  Source bitmask: {docket.get('source')}")
            report["deep_dive_docket"] = docket

        # Count entries + RECAP docs
        for endpoint, key, params in [
            ("docket-entries", "entry_count", {"docket": sample_did, "page_size": 1}),
            ("recap-documents", "recap_available", {"docket_entry__docket": sample_did, "is_available": "true", "page_size": 1}),
            ("recap-documents", "recap_total", {"docket_entry__docket": sample_did, "page_size": 1}),
        ]:
            resp3 = api(f"{BASE}/{endpoint}/", params=params)
            if resp3.status_code == 200:
                cnt = resp3.json().get("count", 0)
                print(f"  {key}: {cnt}")
                report[f"deep_dive_{key}"] = cnt

# ─────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────
section("SUMMARY")

print(f"Total API calls made: {_calls}")
print(f"Report saved to {OUTPUT_DIR}/")
report["total_api_calls"] = _calls
save_json("full_report.json", report)

print("\nDone.")
