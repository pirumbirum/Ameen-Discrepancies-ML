#!/usr/bin/env python3
"""
Enrich golden_set/ cases with additional CourtListener API data.

5 enrichment layers (each run independently):
  1. docket_entries   — full timeline of every filing
  2. recap_documents  — available RECAP filing metadata
  3. citations        — citation graph (citing + cited_by)
  4. parties          — parties and attorneys
  5. financial_disclosures — judge financial disclosures

All phases are resumable: skip cases that already have the subfolder populated.
Periodic git checkpoints save progress.

Usage:
  python3 scripts/enrich_golden_set.py docket_entries --commit-every 100
  python3 scripts/enrich_golden_set.py all --commit-every 100
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

CL_API = "https://www.courtlistener.com/api/rest/v4"
GOLDEN_DIR = "golden_set"


def api_get(url, token=None, retries=3, backoff=2):
    """GET from CourtListener API with retries + pagination handling."""
    headers = {"User-Agent": "Ameen-Enrich/1.0"}
    if token:
        headers["Authorization"] = f"Token {token}"

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = backoff * (2 ** attempt)
                print(f"    Rate limited, waiting {wait}s...")
                time.sleep(wait)
            elif e.code == 404:
                return None
            else:
                print(f"    HTTP {e.code} for {url}, retry {attempt+1}/{retries}")
                time.sleep(backoff * (2 ** attempt))
        except Exception as e:
            print(f"    Error: {e}, retry {attempt+1}/{retries}")
            time.sleep(backoff * (2 ** attempt))
    return None


def api_get_all_pages(url, token=None, max_pages=50):
    """Fetch all pages from a paginated CL API endpoint."""
    all_results = []
    page = 0
    while url and page < max_pages:
        data = api_get(url, token=token)
        if data is None:
            break
        all_results.extend(data.get("results", []))
        url = data.get("next")
        page += 1
        if url:
            time.sleep(0.2)  # brief pause between pages
    return all_results


def git_checkpoint(msg):
    """Git add + commit + push golden_set/ to save progress."""
    try:
        subprocess.run(["git", "add", "golden_set/"], check=True, capture_output=True)
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], capture_output=True
        )
        if result.returncode == 0:
            return
        subprocess.run(
            ["git", "commit", "-m", msg], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "push"], check=True, capture_output=True, timeout=60
        )
        print(f"    [checkpoint] {msg}")
    except Exception as e:
        print(f"    [checkpoint] WARNING: {e}")


def find_golden_cases():
    """Walk golden_set/ and return list of (case_dir, docket_id, docket_data)."""
    cases = []
    for cat in sorted(os.listdir(GOLDEN_DIR)):
        cat_dir = os.path.join(GOLDEN_DIR, cat)
        if not os.path.isdir(cat_dir) or cat == "index.json":
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


def is_phase_done(case_dir, subfolder, marker_file="_done.json"):
    """Check if a phase is already completed for a case."""
    sub_dir = os.path.join(case_dir, subfolder)
    return os.path.isfile(os.path.join(sub_dir, marker_file))


def write_marker(sub_dir, stats):
    """Write a _done.json marker to indicate phase completion."""
    with open(os.path.join(sub_dir, "_done.json"), "w") as f:
        json.dump(stats, f, indent=2)


# ── Phase 1: Docket Entries ───────────────────────────────────────

def enrich_docket_entries(cases, token, commit_every):
    print(f"\n{'=' * 60}")
    print(f"ENRICHING: DOCKET ENTRIES ({len(cases):,} cases)")
    print("=" * 60)

    fetched = 0
    skipped = 0
    failed = 0
    start = time.time()

    for i, (case_dir, docket_id, docket) in enumerate(cases, 1):
        if i % 25 == 0 or i == 1:
            elapsed = time.time() - start
            rate = fetched / max(elapsed, 1) * 3600
            print(f"  [{i}/{len(cases)}] {fetched} fetched, {skipped} skipped, {failed} failed | "
                  f"{elapsed/60:.1f} min | ~{rate:.0f} req/hr")
            sys.stdout.flush()

        sub_dir = os.path.join(case_dir, "docket_entries")
        if is_phase_done(case_dir, "docket_entries"):
            skipped += 1
            continue

        os.makedirs(sub_dir, exist_ok=True)

        url = f"{CL_API}/docket-entries/?docket={docket_id}&format=json&order_by=date_filed"
        entries = api_get_all_pages(url, token=token, max_pages=100)

        if entries is None:
            failed += 1
            continue

        with open(os.path.join(sub_dir, "entries.json"), "w") as f:
            json.dump(entries, f, indent=2)

        write_marker(sub_dir, {"count": len(entries), "docket_id": docket_id})
        fetched += 1

        if commit_every > 0 and fetched % commit_every == 0:
            git_checkpoint(f"Docket entries: {fetched}/{len(cases)} cases")

        if not token:
            time.sleep(0.8)
        else:
            time.sleep(0.3)

    elapsed = time.time() - start
    print(f"\nDocket entries done: {fetched} fetched, {skipped} skipped, {failed} failed ({elapsed/60:.1f} min)")
    return fetched


# ── Phase 2: RECAP Documents ─────────────────────────────────────

def enrich_recap_documents(cases, token, commit_every):
    print(f"\n{'=' * 60}")
    print(f"ENRICHING: RECAP DOCUMENTS ({len(cases):,} cases)")
    print("=" * 60)

    fetched = 0
    skipped = 0
    failed = 0
    start = time.time()

    for i, (case_dir, docket_id, docket) in enumerate(cases, 1):
        if i % 25 == 0 or i == 1:
            elapsed = time.time() - start
            rate = fetched / max(elapsed, 1) * 3600
            print(f"  [{i}/{len(cases)}] {fetched} fetched, {skipped} skipped, {failed} failed | "
                  f"{elapsed/60:.1f} min | ~{rate:.0f} req/hr")
            sys.stdout.flush()

        sub_dir = os.path.join(case_dir, "recap_documents")
        if is_phase_done(case_dir, "recap_documents"):
            skipped += 1
            continue

        os.makedirs(sub_dir, exist_ok=True)

        url = f"{CL_API}/recap-documents/?docket_entry__docket={docket_id}&format=json"
        docs = api_get_all_pages(url, token=token, max_pages=100)

        if docs is None:
            failed += 1
            continue

        # Save each doc separately
        for doc in docs:
            doc_id = doc.get("id", "unknown")
            with open(os.path.join(sub_dir, f"doc_{doc_id}.json"), "w") as f:
                json.dump(doc, f, indent=2)

        write_marker(sub_dir, {"count": len(docs), "docket_id": docket_id})
        fetched += 1

        if commit_every > 0 and fetched % commit_every == 0:
            git_checkpoint(f"RECAP docs: {fetched}/{len(cases)} cases")

        if not token:
            time.sleep(0.8)
        else:
            time.sleep(0.3)

    elapsed = time.time() - start
    print(f"\nRECAP docs done: {fetched} fetched, {skipped} skipped, {failed} failed ({elapsed/60:.1f} min)")
    return fetched


# ── Phase 3: Citations ────────────────────────────────────────────

def enrich_citations(cases, token, commit_every):
    print(f"\n{'=' * 60}")
    print(f"ENRICHING: CITATIONS ({len(cases):,} cases)")
    print("=" * 60)

    fetched = 0
    skipped = 0
    failed = 0
    start = time.time()

    for i, (case_dir, docket_id, docket) in enumerate(cases, 1):
        if i % 25 == 0 or i == 1:
            elapsed = time.time() - start
            rate = fetched / max(elapsed, 1) * 3600
            print(f"  [{i}/{len(cases)}] {fetched} fetched, {skipped} skipped, {failed} failed | "
                  f"{elapsed/60:.1f} min | ~{rate:.0f} req/hr")
            sys.stdout.flush()

        sub_dir = os.path.join(case_dir, "citations")
        if is_phase_done(case_dir, "citations"):
            skipped += 1
            continue

        os.makedirs(sub_dir, exist_ok=True)

        # Get cluster IDs for this case from opinions/ subfolder
        opinions_dir = os.path.join(case_dir, "opinions")
        cluster_ids = []
        if os.path.isdir(opinions_dir):
            for cl_folder in os.listdir(opinions_dir):
                if cl_folder.startswith("cluster_"):
                    cluster_ids.append(cl_folder.replace("cluster_", ""))

        citing = []   # cases that cite opinions in this docket
        cited_by = [] # cases that opinions in this docket cite

        for cid in cluster_ids:
            # Opinions citing this cluster
            url = f"{CL_API}/citations/?cited_opinion__cluster={cid}&format=json"
            results = api_get_all_pages(url, token=token, max_pages=20)
            if results:
                citing.extend(results)

            # Opinions this cluster cites
            url = f"{CL_API}/citations/?citing_opinion__cluster={cid}&format=json"
            results = api_get_all_pages(url, token=token, max_pages=20)
            if results:
                cited_by.extend(results)

            if not token:
                time.sleep(0.5)
            else:
                time.sleep(0.2)

        with open(os.path.join(sub_dir, "citing.json"), "w") as f:
            json.dump(citing, f, indent=2)
        with open(os.path.join(sub_dir, "cited_by.json"), "w") as f:
            json.dump(cited_by, f, indent=2)

        write_marker(sub_dir, {
            "citing_count": len(citing),
            "cited_by_count": len(cited_by),
            "cluster_ids": cluster_ids,
            "docket_id": docket_id,
        })
        fetched += 1

        if commit_every > 0 and fetched % commit_every == 0:
            git_checkpoint(f"Citations: {fetched}/{len(cases)} cases")

    elapsed = time.time() - start
    print(f"\nCitations done: {fetched} fetched, {skipped} skipped, {failed} failed ({elapsed/60:.1f} min)")
    return fetched


# ── Phase 4: Parties & Attorneys ──────────────────────────────────

def enrich_parties(cases, token, commit_every):
    print(f"\n{'=' * 60}")
    print(f"ENRICHING: PARTIES & ATTORNEYS ({len(cases):,} cases)")
    print("=" * 60)

    fetched = 0
    skipped = 0
    failed = 0
    start = time.time()

    for i, (case_dir, docket_id, docket) in enumerate(cases, 1):
        if i % 25 == 0 or i == 1:
            elapsed = time.time() - start
            rate = fetched / max(elapsed, 1) * 3600
            print(f"  [{i}/{len(cases)}] {fetched} fetched, {skipped} skipped, {failed} failed | "
                  f"{elapsed/60:.1f} min | ~{rate:.0f} req/hr")
            sys.stdout.flush()

        sub_dir = os.path.join(case_dir, "parties")
        if is_phase_done(case_dir, "parties"):
            skipped += 1
            continue

        os.makedirs(sub_dir, exist_ok=True)

        # Parties
        url = f"{CL_API}/parties/?docket={docket_id}&format=json"
        parties = api_get_all_pages(url, token=token, max_pages=20)

        # Attorneys
        url = f"{CL_API}/attorneys/?docket={docket_id}&format=json"
        attorneys = api_get_all_pages(url, token=token, max_pages=20)

        with open(os.path.join(sub_dir, "parties.json"), "w") as f:
            json.dump(parties or [], f, indent=2)
        with open(os.path.join(sub_dir, "attorneys.json"), "w") as f:
            json.dump(attorneys or [], f, indent=2)

        write_marker(sub_dir, {
            "parties_count": len(parties or []),
            "attorneys_count": len(attorneys or []),
            "docket_id": docket_id,
        })
        fetched += 1

        if commit_every > 0 and fetched % commit_every == 0:
            git_checkpoint(f"Parties: {fetched}/{len(cases)} cases")

        if not token:
            time.sleep(0.8)
        else:
            time.sleep(0.3)

    elapsed = time.time() - start
    print(f"\nParties done: {fetched} fetched, {skipped} skipped, {failed} failed ({elapsed/60:.1f} min)")
    return fetched


# ── Phase 5: Financial Disclosures ────────────────────────────────

def enrich_financial_disclosures(cases, token, commit_every):
    print(f"\n{'=' * 60}")
    print(f"ENRICHING: FINANCIAL DISCLOSURES ({len(cases):,} cases)")
    print("=" * 60)

    # First, collect unique judge names from all cases' opinion clusters
    judge_cache = {}  # judge_name -> disclosure data (avoid re-fetching same judge)

    fetched = 0
    skipped = 0
    failed = 0
    start = time.time()

    for i, (case_dir, docket_id, docket) in enumerate(cases, 1):
        if i % 25 == 0 or i == 1:
            elapsed = time.time() - start
            rate = fetched / max(elapsed, 1) * 3600
            print(f"  [{i}/{len(cases)}] {fetched} fetched, {skipped} skipped, {failed} failed | "
                  f"{elapsed/60:.1f} min | ~{rate:.0f} req/hr")
            sys.stdout.flush()

        sub_dir = os.path.join(case_dir, "financial_disclosures")
        if is_phase_done(case_dir, "financial_disclosures"):
            skipped += 1
            continue

        os.makedirs(sub_dir, exist_ok=True)

        # Collect judge names from cluster metadata and docket
        judge_names = set()
        assigned = docket.get("assigned_to_str", "")
        if assigned:
            judge_names.add(assigned)
        referred = docket.get("referred_to_str", "")
        if referred:
            judge_names.add(referred)

        opinions_dir = os.path.join(case_dir, "opinions")
        if os.path.isdir(opinions_dir):
            for cl_folder in os.listdir(opinions_dir):
                cl_path = os.path.join(opinions_dir, cl_folder, "cluster.json")
                if os.path.isfile(cl_path):
                    with open(cl_path) as f:
                        cl = json.load(f)
                    judges = cl.get("judges", "")
                    if judges:
                        judge_names.add(judges)

        disclosures_found = 0
        for judge_name in judge_names:
            if not judge_name.strip():
                continue

            # Check cache
            if judge_name in judge_cache:
                results = judge_cache[judge_name]
            else:
                url = f"{CL_API}/financial-disclosures/?person__name_last={urllib.request.quote(judge_name.split()[-1])}&format=json"
                results = api_get_all_pages(url, token=token, max_pages=5)
                judge_cache[judge_name] = results or []
                if not token:
                    time.sleep(0.5)
                else:
                    time.sleep(0.2)

            if results:
                safe_name = judge_name.replace(" ", "_").replace("/", "_")[:40]
                with open(os.path.join(sub_dir, f"judge_{safe_name}.json"), "w") as f:
                    json.dump(results, f, indent=2)
                disclosures_found += len(results)

        write_marker(sub_dir, {
            "judges_searched": list(judge_names),
            "disclosures_found": disclosures_found,
            "docket_id": docket_id,
        })
        fetched += 1

        if commit_every > 0 and fetched % commit_every == 0:
            git_checkpoint(f"Financial disclosures: {fetched}/{len(cases)} cases")

    elapsed = time.time() - start
    print(f"\nFinancial disclosures done: {fetched} fetched, {skipped} skipped, {failed} failed ({elapsed/60:.1f} min)")
    print(f"  Judge cache size: {len(judge_cache)} unique judges")
    return fetched


# ── CLI ────────────────────────────────────────────────────────────

PHASES = {
    "docket_entries": enrich_docket_entries,
    "recap_documents": enrich_recap_documents,
    "citations": enrich_citations,
    "parties": enrich_parties,
    "financial_disclosures": enrich_financial_disclosures,
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=list(PHASES.keys()) + ["all"])
    parser.add_argument("--commit-every", type=int, default=0)
    args = parser.parse_args()

    token = os.environ.get("CL_API_TOKEN", "")
    if token:
        print(f"Using API token (5,000 req/hr)")
    else:
        print("WARNING: No CL_API_TOKEN — anonymous rate limits apply")

    cases = find_golden_cases()
    print(f"Found {len(cases):,} golden set cases")

    if args.phase == "all":
        phases_to_run = list(PHASES.keys())
    else:
        phases_to_run = [args.phase]

    for phase_name in phases_to_run:
        fn = PHASES[phase_name]
        count = fn(cases, token, args.commit_every)

        # Checkpoint after each phase
        if args.commit_every > 0 and count > 0:
            git_checkpoint(f"Enrichment {phase_name}: complete ({count} cases)")

    print(f"\n{'=' * 60}")
    print("ALL ENRICHMENT PHASES COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
