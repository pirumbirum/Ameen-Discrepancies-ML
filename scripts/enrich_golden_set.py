#!/usr/bin/env python3
"""
Enrich golden_set/ cases with COMPLETE CourtListener API data.

Phases (run sequentially):
  1. full_docket      — re-fetch full docket from /dockets/{id}/ (60 fields)
  2. docket_entries   — full timeline + nested RECAP docs with plain_text
  3. citations        — citation graph (citing + cited_by)
  4. oral_arguments   — oral argument audio metadata
  5. judge_profiles   — judge person records (positions, education, etc.)
  6. financial_disclosures — judge financial disclosures

All phases are resumable: skip cases that already have a valid _done.json marker.
Git checkpoints every --checkpoint-minutes (default 15).

Usage:
  python3 scripts/enrich_golden_set.py all --checkpoint-minutes 15
  python3 scripts/enrich_golden_set.py docket_entries --checkpoint-minutes 15
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

CL_API = "https://www.courtlistener.com/api/rest/v4"
GOLDEN_DIR = "golden_set"

# ── Global state ──────────────────────────────────────────────────
_stats = {"api_calls": 0, "api_errors": 0, "bytes_downloaded": 0}
_last_checkpoint = time.time()
_checkpoint_interval = 900  # seconds (15 min default, set by CLI)


def api_get(url, token, retries=4, backoff=2):
    """GET from CourtListener API with retries. Token REQUIRED (v4.3+)."""
    if not token:
        return None, "NO_TOKEN"

    headers = {
        "User-Agent": "Ameen-Enrich/2.0",
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


def git_checkpoint(msg):
    """Git add + commit + pull --rebase + push."""
    global _last_checkpoint
    try:
        subprocess.run(["git", "add", "golden_set/"], check=True, capture_output=True)
        result = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True)
        if result.returncode == 0:
            return  # nothing to commit
        subprocess.run(["git", "commit", "-m", msg], check=True, capture_output=True)
        # Rebase on remote first to handle any external commits
        subprocess.run(
            ["git", "pull", "--rebase", "origin", "HEAD"],
            capture_output=True, timeout=120
        )
        subprocess.run(["git", "push"], check=True, capture_output=True, timeout=120)
        _last_checkpoint = time.time()
        mb = _stats["bytes_downloaded"] / 1024 / 1024
        print(f"    [SAVED] {msg} | {mb:.1f} MB total")
    except Exception as e:
        print(f"    [checkpoint] WARNING: {e}")


def maybe_checkpoint(phase_name, fetched, total):
    """Checkpoint if enough time has passed since last save."""
    global _last_checkpoint
    if time.time() - _last_checkpoint >= _checkpoint_interval:
        git_checkpoint(f"{phase_name}: {fetched}/{total}")


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
    next_save = max(0, _checkpoint_interval - (time.time() - _last_checkpoint))
    print(f"  [{i}/{total}] fetched={fetched} skip={skipped} fail={failed} | "
          f"{elapsed/60:.1f}m | ~{rate:.0f}/hr | {mb:.1f}MB | save in {next_save/60:.0f}m")
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
        maybe_checkpoint("Full docket", fetched, len(cases))
        time.sleep(0.2)

    git_checkpoint(f"Phase full_docket complete ({fetched} cases)")
    elapsed = time.time() - start
    print(f"\nFull docket done: {fetched} fetched, {skipped} skipped, {failed} failed ({elapsed/60:.1f} min)")
    return fetched


# ── Phase 2: Docket Entries + RECAP text ──────────────────────────

def enrich_docket_entries(cases, token):
    print(f"\n{'=' * 60}")
    print(f"PHASE 2: DOCKET ENTRIES + RECAP TEXT ({len(cases):,} cases)")
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
        maybe_checkpoint("Docket entries", fetched, len(cases))
        time.sleep(0.2)

    git_checkpoint(f"Phase docket_entries complete ({fetched} cases)")
    elapsed = time.time() - start
    print(f"\nDocket entries done: {fetched} fetched, {skipped} skipped, {failed} failed ({elapsed/60:.1f} min)")
    return fetched


# ── Phase 3: Citations ────────────────────────────────────────────

def enrich_citations(cases, token):
    print(f"\n{'=' * 60}")
    print(f"PHASE 3: CITATIONS ({len(cases):,} cases)")
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

        opinions_dir = os.path.join(case_dir, "opinions")
        cluster_ids = []
        if os.path.isdir(opinions_dir):
            for cl_folder in os.listdir(opinions_dir):
                if cl_folder.startswith("cluster_"):
                    cluster_ids.append(cl_folder.replace("cluster_", ""))

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
            "cluster_ids": cluster_ids,
        })
        fetched += 1
        maybe_checkpoint("Citations", fetched, len(cases))

    git_checkpoint(f"Phase citations complete ({fetched} cases)")
    elapsed = time.time() - start
    print(f"\nCitations done: {fetched} fetched, {skipped} skipped, {failed} failed ({elapsed/60:.1f} min)")
    return fetched


# ── Phase 4: Oral Arguments ──────────────────────────────────────

def enrich_oral_arguments(cases, token):
    print(f"\n{'=' * 60}")
    print(f"PHASE 4: ORAL ARGUMENTS ({len(cases):,} cases)")
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
        maybe_checkpoint("Oral arguments", fetched, len(cases))
        time.sleep(0.15)

    git_checkpoint(f"Phase oral_arguments complete ({fetched} cases)")
    elapsed = time.time() - start
    print(f"\nOral arguments done: {fetched} fetched, {skipped} skipped, {failed} failed ({elapsed/60:.1f} min)")
    return fetched


# ── Phase 5: Judge Profiles ──────────────────────────────────────

def enrich_judge_profiles(cases, token):
    print(f"\n{'=' * 60}")
    print(f"PHASE 5: JUDGE PROFILES ({len(cases):,} cases)")
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
        maybe_checkpoint("Judge profiles", fetched, len(cases))

    git_checkpoint(f"Phase judge_profiles complete ({fetched} cases)")
    elapsed = time.time() - start
    print(f"\nJudge profiles done: {fetched} fetched, {skipped} skipped, {failed} failed ({elapsed/60:.1f} min)")
    print(f"  Person cache: {len(person_cache)} unique judges")
    return fetched


# ── Phase 6: Financial Disclosures ────────────────────────────────

def enrich_financial_disclosures(cases, token):
    print(f"\n{'=' * 60}")
    print(f"PHASE 6: FINANCIAL DISCLOSURES ({len(cases):,} cases)")
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
        maybe_checkpoint("Financial disclosures", fetched, len(cases))

    git_checkpoint(f"Phase financial_disclosures complete ({fetched} cases)")
    elapsed = time.time() - start
    print(f"\nFinancial disclosures done: {fetched} fetched, {skipped} skipped, {failed} failed ({elapsed/60:.1f} min)")
    return fetched


# ── CLI ────────────────────────────────────────────────────────────

PHASES = {
    "full_docket": enrich_full_docket,
    "docket_entries": enrich_docket_entries,
    "citations": enrich_citations,
    "oral_arguments": enrich_oral_arguments,
    "judge_profiles": enrich_judge_profiles,
    "financial_disclosures": enrich_financial_disclosures,
}

def main():
    global _checkpoint_interval

    parser = argparse.ArgumentParser(description="Enrich golden set with CourtListener data")
    parser.add_argument("phase", choices=list(PHASES.keys()) + ["all"])
    parser.add_argument("--checkpoint-minutes", type=int, default=15,
                        help="Git save every N minutes (default: 15)")
    parser.add_argument("--clean-bad-markers", action="store_true",
                        help="Remove _done.json markers that lack status=ok")
    args = parser.parse_args()

    _checkpoint_interval = args.checkpoint_minutes * 60
    print(f"Checkpoint interval: every {args.checkpoint_minutes} minutes")

    token = os.environ.get("CL_API_TOKEN", "")
    if not token:
        print("FATAL: CL_API_TOKEN is required (v4.3+ requires authentication)")
        sys.exit(1)
    print(f"Using API token (authenticated)")

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
        print(f"Cleaned {cleaned} invalid markers from previous runs")

    cases = find_golden_cases()
    print(f"Found {len(cases):,} golden set cases\n")

    print("Testing API connectivity...")
    test_data, test_err = api_get(f"{CL_API}/courts/?format=json&page_size=1", token)
    if test_err:
        print(f"FATAL: API test failed: {test_err}")
        sys.exit(1)
    print(f"API OK — connected to CourtListener v4\n")

    if args.phase == "all":
        phases_to_run = list(PHASES.keys())
    else:
        phases_to_run = [args.phase]

    for phase_name in phases_to_run:
        fn = PHASES[phase_name]
        fn(cases, token)

    mb = _stats["bytes_downloaded"] / 1024 / 1024
    print(f"\n{'=' * 60}")
    print(f"ALL PHASES COMPLETE")
    print(f"  API calls: {_stats['api_calls']:,}")
    print(f"  API errors: {_stats['api_errors']:,}")
    print(f"  Data downloaded: {mb:.1f} MB")
    print("=" * 60)


if __name__ == "__main__":
    main()
