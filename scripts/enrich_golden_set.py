#!/usr/bin/env python3
"""
Enrich golden_set/ cases with ALL available CourtListener API data.

Phases (run individually or all together):
  1. full_docket          — re-fetch full docket from /dockets/{id}/ (60 fields)
  2. docket_entries       — full timeline + nested RECAP docs
  3. parties              — parties with roles (plaintiff, defendant, etc.)
  4. attorneys            — attorneys with firm info, contact, roles
  5. opinions             — opinion cluster text (from clusters in full_docket)
  6. recap_documents      — RECAP document metadata (availability, page count, text)
  7. citations            — citation graph (citing + cited_by)
  8. oral_arguments       — oral argument audio metadata
  9. judge_profiles       — judge person records (positions, education, etc.)
  10. financial_disclosures — judge financial disclosures

All phases are resumable: skip cases that already have a valid _done.json marker.

Usage:
  python3 scripts/enrich_golden_set.py all --limit 5
  python3 scripts/enrich_golden_set.py parties
  python3 scripts/enrich_golden_set.py docket_entries --limit 100
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
GOLDEN_DIR = "golden_set"

# ── Global state ──────────────────────────────────────────────────
_stats = {"api_calls": 0, "api_errors": 0, "bytes_downloaded": 0}


def api_get(url, token, retries=4, backoff=2):
    """GET from CourtListener API with retries. Token REQUIRED (v4.3+)."""
    if not token:
        return None, "NO_TOKEN"

    headers = {
        "User-Agent": "Ameen-Enrich/3.0",
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
                print(f"    AUTH FAILED (401) — check CL_API_TOKEN")
                _stats["api_errors"] += 1
                return None, "401"
            else:
                _stats["api_errors"] += 1
                print(f"    HTTP {e.code} for {url[:80]}..., retry {attempt+1}/{retries}")
                time.sleep(backoff * (2 ** attempt))
        except Exception as e:
            _stats["api_errors"] += 1
            print(f"    Error: {e}, retry {attempt+1}/{retries}")
            time.sleep(backoff * (2 ** attempt))
    return None, "MAX_RETRIES"


def api_get_all_pages(url, token, max_pages=200):
    """Fetch all pages from a paginated CL API endpoint."""
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



def find_golden_cases():
    """Walk golden_set/ and return list of (case_dir, docket_id, docket_data)."""
    cases = []
    for cat in sorted(os.listdir(GOLDEN_DIR)):
        cat_dir = os.path.join(GOLDEN_DIR, cat)
        if not os.path.isdir(cat_dir):
            continue
        for case_folder in sorted(os.listdir(cat_dir)):
            case_dir = os.path.join(cat_dir, case_folder)
            docket_path = os.path.join(case_dir, "docket.json")
            if not os.path.isfile(docket_path):
                continue
            with open(docket_path) as f:
                docket = json.load(f)
            docket_id = str(docket.get("id", ""))
            if docket_id:
                cases.append((case_dir, docket_id, docket))
    return cases


def is_phase_done(case_dir, subfolder):
    """Check if a phase is already completed for a case."""
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
    """Write a _done.json marker indicating successful completion."""
    stats["status"] = "ok"
    stats["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(os.path.join(sub_dir, "_done.json"), "w") as f:
        json.dump(stats, f, indent=2)


def progress_line(i, total, fetched, skipped, failed, start):
    elapsed = time.time() - start
    rate = fetched / max(elapsed, 1) * 3600
    mb = _stats["bytes_downloaded"] / 1024 / 1024
    print(f"  [{i}/{total}] fetched={fetched} skip={skipped} fail={failed} | "
          f"{elapsed/60:.1f}m | ~{rate:.0f}/hr | {mb:.1f}MB")
    sys.stdout.flush()


# ── Phase 1: Full Docket Detail ──────────────────────────────────

def enrich_full_docket(cases, token):
    print(f"\n{'=' * 60}")
    print(f"PHASE 1: FULL DOCKET DETAIL ({len(cases):,} cases)")
    print("=" * 60)

    fetched = skipped = failed = 0
    start = time.time()

    for i, (case_dir, docket_id, docket) in enumerate(cases, 1):
        if i % 25 == 0 or i == 1:
            progress_line(i, len(cases), fetched, skipped, failed, start)

        if is_phase_done(case_dir, "full_docket"):
            skipped += 1
            continue

        sub_dir = os.path.join(case_dir, "full_docket")
        os.makedirs(sub_dir, exist_ok=True)

        url = f"{CL_API}/dockets/{docket_id}/?format=json"
        data, err = api_get(url, token)

        if err:
            failed += 1
            print(f"    FAILED {docket_id}: {err}")
            if err == "401":
                print("    FATAL: Auth failed. Aborting.")
                return fetched
            continue

        with open(os.path.join(sub_dir, "docket_full.json"), "w") as f:
            json.dump(data, f, indent=2)

        write_marker(sub_dir, {"docket_id": docket_id, "fields_count": len(data)})
        fetched += 1
        time.sleep(0.2)

    elapsed = time.time() - start
    print(f"\nFull docket done: {fetched} fetched, {skipped} skipped, {failed} failed ({elapsed/60:.1f} min)")
    return fetched


# ── Phase 2: Docket Entries + RECAP text ──────────────────────────

def enrich_docket_entries(cases, token):
    print(f"\n{'=' * 60}")
    print(f"PHASE 2: DOCKET ENTRIES ({len(cases):,} cases)")
    print("=" * 60)

    fetched = skipped = failed = 0
    start = time.time()

    for i, (case_dir, docket_id, docket) in enumerate(cases, 1):
        if i % 10 == 0 or i == 1:
            progress_line(i, len(cases), fetched, skipped, failed, start)

        if is_phase_done(case_dir, "docket_entries"):
            skipped += 1
            continue

        sub_dir = os.path.join(case_dir, "docket_entries")
        os.makedirs(sub_dir, exist_ok=True)

        # Per the reference guide: omit plain_text for listing, fetch separately if needed
        url = (f"{CL_API}/docket-entries/"
               f"?docket={docket_id}"
               f"&order_by=date_filed"
               f"&format=json")
        entries, err = api_get_all_pages(url, token, max_pages=200)

        if err:
            failed += 1
            print(f"    FAILED {docket_id}: {err}")
            if err == "401":
                print("    FATAL: Auth failed. Aborting.")
                return fetched
            continue

        with open(os.path.join(sub_dir, "entries.json"), "w") as f:
            json.dump(entries, f, indent=2)

        docs_with_text = 0
        total_docs = 0
        for entry in entries:
            for doc in entry.get("recap_documents", []):
                total_docs += 1
                if doc.get("plain_text"):
                    docs_with_text += 1

        write_marker(sub_dir, {
            "docket_id": docket_id,
            "entry_count": len(entries),
            "recap_doc_count": total_docs,
            "docs_with_text": docs_with_text,
        })
        fetched += 1
        time.sleep(0.2)

    elapsed = time.time() - start
    print(f"\nDocket entries done: {fetched} fetched, {skipped} skipped, {failed} failed ({elapsed/60:.1f} min)")
    return fetched


# ── Phase 3: Parties ─────────────────────────────────────────────

def enrich_parties(cases, token):
    print(f"\n{'=' * 60}")
    print(f"PHASE 3: PARTIES ({len(cases):,} cases)")
    print("=" * 60)

    fetched = skipped = failed = 0
    start = time.time()

    for i, (case_dir, docket_id, docket) in enumerate(cases, 1):
        if i % 25 == 0 or i == 1:
            progress_line(i, len(cases), fetched, skipped, failed, start)

        if is_phase_done(case_dir, "parties"):
            skipped += 1
            continue

        sub_dir = os.path.join(case_dir, "parties")
        os.makedirs(sub_dir, exist_ok=True)

        # Use nested endpoint: /dockets/{id}/parties/
        url = f"{CL_API}/dockets/{docket_id}/parties/?format=json"
        parties, err = api_get_all_pages(url, token, max_pages=50)

        if err:
            failed += 1
            print(f"    FAILED {docket_id}: {err}")
            if err == "401":
                print("    FATAL: Auth failed. Aborting.")
                return fetched
            continue

        with open(os.path.join(sub_dir, "parties.json"), "w") as f:
            json.dump(parties, f, indent=2)

        # Count by type
        party_types = {}
        for p in parties:
            pt = "unknown"
            if isinstance(p.get("party_type"), dict):
                pt = p["party_type"].get("name", "unknown")
            elif isinstance(p.get("party_type"), str):
                pt = p["party_type"]
            party_types[pt] = party_types.get(pt, 0) + 1

        write_marker(sub_dir, {
            "docket_id": docket_id,
            "party_count": len(parties),
            "party_types": party_types,
        })
        fetched += 1
        time.sleep(0.2)

    elapsed = time.time() - start
    print(f"\nParties done: {fetched} fetched, {skipped} skipped, {failed} failed ({elapsed/60:.1f} min)")
    return fetched


# ── Phase 4: Attorneys ────────────────────────────────────────────

def enrich_attorneys(cases, token):
    print(f"\n{'=' * 60}")
    print(f"PHASE 4: ATTORNEYS ({len(cases):,} cases)")
    print("=" * 60)

    fetched = skipped = failed = 0
    start = time.time()

    for i, (case_dir, docket_id, docket) in enumerate(cases, 1):
        if i % 25 == 0 or i == 1:
            progress_line(i, len(cases), fetched, skipped, failed, start)

        if is_phase_done(case_dir, "attorneys"):
            skipped += 1
            continue

        sub_dir = os.path.join(case_dir, "attorneys")
        os.makedirs(sub_dir, exist_ok=True)

        # Use nested endpoint: /dockets/{id}/attorneys/
        url = f"{CL_API}/dockets/{docket_id}/attorneys/?format=json"
        attorneys, err = api_get_all_pages(url, token, max_pages=50)

        if err:
            failed += 1
            print(f"    FAILED {docket_id}: {err}")
            if err == "401":
                print("    FATAL: Auth failed. Aborting.")
                return fetched
            continue

        with open(os.path.join(sub_dir, "attorneys.json"), "w") as f:
            json.dump(attorneys, f, indent=2)

        # Count roles
        roles = {}
        for a in attorneys:
            for role in a.get("roles", []):
                r = role if isinstance(role, str) else str(role)
                roles[r] = roles.get(r, 0) + 1

        write_marker(sub_dir, {
            "docket_id": docket_id,
            "attorney_count": len(attorneys),
            "roles": roles,
        })
        fetched += 1
        time.sleep(0.2)

    elapsed = time.time() - start
    print(f"\nAttorneys done: {fetched} fetched, {skipped} skipped, {failed} failed ({elapsed/60:.1f} min)")
    return fetched


# ── Phase 5: Opinions / Clusters ─────────────────────────────────

def enrich_opinions(cases, token):
    print(f"\n{'=' * 60}")
    print(f"PHASE 5: OPINIONS / CLUSTERS ({len(cases):,} cases)")
    print("=" * 60)

    fetched = skipped = failed = 0
    start = time.time()

    for i, (case_dir, docket_id, docket) in enumerate(cases, 1):
        if i % 25 == 0 or i == 1:
            progress_line(i, len(cases), fetched, skipped, failed, start)

        if is_phase_done(case_dir, "opinions"):
            skipped += 1
            continue

        sub_dir = os.path.join(case_dir, "opinions")
        os.makedirs(sub_dir, exist_ok=True)

        # Get cluster URLs from full_docket if available
        cluster_urls = []
        full_docket_path = os.path.join(case_dir, "full_docket", "docket_full.json")
        if os.path.isfile(full_docket_path):
            with open(full_docket_path) as f:
                fd = json.load(f)
            cluster_urls = fd.get("clusters", [])

        # Also check docket.json for clusters
        docket_clusters = docket.get("clusters", [])
        for c in docket_clusters:
            if c not in cluster_urls:
                cluster_urls.append(c)

        all_opinions = []
        all_clusters = []

        for cluster_url in cluster_urls:
            if not isinstance(cluster_url, str):
                continue
            # Fetch cluster
            curl = cluster_url if cluster_url.startswith("http") else f"https://www.courtlistener.com{cluster_url}"
            if "?format=json" not in curl:
                curl += "?format=json" if "?" not in curl else "&format=json"
            cluster_data, err = api_get(curl, token)
            if err == "401":
                print("    FATAL: Auth failed. Aborting.")
                return fetched
            if cluster_data:
                all_clusters.append(cluster_data)
                # Fetch individual opinions from this cluster
                opinion_urls = cluster_data.get("sub_opinions", [])
                for op_url in opinion_urls:
                    if not isinstance(op_url, str):
                        continue
                    ourl = op_url if op_url.startswith("http") else f"https://www.courtlistener.com{op_url}"
                    if "?format=json" not in ourl:
                        ourl += "?format=json" if "?" not in ourl else "&format=json"
                    op_data, oerr = api_get(ourl, token)
                    if op_data:
                        all_opinions.append(op_data)
                    time.sleep(0.15)
            time.sleep(0.15)

        with open(os.path.join(sub_dir, "clusters.json"), "w") as f:
            json.dump(all_clusters, f, indent=2)
        with open(os.path.join(sub_dir, "opinions.json"), "w") as f:
            json.dump(all_opinions, f, indent=2)

        write_marker(sub_dir, {
            "docket_id": docket_id,
            "cluster_count": len(all_clusters),
            "opinion_count": len(all_opinions),
        })
        fetched += 1

    elapsed = time.time() - start
    print(f"\nOpinions done: {fetched} fetched, {skipped} skipped, {failed} failed ({elapsed/60:.1f} min)")
    return fetched


# ── Phase 6: RECAP Documents (separate endpoint) ─────────────────

def enrich_recap_documents(cases, token):
    print(f"\n{'=' * 60}")
    print(f"PHASE 6: RECAP DOCUMENTS ({len(cases):,} cases)")
    print("=" * 60)

    fetched = skipped = failed = 0
    start = time.time()

    for i, (case_dir, docket_id, docket) in enumerate(cases, 1):
        if i % 10 == 0 or i == 1:
            progress_line(i, len(cases), fetched, skipped, failed, start)

        if is_phase_done(case_dir, "recap_documents"):
            skipped += 1
            continue

        sub_dir = os.path.join(case_dir, "recap_documents")
        os.makedirs(sub_dir, exist_ok=True)

        # Fetch RECAP documents for this docket (omit plain_text to avoid huge payloads)
        url = (f"{CL_API}/recap-documents/"
               f"?docket_entry__docket={docket_id}"
               f"&omit=plain_text"
               f"&format=json")
        docs, err = api_get_all_pages(url, token, max_pages=200)

        if err:
            failed += 1
            print(f"    FAILED {docket_id}: {err}")
            if err == "401":
                print("    FATAL: Auth failed. Aborting.")
                return fetched
            continue

        with open(os.path.join(sub_dir, "documents.json"), "w") as f:
            json.dump(docs, f, indent=2)

        available = sum(1 for d in docs if d.get("is_available"))
        free = sum(1 for d in docs if d.get("is_free_on_pacer"))
        total_pages = sum(d.get("page_count", 0) or 0 for d in docs)

        write_marker(sub_dir, {
            "docket_id": docket_id,
            "document_count": len(docs),
            "available_in_recap": available,
            "free_on_pacer": free,
            "total_pages": total_pages,
        })
        fetched += 1
        time.sleep(0.2)

    elapsed = time.time() - start
    print(f"\nRECAP documents done: {fetched} fetched, {skipped} skipped, {failed} failed ({elapsed/60:.1f} min)")
    return fetched


# ── Phase 7: Citations ────────────────────────────────────────────

def enrich_citations(cases, token):
    print(f"\n{'=' * 60}")
    print(f"PHASE 7: CITATIONS ({len(cases):,} cases)")
    print("=" * 60)

    fetched = skipped = failed = 0
    start = time.time()

    for i, (case_dir, docket_id, docket) in enumerate(cases, 1):
        if i % 25 == 0 or i == 1:
            progress_line(i, len(cases), fetched, skipped, failed, start)

        if is_phase_done(case_dir, "citations"):
            skipped += 1
            continue

        sub_dir = os.path.join(case_dir, "citations")
        os.makedirs(sub_dir, exist_ok=True)

        # Get cluster IDs from opinions dir or full_docket
        cluster_ids = set()

        opinions_dir = os.path.join(case_dir, "opinions")
        if os.path.isdir(opinions_dir):
            clusters_path = os.path.join(opinions_dir, "clusters.json")
            if os.path.isfile(clusters_path):
                try:
                    with open(clusters_path) as f:
                        clusters = json.load(f)
                    for c in clusters:
                        if isinstance(c, dict) and c.get("id"):
                            cluster_ids.add(str(c["id"]))
                except Exception:
                    pass
            # Also check for old-style cluster folders
            for cl_folder in os.listdir(opinions_dir):
                if cl_folder.startswith("cluster_"):
                    cluster_ids.add(cl_folder.replace("cluster_", ""))

        # Also get from full_docket
        full_docket_path = os.path.join(case_dir, "full_docket", "docket_full.json")
        if os.path.isfile(full_docket_path):
            with open(full_docket_path) as f:
                fd = json.load(f)
            for curl in fd.get("clusters", []):
                if isinstance(curl, str):
                    # Extract ID from URL like https://.../clusters/12345/
                    parts = curl.rstrip("/").split("/")
                    if parts:
                        cluster_ids.add(parts[-1])

        citing = []
        cited_by = []

        for cid in cluster_ids:
            url = f"{CL_API}/citations/?cited_opinion__cluster={cid}&format=json"
            results, err = api_get_all_pages(url, token, max_pages=20)
            if err == "401":
                print("    FATAL: Auth failed. Aborting.")
                return fetched
            if results:
                citing.extend(results)

            url = f"{CL_API}/citations/?citing_opinion__cluster={cid}&format=json"
            results, err = api_get_all_pages(url, token, max_pages=20)
            if err == "401":
                print("    FATAL: Auth failed. Aborting.")
                return fetched
            if results:
                cited_by.extend(results)

            time.sleep(0.15)

        with open(os.path.join(sub_dir, "citing.json"), "w") as f:
            json.dump(citing, f, indent=2)
        with open(os.path.join(sub_dir, "cited_by.json"), "w") as f:
            json.dump(cited_by, f, indent=2)

        write_marker(sub_dir, {
            "docket_id": docket_id,
            "citing_count": len(citing),
            "cited_by_count": len(cited_by),
            "cluster_ids": list(cluster_ids),
        })
        fetched += 1

    elapsed = time.time() - start
    print(f"\nCitations done: {fetched} fetched, {skipped} skipped, {failed} failed ({elapsed/60:.1f} min)")
    return fetched


# ── Phase 8: Oral Arguments ──────────────────────────────────────

def enrich_oral_arguments(cases, token):
    print(f"\n{'=' * 60}")
    print(f"PHASE 8: ORAL ARGUMENTS ({len(cases):,} cases)")
    print("=" * 60)

    fetched = skipped = failed = 0
    start = time.time()

    for i, (case_dir, docket_id, docket) in enumerate(cases, 1):
        if i % 25 == 0 or i == 1:
            progress_line(i, len(cases), fetched, skipped, failed, start)

        if is_phase_done(case_dir, "oral_arguments"):
            skipped += 1
            continue

        sub_dir = os.path.join(case_dir, "oral_arguments")
        os.makedirs(sub_dir, exist_ok=True)

        url = f"{CL_API}/audio/?docket={docket_id}&format=json"
        results, err = api_get_all_pages(url, token, max_pages=10)

        if err:
            if err == "401":
                print("    FATAL: Auth failed. Aborting.")
                return fetched
            failed += 1
            continue

        with open(os.path.join(sub_dir, "audio.json"), "w") as f:
            json.dump(results or [], f, indent=2)

        write_marker(sub_dir, {
            "docket_id": docket_id,
            "audio_count": len(results or []),
        })
        fetched += 1
        time.sleep(0.15)

    elapsed = time.time() - start
    print(f"\nOral arguments done: {fetched} fetched, {skipped} skipped, {failed} failed ({elapsed/60:.1f} min)")
    return fetched


# ── Phase 9: Judge Profiles ──────────────────────────────────────

def enrich_judge_profiles(cases, token):
    print(f"\n{'=' * 60}")
    print(f"PHASE 9: JUDGE PROFILES ({len(cases):,} cases)")
    print("=" * 60)

    person_cache = {}
    fetched = skipped = failed = 0
    start = time.time()

    for i, (case_dir, docket_id, docket) in enumerate(cases, 1):
        if i % 25 == 0 or i == 1:
            progress_line(i, len(cases), fetched, skipped, failed, start)

        if is_phase_done(case_dir, "judge_profiles"):
            skipped += 1
            continue

        sub_dir = os.path.join(case_dir, "judge_profiles")
        os.makedirs(sub_dir, exist_ok=True)

        full_docket_path = os.path.join(case_dir, "full_docket", "docket_full.json")
        person_urls = set()

        if os.path.isfile(full_docket_path):
            with open(full_docket_path) as f:
                fd = json.load(f)
            for field in ["assigned_to", "referred_to"]:
                purl = fd.get(field)
                if purl and isinstance(purl, str) and "/people/" in purl:
                    person_urls.add(purl)
            for panel_url in fd.get("panel", []):
                if isinstance(panel_url, str) and "/people/" in panel_url:
                    person_urls.add(panel_url)

        judge_names = set()
        for field in ["assigned_to_str", "referred_to_str"]:
            name = docket.get(field, "")
            if name and name.strip():
                judge_names.add(name.strip())

        profiles = {}
        for purl in person_urls:
            if purl in person_cache:
                profiles[purl] = person_cache[purl]
                continue
            if not purl.startswith("http"):
                purl = f"https://www.courtlistener.com{purl}"
            data, err = api_get(purl + "?format=json", token)
            if err == "401":
                print("    FATAL: Auth failed. Aborting.")
                return fetched
            if data:
                person_cache[purl] = data
                profiles[purl] = data
            time.sleep(0.15)

        if not profiles and judge_names:
            for name in judge_names:
                last_name = name.split()[-1]
                url = f"{CL_API}/people/?name_last={urllib.parse.quote(last_name)}&format=json"
                results, err = api_get_all_pages(url, token, max_pages=3)
                if err == "401":
                    print("    FATAL: Auth failed. Aborting.")
                    return fetched
                if results:
                    for person in results:
                        pid = person.get("id", "unknown")
                        profiles[f"person_{pid}"] = person
                time.sleep(0.15)

        for key, profile in profiles.items():
            pid = profile.get("id", "unknown")
            with open(os.path.join(sub_dir, f"person_{pid}.json"), "w") as f:
                json.dump(profile, f, indent=2)

        write_marker(sub_dir, {
            "docket_id": docket_id,
            "profiles_found": len(profiles),
            "judge_names": list(judge_names),
        })
        fetched += 1

    elapsed = time.time() - start
    print(f"\nJudge profiles done: {fetched} fetched, {skipped} skipped, {failed} failed ({elapsed/60:.1f} min)")
    print(f"  Person cache: {len(person_cache)} unique judges")
    return fetched


# ── Phase 10: Financial Disclosures ──────────────────────────────

def enrich_financial_disclosures(cases, token):
    print(f"\n{'=' * 60}")
    print(f"PHASE 10: FINANCIAL DISCLOSURES ({len(cases):,} cases)")
    print("=" * 60)

    judge_cache = {}
    fetched = skipped = failed = 0
    start = time.time()

    for i, (case_dir, docket_id, docket) in enumerate(cases, 1):
        if i % 25 == 0 or i == 1:
            progress_line(i, len(cases), fetched, skipped, failed, start)

        if is_phase_done(case_dir, "financial_disclosures"):
            skipped += 1
            continue

        sub_dir = os.path.join(case_dir, "financial_disclosures")
        os.makedirs(sub_dir, exist_ok=True)

        person_ids = set()
        jp_dir = os.path.join(case_dir, "judge_profiles")
        if os.path.isdir(jp_dir):
            for f in os.listdir(jp_dir):
                if f.startswith("person_") and f.endswith(".json") and f != "_done.json":
                    pid = f.replace("person_", "").replace(".json", "")
                    person_ids.add(pid)

        judge_names = set()
        for field in ["assigned_to_str", "referred_to_str"]:
            name = docket.get(field, "")
            if name and name.strip():
                judge_names.add(name.strip())

        disclosures = []

        for pid in person_ids:
            cache_key = f"pid_{pid}"
            if cache_key in judge_cache:
                results = judge_cache[cache_key]
            else:
                url = f"{CL_API}/financial-disclosures/?person={pid}&format=json"
                results, err = api_get_all_pages(url, token, max_pages=5)
                if err == "401":
                    print("    FATAL: Auth failed. Aborting.")
                    return fetched
                judge_cache[cache_key] = results or []
                results = results or []
                time.sleep(0.15)
            disclosures.extend(results)

        if not disclosures and judge_names:
            for name in judge_names:
                cache_key = f"name_{name}"
                if cache_key in judge_cache:
                    results = judge_cache[cache_key]
                else:
                    last_name = name.split()[-1]
                    url = f"{CL_API}/financial-disclosures/?person__name_last={urllib.parse.quote(last_name)}&format=json"
                    results, err = api_get_all_pages(url, token, max_pages=5)
                    if err == "401":
                        print("    FATAL: Auth failed. Aborting.")
                        return fetched
                    judge_cache[cache_key] = results or []
                    results = results or []
                    time.sleep(0.15)
                disclosures.extend(results)

        with open(os.path.join(sub_dir, "disclosures.json"), "w") as f:
            json.dump(disclosures, f, indent=2)

        write_marker(sub_dir, {
            "docket_id": docket_id,
            "disclosures_found": len(disclosures),
            "person_ids": list(person_ids),
            "judge_names": list(judge_names),
        })
        fetched += 1

    elapsed = time.time() - start
    print(f"\nFinancial disclosures done: {fetched} fetched, {skipped} skipped, {failed} failed ({elapsed/60:.1f} min)")
    return fetched


# ── CLI ────────────────────────────────────────────────────────────

PHASES = {
    "full_docket": enrich_full_docket,
    "docket_entries": enrich_docket_entries,
    "parties": enrich_parties,
    "attorneys": enrich_attorneys,
    "opinions": enrich_opinions,
    "recap_documents": enrich_recap_documents,
    "citations": enrich_citations,
    "oral_arguments": enrich_oral_arguments,
    "judge_profiles": enrich_judge_profiles,
    "financial_disclosures": enrich_financial_disclosures,
}

def report(cases):
    """Print enrichment status report."""
    layers = list(PHASES.keys())
    print(f"\n{'=' * 60}")
    print(f"ENRICHMENT REPORT — {len(cases)} cases")
    print("=" * 60)
    for layer in layers:
        done = sum(1 for cd, _, _ in cases if is_phase_done(cd, layer))
        pct = done / max(len(cases), 1) * 100
        bar = "#" * int(pct / 5) + "." * (20 - int(pct / 5))
        print(f"  {layer:30s} [{bar}] {done:>5}/{len(cases)} ({pct:.0f}%)")

    # Docket entries detail
    total_entries = total_docs = docs_text = 0
    for cd, _, _ in cases:
        marker = os.path.join(cd, "docket_entries", "_done.json")
        if os.path.isfile(marker):
            try:
                m = json.load(open(marker))
                if m.get("status") == "ok":
                    total_entries += m.get("entry_count", 0)
                    total_docs += m.get("recap_doc_count", 0)
                    docs_text += m.get("docs_with_text", 0)
            except Exception:
                pass

    # Parties detail
    total_parties = 0
    for cd, _, _ in cases:
        marker = os.path.join(cd, "parties", "_done.json")
        if os.path.isfile(marker):
            try:
                m = json.load(open(marker))
                if m.get("status") == "ok":
                    total_parties += m.get("party_count", 0)
            except Exception:
                pass

    # Attorneys detail
    total_attorneys = 0
    for cd, _, _ in cases:
        marker = os.path.join(cd, "attorneys", "_done.json")
        if os.path.isfile(marker):
            try:
                m = json.load(open(marker))
                if m.get("status") == "ok":
                    total_attorneys += m.get("attorney_count", 0)
            except Exception:
                pass

    # Opinions detail
    total_clusters = total_opinions = 0
    for cd, _, _ in cases:
        marker = os.path.join(cd, "opinions", "_done.json")
        if os.path.isfile(marker):
            try:
                m = json.load(open(marker))
                if m.get("status") == "ok":
                    total_clusters += m.get("cluster_count", 0)
                    total_opinions += m.get("opinion_count", 0)
            except Exception:
                pass

    # RECAP docs detail
    total_recap = recap_available = 0
    for cd, _, _ in cases:
        marker = os.path.join(cd, "recap_documents", "_done.json")
        if os.path.isfile(marker):
            try:
                m = json.load(open(marker))
                if m.get("status") == "ok":
                    total_recap += m.get("document_count", 0)
                    recap_available += m.get("available_in_recap", 0)
            except Exception:
                pass

    print(f"\n  --- DATA SUMMARY ---")
    print(f"  Docket entries:    {total_entries:,} entries, {total_docs:,} docs, {docs_text:,} with text")
    print(f"  Parties:           {total_parties:,}")
    print(f"  Attorneys:         {total_attorneys:,}")
    print(f"  Opinion clusters:  {total_clusters:,} clusters, {total_opinions:,} opinions")
    print(f"  RECAP documents:   {total_recap:,} total, {recap_available:,} available")

    mb = _stats["bytes_downloaded"] / 1024 / 1024
    print(f"\n  API calls: {_stats['api_calls']:,}")
    print(f"  API errors: {_stats['api_errors']:,}")
    print(f"  Downloaded: {mb:.1f} MB")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Enrich golden set with CourtListener data")
    parser.add_argument("phase", choices=list(PHASES.keys()) + ["all"])
    parser.add_argument("--limit", type=int, default=0,
                        help="Only process first N cases (0=all)")
    parser.add_argument("--clean-bad-markers", action="store_true",
                        help="Remove _done.json markers that lack status=ok")
    args = parser.parse_args()

    token = os.environ.get("CL_API_TOKEN", "") or os.environ.get("COURTLISTENER_TOKEN", "")
    if not token:
        print("FATAL: CL_API_TOKEN or COURTLISTENER_TOKEN required")
        sys.exit(1)
    print(f"Using API token (length={len(token)})")

    if args.clean_bad_markers:
        cleaned = 0
        for root, dirs, files in os.walk(GOLDEN_DIR):
            if "_done.json" in files:
                marker = os.path.join(root, "_done.json")
                try:
                    with open(marker) as f:
                        m = json.load(f)
                    if m.get("status") != "ok":
                        os.remove(marker)
                        cleaned += 1
                except Exception:
                    os.remove(marker)
                    cleaned += 1
        print(f"Cleaned {cleaned} invalid markers")

    cases = find_golden_cases()
    if args.limit > 0:
        cases = cases[:args.limit]
    print(f"Processing {len(cases):,} cases\n")

    print("Testing API...")
    test_data, test_err = api_get(f"{CL_API}/courts/?format=json&page_size=1", token)
    if test_err:
        print(f"FATAL: API test failed: {test_err}")
        sys.exit(1)
    print(f"API OK\n")

    if args.phase == "all":
        phases_to_run = list(PHASES.keys())
    else:
        phases_to_run = [args.phase]

    for phase_name in phases_to_run:
        fn = PHASES[phase_name]
        fn(cases, token)

    report(cases)


if __name__ == "__main__":
    main()
