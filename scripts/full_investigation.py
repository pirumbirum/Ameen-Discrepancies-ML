#!/usr/bin/env python3
"""
Comprehensive CourtListener investigation: API + website scraping.
Runs on GitHub Actions. Produces detailed JSON artifacts in research/.

Phase 1: Scrape all CourtListener documentation pages (HTML -> text)
Phase 2: OPTIONS discovery on every API endpoint (filters, fields, ordering)
Phase 3: Global counts across the platform
Phase 4: Per-NOS search counts (type=d, type=r, type=rd, type=o)
Phase 5: Per-NOS RECAP availability with available_only filter
Phase 6: Golden set RECAP audit (every docket in golden_set/)
Phase 7: Deep dive into data-rich dockets (entries, documents, page counts)
Phase 8: Docket source bitmask analysis
Phase 9: Sample RECAP document fields and content
Phase 10: Opinions + citations landscape per NOS
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime

CL_API = "https://www.courtlistener.com/api/rest/v4"
CL_WEB = "https://www.courtlistener.com"
GOLDEN_DIR = "golden_set"
CASES_DIR = "cases2/metadata"
OUTPUT_DIR = "research"
DOCS_DIR = "research/api_docs"
TIMESTAMP = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

_calls = 0
_errors = 0


def api(path_or_url, token, params=None, method="GET", retries=3, backoff=2):
    """Make an API call with retry logic and rate-limit handling."""
    global _calls, _errors
    _calls += 1

    if path_or_url.startswith("http"):
        url = path_or_url
    else:
        url = f"{CL_API}/{path_or_url.lstrip('/')}"

    if params:
        qs = urllib.parse.urlencode(params)
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{qs}"

    headers = {
        "Authorization": f"Token {token}",
        "User-Agent": "Ameen-FullInvestigation/1.0",
    }

    for attempt in range(retries):
        try:
            if method == "OPTIONS":
                req = urllib.request.Request(url, headers=headers, method="OPTIONS")
            else:
                req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw), None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = backoff * (2 ** attempt)
                print(f"  RATE LIMITED on {url}, waiting {wait}s...")
                time.sleep(wait)
            elif e.code == 404:
                return None, "404"
            elif e.code == 403:
                _errors += 1
                return None, "403_FORBIDDEN"
            else:
                _errors += 1
                body = ""
                try:
                    body = e.read().decode()[:200]
                except Exception:
                    pass
                print(f"  HTTP {e.code} on {url}: {body}")
                time.sleep(backoff * (2 ** attempt))
        except Exception as e:
            _errors += 1
            print(f"  Error on {url}: {e}")
            time.sleep(backoff * (2 ** attempt))

    return None, "MAX_RETRIES"


def fetch_page(url, filename):
    """Fetch a web page and save it."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Ameen-Research/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        path = os.path.join(DOCS_DIR, filename)
        with open(path, "w") as f:
            f.write(html)
        print(f"  OK {url} -> {path} ({len(html):,} bytes)")
        return html
    except Exception as e:
        print(f"  FAIL {url}: {e}")
        return None


def extract_text(html):
    """Simple text extraction from HTML."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        main = soup.find("main") or soup.find("article") or soup.find("div", class_="content") or soup.body
        if main:
            return main.get_text(separator="\n", strip=True)
    except ImportError:
        pass
    # Fallback: strip tags manually
    import re
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def save(name, data):
    """Save JSON data to research/ directory."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, name)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  -> Saved {path}")
    return path


def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def load_golden_set_ids():
    """Load all docket IDs from golden_set, grouped by category."""
    categories = {}
    if not os.path.isdir(GOLDEN_DIR):
        print(f"  WARNING: {GOLDEN_DIR} not found")
        return categories
    for cat in sorted(os.listdir(GOLDEN_DIR)):
        cat_dir = os.path.join(GOLDEN_DIR, cat)
        if not os.path.isdir(cat_dir) or cat.endswith(".json"):
            continue
        ids = []
        for case_folder in sorted(os.listdir(cat_dir)):
            docket_path = os.path.join(cat_dir, case_folder, "docket.json")
            if os.path.isfile(docket_path):
                try:
                    with open(docket_path) as f:
                        d = json.load(f)
                    did = str(d.get("id", ""))
                    if did:
                        ids.append({
                            "docket_id": did,
                            "case_name": d.get("case_name", ""),
                            "folder": case_folder,
                        })
                except Exception:
                    pass
        if ids:
            categories[cat] = ids
    return categories


