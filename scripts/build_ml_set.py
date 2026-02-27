#!/usr/bin/env python3
"""
Build ml-set/: 100 cases per category, ranked by DATA RICHNESS.

Strategy:
  Phase 1 — DISCOVERY: For each NOS category, find candidate cases that
            actually have RECAP data (docket entries + documents).
  Phase 2 — SCORING:   Score each candidate by:
              - docket_entry_count (filing timeline depth)
              - recap_doc_available (actual downloadable documents)
              - opinion_cluster_count (judicial reasoning)
              composite = entries*1 + available_docs*5 + clusters*20
  Phase 3 — SELECTION:  Pick top 100 per category by score.
  Phase 4 — DOWNLOAD:   Pull everything for selected cases.

Usage:
  python3 scripts/build_ml_set.py discover          # Phase 1+2+3
  python3 scripts/build_ml_set.py download           # Phase 4
  python3 scripts/build_ml_set.py download --limit 100
  python3 scripts/build_ml_set.py report
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

CL_API = "https://www.courtlistener.com/api/rest/v4"
ML_DIR = "ml-set"

_stats = {"api_calls": 0, "api_errors": 0, "bytes_downloaded": 0}

# NOS codes per category
CATEGORIES = {
    "antitrust":       {"nos": "410", "label": "Anti-Trust"},
    "banks":           {"nos": "430", "label": "Banks and Banking"},
    "environmental":   {"nos": "893", "label": "Environmental Matters"},
    "insurance":       {"nos": "110", "label": "Insurance"},
    "other_contract":  {"nos": "190", "label": "Other Contract"},
    "patent":          {"nos": "830", "label": "Patent"},
    "rico":            {"nos": "470", "label": "RICO"},
    "securities":      {"nos": "850", "label": "Securities"},
    "stockholders":    {"nos": "160", "label": "Stockholders Suits"},
    "trade_secret":    {"nos": "880", "label": "Trade Secrets"},
    "trademark":       {"nos": "840", "label": "Trademark"},
}


def api_get(url, token, retries=4, backoff=2):
    if not token:
        return None, "NO_TOKEN"
    headers = {
        "User-Agent": "Ameen-MLSet/1.0",
        "Authorization": f"Token {token}",
    }
    for attempt in range(retries):
        _stats["api_calls"] += 1
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                _stats["bytes_downloaded"] += len(raw)
                return json.loads(raw.decode()), None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = backoff * (2 ** attempt)
                print(f"    RATE LIMITED, waiting {wait}s...")
                time.sleep(wait)
            elif e.code == 404:
                return None, "404"
            elif e.code == 401:
                _stats["api_errors"] += 1
                return None, "401"
            else:
                _stats["api_errors"] += 1
                print(f"    HTTP {e.code}, retry {attempt+1}/{retries}")
                time.sleep(backoff * (2 ** attempt))
        except Exception as e:
            _stats["api_errors"] += 1
            print(f"    Error: {e}, retry {attempt+1}/{retries}")
            time.sleep(backoff * (2 ** attempt))
    return None, "MAX_RETRIES"


def api_get_all_pages(url, token, max_pages=200):
    all_results = []
    page = 0
    while url and page < max_pages:
        data, err = api_get(url, token)
        if err:
            if page == 0:
                return None, err
            break
        all_results.extend(data.get("results", []))
        url = data.get("next")
        page += 1
        if url:
            time.sleep(0.15)
    return all_results, None


def get_count(url, token):
    """Get count from a CL API endpoint using page_size=1."""
    sep = "&" if "?" in url else "?"
    count_url = url + sep + "page_size=1"
    data, err = api_get(count_url, token)
    if err:
        return 0
    results = data.get("results", [])
    # If there's a next page, there are more. Count from results + next existence.
    # Best way: check if 'count' is an int
    count_val = data.get("count", 0)
    if isinstance(count_val, int):
        return count_val
    # Otherwise estimate: if next exists, at least 2 pages
    if data.get("next"):
        return 20  # at least 20+
    return len(results)


# ── PHASE 1+2+3: DISCOVER, SCORE, SELECT ─────────────────────────

def discover(token):
    """Find and rank data-rich cases for each category."""
    os.makedirs(ML_DIR, exist_ok=True)

    for cat_name, cat_info in CATEGORIES.items():
        nos = cat_info["nos"]
        cat_dir = os.path.join(ML_DIR, cat_name)
        selection_file = os.path.join(cat_dir, "_selection.json")

        # Skip if already selected
        if os.path.isfile(selection_file):
            with open(selection_file) as f:
                sel = json.load(f)
            if sel.get("status") == "selected" and len(sel.get("cases", [])) >= 100:
                print(f"  {cat_name}: already selected {len(sel['cases'])} cases, skipping")
                continue

        os.makedirs(cat_dir, exist_ok=True)
        print(f"\n{'=' * 60}")
        print(f"DISCOVERING: {cat_name} (NOS {nos})")
        print("=" * 60)

        # Step 1: Use search API type=r to find cases WITH recap data
        # type=r returns dockets that have RECAP documents
        candidates = {}
        search_url = (f"{CL_API}/search/"
                      f"?type=r"
                      f"&suitNature={nos}"
                      f"&order_by=dateFiled+desc"
                      f"&court=dcd+nysd+nyed+cacd+ilnd+txsd+txnd+flsd+paed+njd+"
                      f"cand+mad+gand+vaed+wawd+mdd+ared+ctd+cod+ord+"
                      f"ohnd+ohsd+miwd+mied+insd+innd+wiwd+wied+tnmd+moed"
                      )

        print(f"  Searching type=r (cases with RECAP data)...")
        page = 0
        max_pages = 40  # up to 800 candidates
        url = search_url
        while url and page < max_pages:
            data, err = api_get(url, token)
            if err:
                print(f"    Search error: {err}")
                break
            for result in data.get("results", []):
                did = result.get("docket_id")
                if did and did not in candidates:
                    candidates[did] = {
                        "docket_id": did,
                        "case_name": result.get("caseName", ""),
                        "court_id": result.get("court_id", ""),
                        "date_filed": result.get("dateFiled", ""),
                        "date_terminated": result.get("dateTerminated", ""),
                        "docket_number": result.get("docketNumber", ""),
                        "nature_of_suit": nos,
                        # Count nested docs as rough indicator
                        "search_doc_count": len(result.get("recap_documents", [])),
                    }
            url = data.get("next")
            page += 1
            if url:
                time.sleep(0.2)

        print(f"  Found {len(candidates)} candidate dockets from search")

        # Also search database API for RECAP-sourced dockets with opinions
        # source bitmask: 1=RECAP, 3=RECAP+SCRAPER, 9=RECAP+IDB, 11=RECAP+SCRAPER+IDB
        db_url = (f"{CL_API}/dockets/"
                  f"?nature_of_suit={nos}"
                  f"&source__in=1,3,9,11"
                  f"&order_by=-date_modified"
                  f"&format=json")
        print(f"  Also checking database API for RECAP-sourced dockets...")
        page = 0
        url = db_url
        while url and page < 20 and len(candidates) < 800:
            data, err = api_get(url, token)
            if err:
                break
            for d in data.get("results", []):
                did = str(d.get("id", ""))
                if did and did not in candidates:
                    candidates[did] = {
                        "docket_id": did,
                        "case_name": d.get("case_name", ""),
                        "court_id": d.get("court_id", ""),
                        "date_filed": d.get("date_filed", ""),
                        "date_terminated": d.get("date_terminated", ""),
                        "docket_number": d.get("docket_number", ""),
                        "nature_of_suit": nos,
                        "search_doc_count": 0,
                        "cluster_count": len(d.get("clusters", [])),
                    }
            url = data.get("next")
            page += 1
            if url:
                time.sleep(0.2)

        print(f"  Total candidates: {len(candidates)}")

        if len(candidates) == 0:
            print(f"  WARNING: No candidates found for {cat_name}")
            continue

        # Step 2: Score each candidate
        print(f"  Scoring {len(candidates)} candidates...")
        scored = []
        for i, (did, info) in enumerate(candidates.items()):
            if i % 50 == 0:
                print(f"    [{i}/{len(candidates)}] scored, API calls: {_stats['api_calls']}")
                sys.stdout.flush()

            # Get docket detail (for cluster count)
            cluster_count = info.get("cluster_count", 0)
            if cluster_count == 0:
                docket_url = f"{CL_API}/dockets/{did}/?fields=id,clusters,case_name,court_id,date_filed,date_terminated,assigned_to_str,nature_of_suit,cause,slug&format=json"
                docket_data, err = api_get(docket_url, token)
                if err:
                    continue
                cluster_count = len(docket_data.get("clusters", []))
                info["case_name"] = docket_data.get("case_name", info.get("case_name", ""))
                info["court_id"] = docket_data.get("court_id", info.get("court_id", ""))
                info["assigned_to_str"] = docket_data.get("assigned_to_str", "")
                info["slug"] = docket_data.get("slug", "")
                time.sleep(0.1)

            # Count docket entries
            entries_url = f"{CL_API}/docket-entries/?docket={did}&format=json&page_size=1"
            entry_data, err = api_get(entries_url, token)
            entry_count = 0
            if not err and entry_data:
                entry_count = entry_data.get("count", 0)
                if not isinstance(entry_count, int):
                    # Estimate from results
                    entry_count = len(entry_data.get("results", []))
                    if entry_data.get("next"):
                        entry_count = 20  # at least a page
            time.sleep(0.1)

            # Count available RECAP documents
            docs_url = f"{CL_API}/recap-documents/?docket_entry__docket={did}&is_available=true&format=json&page_size=1"
            doc_data, err = api_get(docs_url, token)
            doc_count = 0
            if not err and doc_data:
                doc_count = doc_data.get("count", 0)
                if not isinstance(doc_count, int):
                    doc_count = len(doc_data.get("results", []))
                    if doc_data.get("next"):
                        doc_count = 20
            time.sleep(0.1)

            info["cluster_count"] = cluster_count
            info["entry_count"] = entry_count
            info["available_doc_count"] = doc_count

            # Composite score: balance opinions and RECAP data
            # Both must be present for a good score
            score = entry_count * 1 + doc_count * 5 + cluster_count * 20
            # Bonus if case has BOTH opinions and docs
            if cluster_count > 0 and doc_count > 0:
                score *= 2
            # Penalty if missing either entirely
            if cluster_count == 0:
                score = score // 4
            if entry_count == 0 and doc_count == 0:
                score = score // 10

            info["score"] = score
            scored.append(info)

        # Step 3: Sort and pick top 100
        scored.sort(key=lambda x: x["score"], reverse=True)
        top100 = scored[:100]

        # Save selection
        selection = {
            "status": "selected",
            "category": cat_name,
            "nos_code": nos,
            "total_candidates": len(candidates),
            "cases": top100,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with open(selection_file, "w") as f:
            json.dump(selection, f, indent=2)

        # Print top 5
        print(f"\n  Top 5 for {cat_name}:")
        for j, c in enumerate(top100[:5], 1):
            print(f"    {j}. score={c['score']} entries={c['entry_count']} "
                  f"docs={c['available_doc_count']} opinions={c['cluster_count']} "
                  f"— {c['case_name'][:60]}")
        if top100:
            avg_score = sum(c['score'] for c in top100) / len(top100)
            avg_entries = sum(c['entry_count'] for c in top100) / len(top100)
            avg_docs = sum(c['available_doc_count'] for c in top100) / len(top100)
            avg_clusters = sum(c['cluster_count'] for c in top100) / len(top100)
            print(f"\n  Top 100 averages: score={avg_score:.0f} entries={avg_entries:.0f} "
                  f"docs={avg_docs:.0f} opinions={avg_clusters:.1f}")
        print(f"  Saved to {selection_file}")

    print(f"\n\nDiscovery complete. API calls: {_stats['api_calls']}")


# ── PHASE 4: DOWNLOAD EVERYTHING ──────────────────────────────────

def is_phase_done(case_dir, subfolder):
    marker = os.path.join(case_dir, subfolder, "_done.json")
    if not os.path.isfile(marker):
        return False
    try:
        with open(marker) as f:
            m = json.load(f)
        return m.get("status") == "ok"
    except Exception:
        return False


def write_marker(sub_dir, stats):
    stats["status"] = "ok"
    stats["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(os.path.join(sub_dir, "_done.json"), "w") as f:
        json.dump(stats, f, indent=2)


def download_case(case_dir, docket_id, token):
    """Download ALL available data for a single case."""
    downloaded = []

    # 1. Full docket
    if not is_phase_done(case_dir, "full_docket"):
        sub = os.path.join(case_dir, "full_docket")
        os.makedirs(sub, exist_ok=True)
        data, err = api_get(f"{CL_API}/dockets/{docket_id}/?format=json", token)
        if data:
            with open(os.path.join(sub, "docket_full.json"), "w") as f:
                json.dump(data, f, indent=2)
            write_marker(sub, {"docket_id": docket_id, "fields": len(data)})
            downloaded.append("full_docket")
        time.sleep(0.15)

    # 2. Docket entries (the timeline we were missing!)
    if not is_phase_done(case_dir, "docket_entries"):
        sub = os.path.join(case_dir, "docket_entries")
        os.makedirs(sub, exist_ok=True)
        url = f"{CL_API}/docket-entries/?docket={docket_id}&order_by=date_filed&format=json"
        entries, err = api_get_all_pages(url, token, max_pages=200)
        if entries is not None:
            with open(os.path.join(sub, "entries.json"), "w") as f:
                json.dump(entries, f, indent=2)
            total_docs = sum(len(e.get("recap_documents", [])) for e in entries)
            write_marker(sub, {
                "docket_id": docket_id,
                "entry_count": len(entries),
                "recap_doc_count": total_docs,
            })
            downloaded.append("docket_entries")
        time.sleep(0.15)

    # 3. Parties
    if not is_phase_done(case_dir, "parties"):
        sub = os.path.join(case_dir, "parties")
        os.makedirs(sub, exist_ok=True)
        url = f"{CL_API}/parties/?docket={docket_id}&format=json"
        parties, err = api_get_all_pages(url, token, max_pages=50)
        if parties is not None:
            with open(os.path.join(sub, "parties.json"), "w") as f:
                json.dump(parties, f, indent=2)
            write_marker(sub, {"docket_id": docket_id, "count": len(parties)})
            downloaded.append("parties")
        time.sleep(0.15)

    # 4. Attorneys
    if not is_phase_done(case_dir, "attorneys"):
        sub = os.path.join(case_dir, "attorneys")
        os.makedirs(sub, exist_ok=True)
        url = f"{CL_API}/attorneys/?docket={docket_id}&format=json"
        attorneys, err = api_get_all_pages(url, token, max_pages=50)
        if attorneys is not None:
            with open(os.path.join(sub, "attorneys.json"), "w") as f:
                json.dump(attorneys, f, indent=2)
            write_marker(sub, {"docket_id": docket_id, "count": len(attorneys)})
            downloaded.append("attorneys")
        time.sleep(0.15)

    # 5. RECAP documents metadata (availability, page counts, etc.)
    if not is_phase_done(case_dir, "recap_documents"):
        sub = os.path.join(case_dir, "recap_documents")
        os.makedirs(sub, exist_ok=True)
        url = f"{CL_API}/recap-documents/?docket_entry__docket={docket_id}&format=json"
        docs, err = api_get_all_pages(url, token, max_pages=200)
        if docs is not None:
            with open(os.path.join(sub, "documents.json"), "w") as f:
                json.dump(docs, f, indent=2)
            available = sum(1 for d in docs if d.get("is_available"))
            with_text = sum(1 for d in docs if d.get("plain_text"))
            total_pages = sum(d.get("page_count", 0) or 0 for d in docs)
            write_marker(sub, {
                "docket_id": docket_id,
                "count": len(docs),
                "available": available,
                "with_text": with_text,
                "total_pages": total_pages,
            })
            downloaded.append("recap_documents")
        time.sleep(0.15)

    # 6. Opinions (clusters + full opinion text)
    if not is_phase_done(case_dir, "opinions"):
        sub = os.path.join(case_dir, "opinions")
        os.makedirs(sub, exist_ok=True)

        # Get cluster URLs from full_docket
        cluster_urls = []
        fd_path = os.path.join(case_dir, "full_docket", "docket_full.json")
        if os.path.isfile(fd_path):
            with open(fd_path) as f:
                fd = json.load(f)
            cluster_urls = [c for c in fd.get("clusters", []) if isinstance(c, str)]

        all_clusters = []
        all_opinions = []
        for curl in cluster_urls:
            if not curl.startswith("http"):
                curl = f"https://www.courtlistener.com{curl}"
            if "?" not in curl:
                curl += "?format=json"
            elif "format=json" not in curl:
                curl += "&format=json"
            cdata, err = api_get(curl, token)
            if cdata:
                all_clusters.append(cdata)
                for op_url in cdata.get("sub_opinions", []):
                    if not isinstance(op_url, str):
                        continue
                    ourl = op_url if op_url.startswith("http") else f"https://www.courtlistener.com{op_url}"
                    if "?" not in ourl:
                        ourl += "?format=json"
                    elif "format=json" not in ourl:
                        ourl += "&format=json"
                    odata, _ = api_get(ourl, token)
                    if odata:
                        all_opinions.append(odata)
                    time.sleep(0.1)
            time.sleep(0.1)

        with open(os.path.join(sub, "clusters.json"), "w") as f:
            json.dump(all_clusters, f, indent=2)
        with open(os.path.join(sub, "opinions.json"), "w") as f:
            json.dump(all_opinions, f, indent=2)
        write_marker(sub, {
            "docket_id": docket_id,
            "cluster_count": len(all_clusters),
            "opinion_count": len(all_opinions),
        })
        downloaded.append("opinions")

    # 7. Citations
    if not is_phase_done(case_dir, "citations"):
        sub = os.path.join(case_dir, "citations")
        os.makedirs(sub, exist_ok=True)
        cluster_ids = set()
        cl_path = os.path.join(case_dir, "opinions", "clusters.json")
        if os.path.isfile(cl_path):
            with open(cl_path) as f:
                for c in json.load(f):
                    if isinstance(c, dict) and c.get("id"):
                        cluster_ids.add(str(c["id"]))
        citing = []
        cited_by = []
        for cid in cluster_ids:
            r, _ = api_get_all_pages(f"{CL_API}/citations/?cited_opinion__cluster={cid}&format=json", token, 20)
            if r: citing.extend(r)
            r, _ = api_get_all_pages(f"{CL_API}/citations/?citing_opinion__cluster={cid}&format=json", token, 20)
            if r: cited_by.extend(r)
            time.sleep(0.1)
        with open(os.path.join(sub, "citing.json"), "w") as f:
            json.dump(citing, f, indent=2)
        with open(os.path.join(sub, "cited_by.json"), "w") as f:
            json.dump(cited_by, f, indent=2)
        write_marker(sub, {"docket_id": docket_id, "citing": len(citing), "cited_by": len(cited_by)})
        downloaded.append("citations")

    # 8. Judge profiles
    if not is_phase_done(case_dir, "judge_profiles"):
        sub = os.path.join(case_dir, "judge_profiles")
        os.makedirs(sub, exist_ok=True)
        person_urls = set()
        fd_path = os.path.join(case_dir, "full_docket", "docket_full.json")
        if os.path.isfile(fd_path):
            with open(fd_path) as f:
                fd = json.load(f)
            for field in ["assigned_to", "referred_to"]:
                purl = fd.get(field)
                if purl and isinstance(purl, str) and "/people/" in purl:
                    person_urls.add(purl)
            for purl in fd.get("panel", []):
                if isinstance(purl, str) and "/people/" in purl:
                    person_urls.add(purl)
        profiles = {}
        for purl in person_urls:
            full_url = purl if purl.startswith("http") else f"https://www.courtlistener.com{purl}"
            data, _ = api_get(full_url + "?format=json", token)
            if data:
                profiles[str(data.get("id", ""))] = data
            time.sleep(0.1)
        for pid, profile in profiles.items():
            with open(os.path.join(sub, f"person_{pid}.json"), "w") as f:
                json.dump(profile, f, indent=2)
        write_marker(sub, {"docket_id": docket_id, "count": len(profiles)})
        downloaded.append("judge_profiles")

    return downloaded


def download_all(token, limit=0):
    """Download all data for selected cases."""
    total_cases = 0
    total_done = 0
    start = time.time()

    for cat_name in sorted(CATEGORIES.keys()):
        cat_dir = os.path.join(ML_DIR, cat_name)
        sel_file = os.path.join(cat_dir, "_selection.json")
        if not os.path.isfile(sel_file):
            print(f"  {cat_name}: no selection file, run 'discover' first")
            continue

        with open(sel_file) as f:
            sel = json.load(f)
        cases = sel.get("cases", [])
        if not cases:
            continue

        print(f"\n{'=' * 60}")
        print(f"DOWNLOADING: {cat_name} ({len(cases)} cases)")
        print("=" * 60)

        for i, case_info in enumerate(cases, 1):
            total_cases += 1
            if limit > 0 and total_cases > limit:
                return

            did = str(case_info["docket_id"])
            slug = case_info.get("slug", "") or case_info.get("case_name", "").replace(" ", "_")[:50]
            # Clean slug
            slug = "".join(c for c in slug if c.isalnum() or c in "_-")
            folder_name = f"{i:03d}_{did}_{slug}"
            case_dir = os.path.join(cat_dir, folder_name)
            os.makedirs(case_dir, exist_ok=True)

            # Save base docket info
            docket_path = os.path.join(case_dir, "docket.json")
            if not os.path.isfile(docket_path):
                with open(docket_path, "w") as f:
                    json.dump(case_info, f, indent=2)

            # Check if fully done
            all_phases = ["full_docket", "docket_entries", "parties", "attorneys",
                          "recap_documents", "opinions", "citations", "judge_profiles"]
            phases_done = sum(1 for p in all_phases if is_phase_done(case_dir, p))
            if phases_done == len(all_phases):
                total_done += 1
                if i % 25 == 0:
                    elapsed = (time.time() - start) / 60
                    print(f"  [{i}/{len(cases)}] skip (done) | "
                          f"{elapsed:.1f}m | API: {_stats['api_calls']}")
                continue

            downloaded = download_case(case_dir, did, token)
            if downloaded:
                total_done += 1

            if i % 10 == 0 or i == 1:
                elapsed = (time.time() - start) / 60
                mb = _stats["bytes_downloaded"] / 1024 / 1024
                print(f"  [{i}/{len(cases)}] {','.join(downloaded) if downloaded else 'skip'} | "
                      f"{elapsed:.1f}m | API: {_stats['api_calls']} | {mb:.1f}MB")
                sys.stdout.flush()

    elapsed = (time.time() - start) / 60
    print(f"\nDownload complete: {total_done}/{total_cases} cases | {elapsed:.1f} min")


# ── REPORT ────────────────────────────────────────────────────────

def report():
    layers = ["full_docket", "docket_entries", "parties", "attorneys",
              "recap_documents", "opinions", "citations", "judge_profiles"]

    print(f"\n{'=' * 60}")
    print(f"ML-SET REPORT")
    print("=" * 60)

    grand_total = 0
    grand_done = {l: 0 for l in layers}
    grand_entries = 0
    grand_docs = 0
    grand_available = 0
    grand_opinions = 0
    grand_parties = 0
    grand_attorneys = 0

    for cat_name in sorted(CATEGORIES.keys()):
        cat_dir = os.path.join(ML_DIR, cat_name)
        if not os.path.isdir(cat_dir):
            continue
        case_count = 0
        cat_entries = 0
        cat_docs = 0
        for item in sorted(os.listdir(cat_dir)):
            item_path = os.path.join(cat_dir, item)
            if not os.path.isdir(item_path) or item.startswith("_"):
                continue
            case_count += 1
            for layer in layers:
                if is_phase_done(item_path, layer):
                    grand_done[layer] += 1
            # Count entries
            m = os.path.join(item_path, "docket_entries", "_done.json")
            if os.path.isfile(m):
                try:
                    d = json.load(open(m))
                    cat_entries += d.get("entry_count", 0)
                    grand_entries += d.get("entry_count", 0)
                except: pass
            # Count docs
            m = os.path.join(item_path, "recap_documents", "_done.json")
            if os.path.isfile(m):
                try:
                    d = json.load(open(m))
                    cat_docs += d.get("available", 0)
                    grand_docs += d.get("count", 0)
                    grand_available += d.get("available", 0)
                except: pass
            # Count opinions
            m = os.path.join(item_path, "opinions", "_done.json")
            if os.path.isfile(m):
                try:
                    d = json.load(open(m))
                    grand_opinions += d.get("opinion_count", 0)
                except: pass
            # Count parties
            m = os.path.join(item_path, "parties", "_done.json")
            if os.path.isfile(m):
                try:
                    d = json.load(open(m))
                    grand_parties += d.get("count", 0)
                except: pass
            # Count attorneys
            m = os.path.join(item_path, "attorneys", "_done.json")
            if os.path.isfile(m):
                try:
                    d = json.load(open(m))
                    grand_attorneys += d.get("count", 0)
                except: pass

        grand_total += case_count
        if case_count > 0:
            print(f"  {cat_name:25s} {case_count:>4} cases | "
                  f"{cat_entries:>6} entries | {cat_docs:>5} docs avail")

    print(f"\n  {'TOTAL':25s} {grand_total:>4} cases")
    print()
    for layer in layers:
        done = grand_done[layer]
        pct = done / max(grand_total, 1) * 100
        bar = "#" * int(pct / 5) + "." * (20 - int(pct / 5))
        print(f"  {layer:25s} [{bar}] {done:>5}/{grand_total} ({pct:.0f}%)")

    print(f"\n  --- DATA TOTALS ---")
    print(f"  Docket entries:  {grand_entries:,}")
    print(f"  RECAP documents: {grand_docs:,} total, {grand_available:,} available")
    print(f"  Opinions:        {grand_opinions:,}")
    print(f"  Parties:         {grand_parties:,}")
    print(f"  Attorneys:       {grand_attorneys:,}")
    print("=" * 60)


# ── CLI ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Build ML training set")
    parser.add_argument("command", choices=["discover", "download", "report"])
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    if args.command == "report":
        report()
        return

    token = os.environ.get("CL_API_TOKEN", "") or os.environ.get("COURTLISTENER_TOKEN", "")
    if not token:
        print("FATAL: CL_API_TOKEN or COURTLISTENER_TOKEN required")
        sys.exit(1)
    print(f"Token OK (length={len(token)})")

    # Test API
    test, err = api_get(f"{CL_API}/courts/?format=json&page_size=1", token)
    if err:
        print(f"FATAL: API test failed: {err}")
        sys.exit(1)
    print("API OK\n")

    if args.command == "discover":
        discover(token)
    elif args.command == "download":
        download_all(token, args.limit)

    report()


if __name__ == "__main__":
    main()
