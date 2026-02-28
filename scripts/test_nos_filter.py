#!/usr/bin/env python3
"""
Debug: test which NOS filter syntax actually works on each endpoint.
Try multiple formats and compare counts.
"""

import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse

TOKEN = os.environ.get("CL_API_TOKEN", "") or os.environ.get("COURTLISTENER_TOKEN", "")
BASE = "https://www.courtlistener.com/api/rest/v4"

if not TOKEN:
    print("FATAL: No token")
    sys.exit(1)


def api(url, params=None):
    if params:
        qs = urllib.parse.urlencode(params)
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{qs}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Token {TOKEN}",
        "User-Agent": "Ameen-NOSDebug/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as e:
        return None, e.code
    except Exception as e:
        return None, str(e)


results = {}

# ============================================================
print("=" * 60)
print("  TEST 1: Search API NOS filtering (type=r)")
print("=" * 60)

tests_r = [
    ("No filter", {"type": "r"}),
    ("suitNature=880 (GET param)", {"type": "r", "suitNature": "880"}),
    ("q=suitNature:880", {"type": "r", "q": "suitNature:880"}),
    ("q=suitNature:\"880\"", {"type": "r", "q": 'suitNature:"880"'}),
    ("q=suitNature:\"Trade Secret\"", {"type": "r", "q": 'suitNature:"Trade Secret"'}),
    ("suitNature=880 + available_only", {"type": "r", "suitNature": "880", "available_only": "on"}),
    ("q=suitNature:880 + available_only", {"type": "r", "q": "suitNature:880", "available_only": "on"}),
]

for label, params in tests_r:
    data, err = api(f"{BASE}/search/", params)
    if data:
        count = data.get("count", "?")
        doc_count = data.get("document_count", "?")
        n_results = len(data.get("results", []))
        # Check first result's NOS
        first_nos = ""
        if data.get("results"):
            first_nos = data["results"][0].get("suitNature", "N/A")
        print(f"  {label:45s} count={count:>12} doc_count={doc_count:>12} first_NOS={first_nos}")
        results[f"type=r {label}"] = {"count": count, "doc_count": doc_count, "first_nos": first_nos}
    else:
        print(f"  {label:45s} ERROR: {err}")
        results[f"type=r {label}"] = {"error": str(err)}

# ============================================================
print(f"\n{'='*60}")
print("  TEST 2: Search API NOS filtering (type=o)")
print("=" * 60)

tests_o = [
    ("No filter", {"type": "o"}),
    ("suitNature=880 (GET param)", {"type": "o", "suitNature": "880"}),
    ("q=suitNature:880", {"type": "o", "q": "suitNature:880"}),
    ("suitNature=850 (securities)", {"type": "o", "suitNature": "850"}),
    ("q=suitNature:850", {"type": "o", "q": "suitNature:850"}),
]

for label, params in tests_o:
    data, err = api(f"{BASE}/search/", params)
    if data:
        count = data.get("count", "?")
        n_results = len(data.get("results", []))
        first_nos = ""
        if data.get("results"):
            first_nos = data["results"][0].get("suitNature", "N/A")
        print(f"  {label:45s} count={count:>12} first_NOS={first_nos}")
        results[f"type=o {label}"] = {"count": count, "first_nos": first_nos}
    else:
        print(f"  {label:45s} ERROR: {err}")
        results[f"type=o {label}"] = {"error": str(err)}

# ============================================================
print(f"\n{'='*60}")
print("  TEST 3: Search API NOS filtering (type=d)")
print("=" * 60)

tests_d = [
    ("No filter", {"type": "d"}),
    ("suitNature=880", {"type": "d", "suitNature": "880"}),
    ("q=suitNature:880", {"type": "d", "q": "suitNature:880"}),
    ("suitNature=850", {"type": "d", "suitNature": "850"}),
]

for label, params in tests_d:
    data, err = api(f"{BASE}/search/", params)
    if data:
        count = data.get("count", "?")
        n_results = len(data.get("results", []))
        first_nos = ""
        if data.get("results"):
            first_nos = data["results"][0].get("suitNature", "N/A")
        print(f"  {label:45s} count={count:>12} first_NOS={first_nos}")
        results[f"type=d {label}"] = {"count": count, "first_nos": first_nos}
    else:
        print(f"  {label:45s} ERROR: {err}")

# ============================================================
print(f"\n{'='*60}")
print("  TEST 4: /clusters/ endpoint NOS filtering")
print("=" * 60)

tests_clusters = [
    ("No filter", {}),
    ("nature_of_suit=880", {"nature_of_suit": "880"}),
    ("docket__nature_of_suit=Trade Secret", {"docket__nature_of_suit": "Trade Secret"}),
    ("docket__nature_of_suit=880", {"docket__nature_of_suit": "880"}),
]

for label, extra in tests_clusters:
    params = {"page_size": "1", "fields": "id,docket"}
    params.update(extra)
    data, err = api(f"{BASE}/clusters/", params)
    if data:
        count = data.get("count", "?")
        print(f"  {label:45s} count={count}")
        results[f"clusters {label}"] = {"count": count}
    else:
        print(f"  {label:45s} ERROR: {err}")
        results[f"clusters {label}"] = {"error": str(err)}

# ============================================================
print(f"\n{'='*60}")
print("  TEST 5: /dockets/ NOS filter")
print("=" * 60)

tests_dockets = [
    ("No filter", {}),
    ("nature_of_suit=Trade Secret", {"nature_of_suit": "Trade Secret"}),
    ("nature_of_suit=880", {"nature_of_suit": "880"}),
    ("nature_of_suit__startswith=880", {"nature_of_suit__startswith": "880"}),
    ("nature_of_suit__contains=Trade Secret", {"nature_of_suit__contains": "Trade Secret"}),
]

for label, extra in tests_dockets:
    params = {"page_size": "1", "fields": "id,nature_of_suit"}
    params.update(extra)
    data, err = api(f"{BASE}/dockets/", params)
    if data:
        count = data.get("count", "?")
        first_nos = ""
        if data.get("results"):
            first_nos = data["results"][0].get("nature_of_suit", "N/A")
        print(f"  {label:45s} count={count} first_NOS={first_nos}")
        results[f"dockets {label}"] = {"count": count, "first_nos": first_nos}
    else:
        print(f"  {label:45s} ERROR: {err}")
        results[f"dockets {label}"] = {"error": str(err)}

# ============================================================
print(f"\n{'='*60}")
print("  TEST 6: Known docket check")
print("  Docket 14213759 should have opinions + RECAP for trade_secret")
print("=" * 60)

# Check this docket directly
data, err = api(f"{BASE}/dockets/14213759/", {"fields": "id,nature_of_suit,case_name"})
if data:
    print(f"  Docket: {json.dumps(data, indent=2)}")

# Search for it
data, err = api(f"{BASE}/search/", {"type": "r", "q": "docket_id:14213759"})
if data:
    print(f"  Search type=r: count={data.get('count')}, doc_count={data.get('document_count')}")
    for r in data.get("results", []):
        print(f"    suitNature={r.get('suitNature')}, caseName={r.get('caseName','')[:50]}")

data, err = api(f"{BASE}/search/", {"type": "o", "q": "docket_id:14213759"})
if data:
    print(f"  Search type=o: count={data.get('count')}")

# Save
os.makedirs("research", exist_ok=True)
with open("research/nos_filter_debug.json", "w") as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nSaved to research/nos_filter_debug.json")