def load_cases2_ids():
    """Load docket IDs from cases2/metadata/ JSONs."""
    categories = {}
    if not os.path.isdir(CASES_DIR):
        print(f"  WARNING: {CASES_DIR} not found")
        return categories
    for fn in sorted(os.listdir(CASES_DIR)):
        if not fn.endswith(".json"):
            continue
        cat = fn.replace(".json", "")
        path = os.path.join(CASES_DIR, fn)
        try:
            with open(path) as f:
                cases = json.load(f)
            categories[cat] = len(cases)
        except Exception:
            pass
    return categories


def main():
    token = os.environ.get("CL_API_TOKEN", "") or os.environ.get("COURTLISTENER_TOKEN", "")
    if not token:
        print("FATAL: No API token. Set CL_API_TOKEN or COURTLISTENER_TOKEN env var.")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(DOCS_DIR, exist_ok=True)

    # Quick auth test
    test_data, err = api("courts/", token, params={"page_size": "1", "format": "json"})
    if err:
        print(f"FATAL: API test failed: {err}")
        sys.exit(1)
    print(f"API connection OK (courts count: {test_data.get('count', '?')})\n")

    report = {"timestamp": TIMESTAMP, "phases": {}}

    # ═══════════════════════════════════════════════════════════
    # PHASE 1: Scrape all CourtListener documentation
    # ═══════════════════════════════════════════════════════════
    section("PHASE 1: Scrape CourtListener documentation")

    pages = [
        # API docs
        (f"{CL_WEB}/help/api/", "api_overview.html"),
        (f"{CL_WEB}/help/api/rest/", "rest_overview.html"),
        (f"{CL_WEB}/help/api/rest/case-law/", "case_law.html"),
        (f"{CL_WEB}/help/api/rest/pacer/", "pacer.html"),
        (f"{CL_WEB}/help/api/rest/search/", "search.html"),
        (f"{CL_WEB}/help/api/rest/citations/", "citations.html"),
        (f"{CL_WEB}/help/api/rest/judges/", "judges.html"),
        (f"{CL_WEB}/help/api/rest/financial-disclosures/", "financial_disclosures.html"),
        (f"{CL_WEB}/help/api/rest/visualizations/", "visualizations.html"),
        (f"{CL_WEB}/help/api/rest/fields/", "fields.html"),
        (f"{CL_WEB}/help/api/rest/recap/", "recap_api.html"),
        (f"{CL_WEB}/help/api/rest/permissions/", "permissions.html"),
        (f"{CL_WEB}/help/api/rest/changes/", "api_changes.html"),
        (f"{CL_WEB}/help/api/rest/alerts/", "alerts.html"),
        (f"{CL_WEB}/help/api/rest/webhooks/", "webhooks.html"),
        # Bulk data & replication
        (f"{CL_WEB}/help/api/bulk-data/", "bulk_data.html"),
        (f"{CL_WEB}/help/api/replication/", "replication.html"),
        # Coverage
        (f"{CL_WEB}/help/coverage/", "coverage.html"),
        (f"{CL_WEB}/help/coverage/recap/", "recap_coverage.html"),
        (f"{CL_WEB}/help/coverage/opinions/", "opinion_coverage.html"),
        (f"{CL_WEB}/help/coverage/financial-disclosures/", "fd_coverage.html"),
        (f"{CL_WEB}/help/coverage/oral-arguments/", "oa_coverage.html"),
        # Help pages
        (f"{CL_WEB}/help/", "help_main.html"),
        (f"{CL_WEB}/help/recap/", "help_recap.html"),
        (f"{CL_WEB}/help/recap/what-is-pacer/", "what_is_pacer.html"),
        (f"{CL_WEB}/help/search-operators/", "search_operators.html"),
        # About
        (f"{CL_WEB}/about/", "about.html"),
        (f"{CL_WEB}/faq/", "faq.html"),
        (f"{CL_WEB}/terms/", "terms.html"),
        # RECAP specific
        (f"{CL_WEB}/recap/", "recap_main.html"),
        # V4 migration
        (f"{CL_WEB}/help/api/rest/v4/migration-guide/", "v4_migration.html"),
        # Blog posts
        ("https://free.law/recap/", "freelaw_recap.html"),
        ("https://free.law/projects/recap/", "freelaw_recap_project.html"),
    ]

    scraped = 0
    for url, filename in pages:
        html = fetch_page(url, filename)
        if html:
            scraped += 1
            # Extract text version
            text = extract_text(html)
            txt_path = os.path.join(DOCS_DIR, filename.replace(".html", ".txt"))
            with open(txt_path, "w") as f:
                f.write(text)
        time.sleep(0.3)

    report["phases"]["1_scraping"] = {"pages_attempted": len(pages), "pages_scraped": scraped}
    print(f"\n  Scraped {scraped}/{len(pages)} pages")

    # ═══════════════════════════════════════════════════════════
    # PHASE 2: OPTIONS discovery on every endpoint
    # ═══════════════════════════════════════════════════════════
    section("PHASE 2: OPTIONS discovery on all API endpoints")

    # First get the API root to discover all endpoints
    root_data, err = api("", token, params={"format": "json"})
    if root_data:
        save("api_v4_root.json", root_data)
        print(f"  API root has {len(root_data)} endpoints:")
        for name in sorted(root_data.keys()):
            print(f"    {name}")
    else:
        print(f"  API root failed: {err}")
        root_data = {}

    endpoints = [
        "recap-documents", "docket-entries", "dockets", "clusters",
        "opinions", "search", "parties", "attorneys", "courts",
        "citation-lookup", "people", "positions", "schools",
        "financial-disclosures", "audio", "recap",
        "recap-email", "recap-fetch", "recap-query",
        "tags", "fjc-integrated-database",
    ]

    options_report = {}
    for ep in endpoints:
        data, err = api(f"{ep}/", token, method="OPTIONS")
        if data:
            filters = list(data.get("filters", {}).keys()) if "filters" in data else []
            fields = list(data.get("fields", {}).keys()) if "fields" in data else []
            ordering = data.get("ordering", [])
            actions = list(data.get("actions", {}).keys()) if "actions" in data else []
            info = {
                "filters": filters, "filter_count": len(filters),
                "fields": fields, "field_count": len(fields),
                "ordering": ordering, "actions": actions,
            }
            options_report[ep] = info
            save(f"options_{ep.replace('-','_')}.json", data)
            print(f"  {ep:30s}: {len(filters)} filters, {len(fields)} fields, {len(ordering)} orderings")
        else:
            options_report[ep] = {"error": str(err)}
            print(f"  {ep:30s}: ERROR {err}")
        time.sleep(0.2)

    report["phases"]["2_options"] = options_report

    # ═══════════════════════════════════════════════════════════
    # PHASE 3: Global counts
    # ═══════════════════════════════════════════════════════════
    section("PHASE 3: Global platform counts")

    count_queries = [
        ("All dockets", "dockets/", {}),
        ("Federal district dockets", "dockets/", {"court__jurisdiction": "FD"}),
        ("Federal appellate dockets", "dockets/", {"court__jurisdiction": "F"}),
        ("All docket entries", "docket-entries/", {}),
        ("All RECAP docs", "recap-documents/", {}),
        ("Available RECAP docs", "recap-documents/", {"is_available": "true"}),
        ("Unavailable RECAP docs", "recap-documents/", {"is_available": "false"}),
        ("Main RECAP docs (type=1)", "recap-documents/", {"document_type": "1"}),
        ("Attachment RECAP docs (type=2)", "recap-documents/", {"document_type": "2"}),
        ("Free-on-PACER docs", "recap-documents/", {"is_free_on_pacer": "true"}),
        ("All opinion clusters", "clusters/", {}),
        ("All opinions", "opinions/", {}),
        ("All courts", "courts/", {}),
        ("All parties", "parties/", {}),
        ("All attorneys", "attorneys/", {}),
        ("All people (judges)", "people/", {}),
        ("All audio (oral args)", "audio/", {}),
        ("All financial disclosures", "financial-disclosures/", {}),
        ("FJC IDB records", "fjc-integrated-database/", {}),
    ]

    global_counts = {}
    for label, endpoint, params in count_queries:
        p = dict(params)
        p["page_size"] = "1"
        p["format"] = "json"
        data, err = api(endpoint, token, params=p)
        if data:
            count = data.get("count", "N/A")
            global_counts[label] = count
            if isinstance(count, int):
                print(f"  {label:40s}: {count:>15,}")
            else:
                print(f"  {label:40s}: {count}")
        else:
            global_counts[label] = f"ERROR: {err}"
            print(f"  {label:40s}: ERROR {err}")
        time.sleep(0.2)

    report["phases"]["3_global_counts"] = global_counts
    save("global_counts.json", global_counts)

    # ═══════════════════════════════════════════════════════════
    # PHASE 4: Per-NOS search counts
    # ═══════════════════════════════════════════════════════════
    section("PHASE 4: Per-NOS search counts (type=d, r, rd)")

    NOS_CODES = {
        "securities": "850", "patent": "830", "trademark": "840",
        "antitrust": "410", "stockholders": "160", "rico": "470",
        "trade_secret": "880", "insurance": "110", "other_contract": "190",
        "banks": "430", "environmental": "893",
    }

    nos_counts = {}
    for cat, nos in sorted(NOS_CODES.items()):
        row = {"nos_code": nos}

        # type=d: docket count
        data, _ = api("search/", token, params={"type": "d", "suitNature": nos})
        if data:
            row["dockets_total"] = data.get("count", 0)

        # type=r: dockets with RECAP (any)
        data, _ = api("search/", token, params={"type": "r", "suitNature": nos})
        if data:
            row["dockets_with_recap"] = data.get("count", 0)
            row["recap_doc_count"] = data.get("document_count", 0)

        # type=r with available_only: dockets with downloadable RECAP PDFs
        data, _ = api("search/", token, params={
            "type": "r", "suitNature": nos, "available_only": "on"
        })
        if data:
            row["dockets_with_available_recap"] = data.get("count", 0)
            row["available_doc_count"] = data.get("document_count", 0)

        # type=rd: flat RECAP doc count
        data, _ = api("search/", token, params={"type": "rd", "suitNature": nos})
        if data:
            row["recap_docs_flat"] = data.get("count", 0)

        # type=o: opinion count
        data, _ = api("search/", token, params={"type": "o", "suitNature": nos})
        if data:
            row["opinions"] = data.get("count", 0)

        nos_counts[cat] = row
        print(f"  {cat:20s} (NOS {nos}): "
              f"dockets={row.get('dockets_total','?'):>8}  "
              f"recap_dockets={row.get('dockets_with_recap','?'):>8}  "
              f"avail_recap={row.get('dockets_with_available_recap','?'):>8}  "
              f"docs={row.get('recap_doc_count','?'):>8}  "
              f"opinions={row.get('opinions','?'):>8}")
        time.sleep(0.3)

    report["phases"]["4_nos_counts"] = nos_counts
    save("nos_search_counts.json", nos_counts)

    # ═══════════════════════════════════════════════════════════
    # PHASE 5: Top dockets per NOS with RECAP data
    # ═══════════════════════════════════════════════════════════
    section("PHASE 5: Sample data-rich dockets per NOS")

    nos_samples = {}
    for cat, nos in sorted(NOS_CODES.items()):
        # Get first page of dockets with available RECAP
        data, _ = api("search/", token, params={
            "type": "r", "suitNature": nos, "available_only": "on",
            "order_by": "dateFiled desc",
        })
        if data and data.get("results"):
            samples = []
            for r in data["results"][:5]:
                sample = {
                    "docket_id": r.get("docket_id"),
                    "caseName": r.get("caseName", "")[:80],
                    "docketNumber": r.get("docketNumber", ""),
                    "court_id": r.get("court_id", ""),
                    "dateFiled": r.get("dateFiled", ""),
                    "dateTerminated": r.get("dateTerminated", ""),
                    "assignedTo": r.get("assignedTo", ""),
                    "suitNature": r.get("suitNature", ""),
                    "recap_docs_nested": len(r.get("recap_documents", [])),
                    "more_docs": r.get("more_docs", False),
                }
                # If there are nested docs, get their details
                nested_docs = []
                for doc in r.get("recap_documents", []):
                    nested_docs.append({
                        "id": doc.get("id"),
                        "short_description": doc.get("short_description", "")[:60],
                        "document_number": doc.get("document_number"),
                        "page_count": doc.get("page_count"),
                        "is_available": doc.get("is_available"),
                        "entry_date_filed": doc.get("entry_date_filed"),
                    })
                sample["nested_recap_docs"] = nested_docs
                samples.append(sample)

            nos_samples[cat] = samples
            print(f"  {cat:20s}: {len(samples)} sample dockets")
            for s in samples[:2]:
                print(f"    {s['docket_id']} — {s['caseName'][:50]} "
                      f"(nested docs: {s['recap_docs_nested']}, more: {s['more_docs']})")
        time.sleep(0.3)

    report["phases"]["5_nos_samples"] = nos_samples
    save("nos_recap_samples.json", nos_samples)

    # ═══════════════════════════════════════════════════════════
    # PHASE 6: Golden set RECAP audit
    # ═══════════════════════════════════════════════════════════
    section("PHASE 6: Golden set RECAP audit")

    golden = load_golden_set_ids()
    print(f"  Loaded {sum(len(v) for v in golden.values())} docket IDs across {len(golden)} categories\n")

    recap_audit = {}
    grand_total = 0
    grand_has_recap = 0
    grand_has_available = 0
    grand_has_entries = 0
    grand_has_clusters = 0
    grand_has_both = 0

    for cat, cases in sorted(golden.items()):
        cat_results = []
        has_recap = 0
        has_available = 0
        has_entries = 0
        has_clusters_cat = 0
        has_both = 0

        for j, case in enumerate(cases):
            did = case["docket_id"]
            grand_total += 1

            # Count ALL RECAP docs
            data, _ = api("recap-documents/", token, params={
                "docket_entry__docket": did, "page_size": "1", "format": "json"
            })
            recap_total = data.get("count", 0) if data else 0
            if not isinstance(recap_total, int):
                recap_total = 0

            # Count available RECAP docs
            data, _ = api("recap-documents/", token, params={
                "docket_entry__docket": did, "is_available": "true",
                "page_size": "1", "format": "json"
            })
            recap_avail = data.get("count", 0) if data else 0
            if not isinstance(recap_avail, int):
                recap_avail = 0

            # Count docket entries
            data, _ = api("docket-entries/", token, params={
                "docket": did, "page_size": "1", "format": "json"
            })
            entry_count = data.get("count", 0) if data else 0
            if not isinstance(entry_count, int):
                entry_count = 0

            # Count opinion clusters
            data, _ = api("clusters/", token, params={
                "docket": did, "page_size": "1", "format": "json"
            })
            cluster_count = data.get("count", 0) if data else 0
            if not isinstance(cluster_count, int):
                cluster_count = 0

            result = {
                "docket_id": did,
                "case_name": case["case_name"][:80],
                "recap_total": recap_total,
                "recap_available": recap_avail,
                "entry_count": entry_count,
                "cluster_count": cluster_count,
            }
            cat_results.append(result)

            if recap_total > 0:
                has_recap += 1
                grand_has_recap += 1
            if recap_avail > 0:
                has_available += 1
                grand_has_available += 1
            if entry_count > 0:
                has_entries += 1
                grand_has_entries += 1
            if cluster_count > 0:
                has_clusters_cat += 1
                grand_has_clusters += 1
            if recap_avail > 0 and cluster_count > 0:
                has_both += 1
                grand_has_both += 1

            if (j + 1) % 10 == 0:
                print(f"    [{cat}] {j+1}/{len(cases)} checked, API calls so far: {_calls}")
                sys.stdout.flush()
            time.sleep(0.15)

        n = max(len(cat_results), 1)
        avg_recap = sum(r["recap_total"] for r in cat_results) / n
        avg_avail = sum(r["recap_available"] for r in cat_results) / n
        avg_entries = sum(r["entry_count"] for r in cat_results) / n
        max_recap = max((r["recap_available"] for r in cat_results), default=0)

        recap_audit[cat] = {
            "total_cases": len(cases),
            "has_any_recap": has_recap,
            "has_available_recap": has_available,
            "has_entries": has_entries,
            "has_clusters": has_clusters_cat,
            "has_opinions_and_recap": has_both,
            "avg_recap_total": round(avg_recap, 1),
            "avg_recap_available": round(avg_avail, 1),
            "avg_entry_count": round(avg_entries, 1),
            "max_recap_available": max_recap,
            "cases": cat_results,
        }

        print(f"\n  {cat:20s}: {has_recap:>3}/{len(cases)} RECAP, "
              f"{has_available:>3}/{len(cases)} available, "
              f"{has_entries:>3}/{len(cases)} entries, "
              f"{has_clusters_cat:>3}/{len(cases)} opinions, "
              f"{has_both:>3}/{len(cases)} BOTH")
        print(f"  {'':20s}  avg: recap={avg_recap:.1f}, avail={avg_avail:.1f}, "
              f"entries={avg_entries:.1f}, max_avail={max_recap}\n")

    report["phases"]["6_golden_audit"] = {
        "grand_total": grand_total,
        "grand_has_recap": grand_has_recap,
        "grand_has_available": grand_has_available,
        "grand_has_entries": grand_has_entries,
        "grand_has_clusters": grand_has_clusters,
        "grand_has_both": grand_has_both,
        "per_category": {k: {kk: vv for kk, vv in v.items() if kk != "cases"}
                        for k, v in recap_audit.items()},
    }
    save("golden_set_recap_audit.json", recap_audit)

    # ═══════════════════════════════════════════════════════════
    # PHASE 7: Deep dive into data-rich dockets
    # ═══════════════════════════════════════════════════════════
    section("PHASE 7: Deep dive into richest RECAP dockets")

    deep_dives = {}
    for cat, audit in sorted(recap_audit.items()):
        ranked = sorted(audit["cases"], key=lambda x: x["recap_available"], reverse=True)
        top3 = [r for r in ranked[:3] if r["recap_available"] > 0]

        for docket in top3:
            did = docket["docket_id"]
            print(f"  Deep diving {cat}/{did} ({docket['case_name'][:40]})...")

            dive = dict(docket)

            # Get full docket metadata
            data, _ = api(f"dockets/{did}/", token, params={
                "format": "json",
                "fields": "id,case_name,date_filed,date_terminated,date_last_filing,"
                          "nature_of_suit,court_id,source,slug,docket_number,"
                          "assigned_to_str,referred_to_str,cause,jury_demand,"
                          "jurisdiction_type,date_argued,date_reargued,"
                          "date_reargument_denied,date_cert_granted,date_cert_denied"
            })
            if data:
                dive["full_docket"] = data
                print(f"    Court: {data.get('court_id')}, Filed: {data.get('date_filed')}, "
                      f"Source: {data.get('source')}")

            # Get first 5 available RECAP docs with details
            data, _ = api("recap-documents/", token, params={
                "docket_entry__docket": did,
                "is_available": "true",
                "page_size": "5",
                "fields": "id,document_type,document_number,attachment_number,"
                          "description,page_count,file_size,is_available,"
                          "date_upload,pacer_doc_id,ocr_status",
                "order_by": "document_number",
                "format": "json",
            })
            if data:
                dive["sample_recap_docs"] = data.get("results", [])
                total_pages = sum(d.get("page_count") or 0 for d in data.get("results", []))
                print(f"    Sample docs: {len(data.get('results',[]))} "
                      f"(total pages in sample: {total_pages})")

            # Get first 5 docket entries
            data, _ = api("docket-entries/", token, params={
                "docket": did,
                "page_size": "5",
                "omit": "recap_documents__plain_text",
                "order_by": "entry_number",
                "format": "json",
            })
            if data:
                entries = data.get("results", [])
                dive["sample_entries"] = []
                for e in entries:
                    entry_info = {
                        "entry_number": e.get("entry_number"),
                        "description": e.get("description", "")[:200],
                        "date_filed": e.get("date_filed"),
                        "recap_doc_count": len(e.get("recap_documents", [])),
                        "recap_docs": [{
                            "id": d.get("id"),
                            "document_type": d.get("document_type"),
                            "is_available": d.get("is_available"),
                            "page_count": d.get("page_count"),
                            "description": d.get("description", "")[:100],
                        } for d in e.get("recap_documents", [])],
                    }
                    dive["sample_entries"].append(entry_info)
                print(f"    Sample entries: {len(entries)}")

            # Check for opinion clusters
            data, _ = api("clusters/", token, params={
                "docket": did, "page_size": "5", "format": "json",
                "fields": "id,case_name,date_filed,citation_count,precedential_status,"
                          "nature_of_suit,source,judges",
            })
            if data:
                dive["clusters"] = data.get("results", [])
                print(f"    Clusters: {data.get('count', 0)}")

            deep_dives[f"{cat}_{did}"] = dive
            time.sleep(0.2)

    report["phases"]["7_deep_dives"] = {k: {"docket_id": v["docket_id"], "case_name": v["case_name"]}
                                         for k, v in deep_dives.items()}
    save("deep_dives.json", deep_dives)

    # ═══════════════════════════════════════════════════════════
    # PHASE 8: Docket source bitmask analysis
    # ═══════════════════════════════════════════════════════════
    section("PHASE 8: Docket source bitmask analysis")

    source_analysis = {}

    # Analyze sources across golden set
    for cat, cases in sorted(golden.items()):
        source_counts = {}
        for case in cases[:20]:
            did = case["docket_id"]
            data, _ = api(f"dockets/{did}/", token, params={
                "format": "json", "fields": "id,source"
            })
            if data:
                src = data.get("source", "unknown")
                src_str = str(src)
                source_counts[src_str] = source_counts.get(src_str, 0) + 1
            time.sleep(0.1)

        source_analysis[cat] = source_counts
        print(f"  {cat:20s}: {dict(sorted(source_counts.items(), key=lambda x: -x[1]))}")

    report["phases"]["8_source_bitmask"] = source_analysis
    save("source_bitmask_analysis.json", source_analysis)

    # ═══════════════════════════════════════════════════════════
    # PHASE 9: Sample RECAP document full field dump
    # ═══════════════════════════════════════════════════════════
    section("PHASE 9: Sample RECAP document field dump")

    # Find a docket with lots of RECAP docs
    data, _ = api("search/", token, params={
        "type": "r", "suitNature": "850", "available_only": "on",
        "order_by": "dateFiled desc",
    })
    if data and data.get("results"):
        sample_did = data["results"][0].get("docket_id")
        print(f"  Sampling docket {sample_did}...")

        # Get full field dump (no field restriction)
        docs_data, _ = api("recap-documents/", token, params={
            "docket_entry__docket": str(sample_did),
            "is_available": "true",
            "page_size": "3",
            "omit": "plain_text",
            "format": "json",
        })
        if docs_data and docs_data.get("results"):
            for doc in docs_data["results"]:
                print(f"\n  Document {doc.get('id')} fields:")
                for k, v in sorted(doc.items()):
                    val_str = str(v)[:100]
                    print(f"    {k:35s} = {val_str}")
            save("sample_recap_docs_full.json", docs_data["results"])
            report["phases"]["9_sample_fields"] = {
                "fields": sorted(docs_data["results"][0].keys()),
                "field_count": len(docs_data["results"][0]),
                "sample_count": len(docs_data["results"]),
            }

    # ═══════════════════════════════════════════════════════════
    # PHASE 10: Opinion + Citation landscape
    # ═══════════════════════════════════════════════════════════
    section("PHASE 10: Opinion + citation landscape per NOS")

    opinion_landscape = {}
    for cat, nos in sorted(NOS_CODES.items()):
        # Search opinions by NOS
        data, _ = api("search/", token, params={
            "type": "o", "suitNature": nos,
            "order_by": "dateFiled desc",
        })
        if data:
            count = data.get("count", 0)
            results = data.get("results", [])
            samples = []
            for r in results[:3]:
                samples.append({
                    "cluster_id": r.get("cluster_id"),
                    "caseName": r.get("caseName", "")[:60],
                    "dateFiled": r.get("dateFiled"),
                    "citation_count": r.get("citation_count", 0),
                    "court_id": r.get("court_id"),
                    "status": r.get("status"),
                    "suitNature": r.get("suitNature"),
                })
            opinion_landscape[cat] = {"count": count, "samples": samples}
            print(f"  {cat:20s}: {count:>8,} opinions")
        time.sleep(0.3)

    report["phases"]["10_opinions"] = opinion_landscape
    save("opinion_landscape.json", opinion_landscape)

    # ═══════════════════════════════════════════════════════════
    # FINAL SUMMARY
    # ═══════════════════════════════════════════════════════════
    section("FINAL SUMMARY")

    print(f"Total API calls: {_calls}")
    print(f"Total errors: {_errors}")

    print(f"\nGlobal Platform Counts:")
    for label, count in global_counts.items():
        if isinstance(count, int):
            print(f"  {label:40s}: {count:>15,}")
        else:
            print(f"  {label:40s}: {count}")

    print(f"\nPer-NOS Breakdown:")
    print(f"  {'Category':20s} {'Dockets':>10} {'RECAP':>10} {'Available':>10} {'Opinions':>10}")
    print(f"  {'-'*20} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
    for cat, row in sorted(nos_counts.items()):
        print(f"  {cat:20s} "
              f"{row.get('dockets_total','?'):>10} "
              f"{row.get('dockets_with_recap','?'):>10} "
              f"{row.get('dockets_with_available_recap','?'):>10} "
              f"{row.get('opinions','?'):>10}")

    print(f"\nGolden Set RECAP Audit:")
    print(f"  Total cases checked: {grand_total}")
    print(f"  Cases with ANY RECAP docs: {grand_has_recap} ({grand_has_recap/max(grand_total,1)*100:.0f}%)")
    print(f"  Cases with AVAILABLE RECAP: {grand_has_available} ({grand_has_available/max(grand_total,1)*100:.0f}%)")
    print(f"  Cases with docket entries: {grand_has_entries} ({grand_has_entries/max(grand_total,1)*100:.0f}%)")
    print(f"  Cases with opinion clusters: {grand_has_clusters} ({grand_has_clusters/max(grand_total,1)*100:.0f}%)")
    print(f"  Cases with BOTH opinions+RECAP: {grand_has_both} ({grand_has_both/max(grand_total,1)*100:.0f}%)")

    print(f"\nTop RECAP-rich dockets in golden_set:")
    for cat, audit in sorted(recap_audit.items()):
        top = sorted(audit["cases"], key=lambda x: x["recap_available"], reverse=True)[0]
        if top["recap_available"] > 0:
            print(f"  {cat:20s}: docket {top['docket_id']} has {top['recap_available']} available docs "
                  f"— {top['case_name'][:40]}")

    report["api_calls"] = _calls
    report["errors"] = _errors
    save("full_investigation_report.json", report)
    print(f"\nAll results saved to {OUTPUT_DIR}/")
    print("INVESTIGATION COMPLETE.")


if __name__ == "__main__":
    main()
