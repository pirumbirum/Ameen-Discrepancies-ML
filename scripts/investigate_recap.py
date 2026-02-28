#!/usr/bin/env python3
"""
Investigation script: Thoroughly explore CourtListener RECAP data capabilities.
Runs on GitHub Actions. Outputs detailed report to stdout + JSON artifacts.

Goals:
  1. Discover all filters/fields on recap-documents, docket-entries endpoints
  2. Measure RECAP availability across our golden_set docket IDs
  3. Test search API type=r, type=rd, type=d for each NOS category
  4. Find the overlap: cases with BOTH opinions AND RECAP docs
  5. Output actionable data for building a blended scoring strategy
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error

CL_API = "https://www.courtlistener.com/api/rest/v4"
GOLDEN_DIR = "golden_set"
OUTPUT_DIR = "research"

_calls = 0


def api(url, token, method="GET", retries=3, backoff=2):
    global _calls
    _calls += 1
    headers = {
        "Authorization": f"Token {token}",
        "User-Agent": "Ameen-Investigate/1.0",
    }
    for attempt in range(retries):
        try:
            if method == "OPTIONS":
                req = urllib.request.Request(url, headers=headers, method="OPTIONS")
            else:
                req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode()), None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = backoff * (2 ** attempt)
                print(f"  RATE LIMITED, waiting {wait}s...")
                time.sleep(wait)
            elif e.code == 404:
                return None, "404"
            else:
                print(f"  HTTP {e.code}, retry {attempt+1}/{retries}")
                time.sleep(backoff * (2 ** attempt))
        except Exception as e:
            print(f"  Error: {e}, retry {attempt+1}/{retries}")
            time.sleep(backoff * (2 ** attempt))
    return None, "MAX_RETRIES"


def save(name, data):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, name)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  -> Saved {path}")


def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def load_golden_set_ids():
    """Load all docket IDs from golden_set, grouped by category."""
    categories = {}
    for cat in sorted(os.listdir(GOLDEN_DIR)):
        cat_dir = os.path.join(GOLDEN_DIR, cat)
        if not os.path.isdir(cat_dir) or cat.endswith(".json"):
            continue
        ids = []
        for case_folder in sorted(os.listdir(cat_dir)):
            docket_path = os.path.join(cat_dir, case_folder, "docket.json")
            if os.path.isfile(docket_path):
                with open(docket_path) as f:
                    d = json.load(f)
                did = str(d.get("id", ""))
                if did:
                    ids.append({
                        "docket_id": did,
                        "case_name": d.get("case_name", ""),
                        "folder": case_folder,
                    })
        categories[cat] = ids
    return categories


def main():
    token = os.environ.get("CL_API_TOKEN", "") or os.environ.get("COURTLISTENER_TOKEN", "")
    if not token:
        print("FATAL: No API token")
        sys.exit(1)

    # Test API
    test, err = api(f"{CL_API}/courts/?format=json&page_size=1", token)
    if err:
        print(f"FATAL: API test failed: {err}")
        sys.exit(1)
    print("API connection OK\n")

    report = {}

    # ─────────────────────────────────────────────────────────
    # 1. OPTIONS on all relevant endpoints
    # ─────────────────────────────────────────────────────────
    section("1. OPTIONS — Discover filters & fields on all endpoints")

    endpoints_to_check = [
        "recap-documents",
        "docket-entries",
        "dockets",
        "clusters",
        "opinions",
        "search",
        "parties",
        "attorneys",
    ]

    for ep in endpoints_to_check:
        url = f"{CL_API}/{ep}/"
        data, err = api(url, token, method="OPTIONS")
        if data:
            filters = list(data.get("filters", {}).keys()) if "filters" in data else []
            fields = list(data.get("fields", {}).keys()) if "fields" in data else []
            ordering = data.get("ordering", [])
            actions = list(data.get("actions", {}).keys()) if "actions" in data else []
            info = {
                "filters": filters,
                "filter_count": len(filters),
                "fields": fields,
                "field_count": len(fields),
                "ordering": ordering,
                "actions": actions,
            }
            report[f"options_{ep}"] = info
            save(f"options_{ep.replace('-','_')}.json", data)
            print(f"  {ep}:")
            print(f"    Filters ({len(filters)}): {filters}")
            print(f"    Fields ({len(fields)}): {fields[:15]}{'...' if len(fields) > 15 else ''}")
            print(f"    Ordering: {ordering}")
        else:
            print(f"  {ep}: ERROR {err}")
        time.sleep(0.2)

    # ─────────────────────────────────────────────────────────
    # 2. Global counts — how much RECAP data exists?
    # ─────────────────────────────────────────────────────────
    section("2. Global RECAP counts")

    count_queries = [
        ("All RECAP docs", "recap-documents", {}),
        ("Available RECAP docs", "recap-documents", {"is_available": "true"}),
        ("All docket entries", "docket-entries", {}),
        ("All dockets", "dockets", {}),
        ("All clusters", "clusters", {}),
        ("All opinions", "opinions", {}),
    ]

    global_counts = {}
    for label, endpoint, params in count_queries:
        p = dict(params)
        p["page_size"] = "1"
        p["format"] = "json"
        qs = "&".join(f"{k}={v}" for k, v in p.items())
        data, err = api(f"{CL_API}/{endpoint}/?{qs}", token)
        if data:
            count = data.get("count", "N/A")
            global_counts[label] = count
            print(f"  {label}: {count:,}" if isinstance(count, int) else f"  {label}: {count}")
        else:
            print(f"  {label}: ERROR {err}")
        time.sleep(0.2)

    report["global_counts"] = global_counts
    save("global_counts.json", global_counts)

    # ─────────────────────────────────────────────────────────
    # 3. Search API — type=r, type=rd, type=d per NOS code
    # ─────────────────────────────────────────────────────────
    section("3. Search API counts per NOS and search type")

    NOS_CODES = {
        "securities": "850", "patent": "830", "trademark": "840",
        "antitrust": "410", "stockholders": "160", "rico": "470",
        "trade_secret": "880", "insurance": "110", "other_contract": "190",
        "banks": "430", "environmental": "893",
    }

    search_counts = {}
    for cat, nos in sorted(NOS_CODES.items()):
        row = {}
        for stype in ["d", "r", "rd", "o"]:
            params = {"type": stype, "suitNature": nos}
            if stype == "o":
                # opinion search uses different params
                params = {"type": "o"}
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            data, err = api(f"{CL_API}/search/?{qs}", token)
            if data:
                row[f"type_{stype}"] = data.get("count", 0)
            else:
                row[f"type_{stype}"] = f"ERR:{err}"
            time.sleep(0.3)

        search_counts[cat] = row
        print(f"  {cat:20s} (NOS {nos}): "
              f"dockets={row.get('type_d','?'):>8}  "
              f"recap_dockets={row.get('type_r','?'):>8}  "
              f"recap_docs={row.get('type_rd','?'):>8}  "
              f"opinions={row.get('type_o','?'):>8}")

    report["search_counts_by_nos"] = search_counts
    save("search_counts_by_nos.json", search_counts)

    # ─────────────────────────────────────────────────────────
    # 4. RECAP availability for golden_set dockets
    # ─────────────────────────────────────────────────────────
    section("4. RECAP availability for golden_set cases")

    golden = load_golden_set_ids()
    print(f"  Loaded {sum(len(v) for v in golden.values())} docket IDs across {len(golden)} categories\n")

    recap_audit = {}
    grand_total = 0
    grand_has_recap = 0
    grand_has_available = 0
    grand_has_entries = 0
    grand_has_both = 0  # has opinions AND available RECAP docs

    for cat, cases in sorted(golden.items()):
        cat_results = []
        has_recap = 0
        has_available = 0
        has_entries = 0
        has_both = 0

        # Sample: check ALL 100 cases per category (4 API calls each = 400/category)
        for j, case in enumerate(cases):
            did = case["docket_id"]
            grand_total += 1

            # Count RECAP docs (all)
            data, _ = api(f"{CL_API}/recap-documents/?docket_entry__docket={did}&page_size=1&format=json", token)
            recap_total = data.get("count", 0) if data else 0
            if not isinstance(recap_total, int):
                recap_total = 0

            # Count available RECAP docs
            data, _ = api(f"{CL_API}/recap-documents/?docket_entry__docket={did}&is_available=true&page_size=1&format=json", token)
            recap_avail = data.get("count", 0) if data else 0
            if not isinstance(recap_avail, int):
                recap_avail = 0

            # Count docket entries
            data, _ = api(f"{CL_API}/docket-entries/?docket={did}&page_size=1&format=json", token)
            entry_count = data.get("count", 0) if data else 0
            if not isinstance(entry_count, int):
                entry_count = 0

            # Check opinion clusters (from full_docket already downloaded)
            cluster_count = 0
            fd_path = os.path.join(GOLDEN_DIR, cat, case["folder"], "full_docket", "docket_full.json")
            if os.path.isfile(fd_path):
                with open(fd_path) as f:
                    fd = json.load(f)
                cluster_count = len(fd.get("clusters", []))

            result = {
                "docket_id": did,
                "case_name": case["case_name"][:60],
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
            if recap_avail > 0 and cluster_count > 0:
                has_both += 1
                grand_has_both += 1

            if (j + 1) % 20 == 0:
                print(f"    [{cat}] {j+1}/{len(cases)} checked, API calls: {_calls}")
                sys.stdout.flush()
            time.sleep(0.15)

        avg_recap = sum(r["recap_total"] for r in cat_results) / max(len(cat_results), 1)
        avg_avail = sum(r["recap_available"] for r in cat_results) / max(len(cat_results), 1)
        avg_entries = sum(r["entry_count"] for r in cat_results) / max(len(cat_results), 1)

        recap_audit[cat] = {
            "total_cases": len(cases),
            "has_any_recap": has_recap,
            "has_available_recap": has_available,
            "has_entries": has_entries,
            "has_opinions_and_recap": has_both,
            "avg_recap_total": round(avg_recap, 1),
            "avg_recap_available": round(avg_avail, 1),
            "avg_entry_count": round(avg_entries, 1),
            "cases": cat_results,
        }

        print(f"\n  {cat:20s}: {has_recap:>3}/100 have RECAP, "
              f"{has_available:>3}/100 have available docs, "
              f"{has_entries:>3}/100 have entries, "
              f"{has_both:>3}/100 have BOTH opinions+RECAP")
        print(f"  {'':20s}  avg: {avg_recap:.1f} recap, {avg_avail:.1f} available, "
              f"{avg_entries:.1f} entries\n")

    report["golden_set_recap_audit"] = {
        "grand_total": grand_total,
        "grand_has_recap": grand_has_recap,
        "grand_has_available": grand_has_available,
        "grand_has_entries": grand_has_entries,
        "grand_has_both_opinions_and_recap": grand_has_both,
        "per_category": {k: {kk: vv for kk, vv in v.items() if kk != "cases"} for k, v in recap_audit.items()},
    }
    save("golden_set_recap_audit.json", recap_audit)

    # ─────────────────────────────────────────────────────────
    # 5. Deep dive: richest RECAP cases per category
    # ─────────────────────────────────────────────────────────
    section("5. Top RECAP-rich cases in golden_set (per category)")

    for cat, audit in sorted(recap_audit.items()):
        ranked = sorted(audit["cases"], key=lambda x: x["recap_available"], reverse=True)
        top5 = ranked[:5]
        print(f"  {cat}:")
        for r in top5:
            print(f"    {r['docket_id']:>10} recap_avail={r['recap_available']:>4} "
                  f"entries={r['entry_count']:>4} clusters={r['cluster_count']:>2} "
                  f"— {r['case_name'][:45]}")
        print()

    # ─────────────────────────────────────────────────────────
    # 6. Search API — find cases with BOTH opinions AND RECAP
    # ─────────────────────────────────────────────────────────
    section("6. Search API: cases with available RECAP docs per NOS")

    recap_search = {}
    for cat, nos in sorted(NOS_CODES.items()):
        # type=r finds dockets with RECAP data
        data, err = api(
            f"{CL_API}/search/?type=r&suitNature={nos}&order_by=dateFiled+desc",
            token
        )
        if data:
            count = data.get("count", 0)
            results = data.get("results", [])
            # Check first 3 results for detail
            samples = []
            for r in results[:3]:
                samples.append({
                    "docket_id": r.get("docket_id"),
                    "caseName": r.get("caseName", "")[:50],
                    "dateFiled": r.get("dateFiled"),
                    "recap_doc_count": len(r.get("recap_documents", [])),
                })
            recap_search[cat] = {"count": count, "samples": samples}
            print(f"  {cat:20s} NOS {nos}: {count:>8,} dockets with RECAP")
        else:
            print(f"  {cat:20s}: ERROR {err}")
        time.sleep(0.3)

    report["recap_search_by_nos"] = recap_search
    save("recap_search_by_nos.json", recap_search)

    # ─────────────────────────────────────────────────────────
    # 7. Test: recap-document fields on a sample
    # ─────────────────────────────────────────────────────────
    section("7. Sample RECAP document fields")

    # Find a docket with RECAP docs
    data, _ = api(f"{CL_API}/search/?type=r&suitNature=850&order_by=dateFiled+desc", token)
    if data and data.get("results"):
        sample_did = data["results"][0].get("docket_id")
        print(f"  Sampling docket {sample_did}...")
        docs_data, _ = api(
            f"{CL_API}/recap-documents/?docket_entry__docket={sample_did}&is_available=true&page_size=5&format=json",
            token
        )
        if docs_data and docs_data.get("results"):
            sample_doc = docs_data["results"][0]
            print(f"  Sample RECAP document fields:")
            for k, v in sorted(sample_doc.items()):
                val_str = str(v)[:80]
                print(f"    {k:35s} = {val_str}")
            report["sample_recap_doc_fields"] = list(sample_doc.keys())
            save("sample_recap_document.json", docs_data["results"][:5])

    # ─────────────────────────────────────────────────────────
    # 8. Test: docket source bitmask for RECAP identification
    # ─────────────────────────────────────────────────────────
    section("8. Docket source field analysis")

    # Check source values on golden_set dockets
    source_counts = {}
    for cat, cases in list(golden.items())[:3]:  # just 3 categories
        for case in cases[:10]:
            fd_path = os.path.join(GOLDEN_DIR, cat, case["folder"], "full_docket", "docket_full.json")
            if os.path.isfile(fd_path):
                with open(fd_path) as f:
                    fd = json.load(f)
                src = fd.get("source", "unknown")
                source_counts[str(src)] = source_counts.get(str(src), 0) + 1

    print(f"  Source bitmask distribution (sample of 30 golden_set dockets):")
    for src, cnt in sorted(source_counts.items(), key=lambda x: -x[1]):
        print(f"    source={src:>5}: {cnt} dockets")
    report["source_bitmask_sample"] = source_counts

    # ─────────────────────────────────────────────────────────
    # 9. Bulk data availability check
    # ─────────────────────────────────────────────────────────
    section("9. Bulk data endpoints")

    # Check if bulk-data endpoint exists
    for endpoint in ["bulk-data", "recap", "recap-archive"]:
        data, err = api(f"{CL_API}/{endpoint}/?format=json", token)
        if data:
            print(f"  {endpoint}: EXISTS")
            if isinstance(data, dict):
                for k in list(data.keys())[:10]:
                    print(f"    {k}: {str(data[k])[:60]}")
            save(f"bulk_{endpoint}.json", data)
        else:
            print(f"  {endpoint}: {err}")
        time.sleep(0.2)

    # ─────────────────────────────────────────────────────────
    # SUMMARY
    # ─────────────────────────────────────────────────────────
    section("FINAL SUMMARY")

    print(f"Total API calls: {_calls}")
    print(f"\nGolden Set RECAP Audit:")
    print(f"  Total cases checked: {grand_total}")
    print(f"  Cases with ANY RECAP docs: {grand_has_recap} ({grand_has_recap/max(grand_total,1)*100:.0f}%)")
    print(f"  Cases with AVAILABLE RECAP: {grand_has_available} ({grand_has_available/max(grand_total,1)*100:.0f}%)")
    print(f"  Cases with docket entries: {grand_has_entries} ({grand_has_entries/max(grand_total,1)*100:.0f}%)")
    print(f"  Cases with BOTH opinions+RECAP: {grand_has_both} ({grand_has_both/max(grand_total,1)*100:.0f}%)")

    print(f"\nSearch API RECAP counts by NOS:")
    for cat, info in sorted(recap_search.items()):
        if isinstance(info, dict):
            print(f"  {cat:20s}: {info.get('count', 0):>8,} dockets with RECAP")

    report["api_calls"] = _calls
    save("full_investigation_report.json", report)
    print(f"\nAll results saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
