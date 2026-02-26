#!/usr/bin/env python3
"""
Build golden_set/: top 100 cases per NOS category ranked by opinion cluster data.

Option B pipeline:
  Phase 1 (clusters):  Stream opinion-clusters CSV, match to our 275K docket IDs
  Phase 2 (score):     Score from cluster data only (citations, published, SCOTUS),
                        build golden_set/ with top 100 per category
  Phase 3 (opinions):  API-fetch full opinions for just the ~1,100 golden set cases

State is persisted between phases in --state-dir (default /tmp/golden_state).
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime
from io import TextIOWrapper

# CourtListener CSVs have huge HTML fields (headmatter, syllabus, etc.)
csv.field_size_limit(10 * 1024 * 1024)  # 10 MB

# Must match filter_bulk_dockets.py
TARGET_NOS = {
    "850": "securities",
    "830": "patent",
    "840": "trademark",
    "410": "antitrust",
    "160": "stockholders",
    "470": "rico",
    "880": "trade_secret",
    "190": "other_contract",
    "110": "insurance",
    "430": "banks",
    "893": "environmental",
}

TOP_N = 100
OUTPUT_DIR = "golden_set"
CL_API = "https://www.courtlistener.com/api/rest/v4"


def sanitize_dirname(name, max_len=50):
    """Safe directory name from case name."""
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'\s+', '_', name.strip())
    return name[:max_len] or "unnamed"


def load_pass1_data():
    """Load docket IDs and metadata from cases2/."""
    print("Loading pass 1 data from cases2/...")
    docket_ids = set()
    docket_data = {}
    docket_nos = {}

    for nos_code, nos_label in TARGET_NOS.items():
        filepath = f"cases2/metadata/{nos_label}.json"
        if not os.path.exists(filepath):
            print(f"  WARNING: {filepath} not found")
            continue

        with open(filepath) as f:
            cases = json.load(f)

        for case in cases:
            did = str(case.get("id", ""))
            if did:
                docket_ids.add(did)
                docket_data[did] = case
                docket_nos[did] = nos_code

        print(f"  {nos_code} {nos_label:20s}: {len(cases):>8,}")

    print(f"  {'TOTAL':>24s}: {len(docket_ids):>8,}")
    return docket_ids, docket_data, docket_nos


def api_get(url, token=None, retries=3, backoff=2):
    """GET from CourtListener API with retries."""
    headers = {"User-Agent": "Ameen-GoldenSet/1.0"}
    if token:
        headers["Authorization"] = f"Token {token}"

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:  # rate limited
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


# ── Phase 1: Clusters ──────────────────────────────────────────────

def phase_clusters(state_dir):
    docket_ids, docket_data, docket_nos = load_pass1_data()

    # Persist for later phases
    with open(f"{state_dir}/docket_data.json", "w") as f:
        json.dump(docket_data, f)
    with open(f"{state_dir}/docket_nos.json", "w") as f:
        json.dump(docket_nos, f)

    print("\n" + "=" * 60)
    print("PHASE 1: STREAMING CLUSTERS CSV")
    print("=" * 60)

    clusters_by_docket = defaultdict(list)
    cluster_ids = set()
    total = 0
    matched = 0
    start = time.time()

    wrapper = TextIOWrapper(sys.stdin.buffer, encoding='utf-8', errors='replace')
    reader = csv.DictReader(wrapper)

    if reader.fieldnames:
        print(f"Columns ({len(reader.fieldnames)}): {', '.join(reader.fieldnames[:10])}...")
        sys.stdout.flush()

    errors = 0
    for row in reader:
        try:
            total += 1
            if total % 500_000 == 0:
                elapsed = time.time() - start
                print(f"  [{total/1e6:.1f}M] {matched:,} matched, {errors} errors | {elapsed/60:.1f} min")
                sys.stdout.flush()

            docket_id = str(row.get("docket_id", ""))
            if docket_id not in docket_ids:
                continue

            cluster_id = str(row.get("id", ""))
            cluster_ids.add(cluster_id)

            clusters_by_docket[docket_id].append({
                "id": cluster_id,
                "docket_id": docket_id,
                "date_filed": row.get("date_filed", ""),
                "case_name": row.get("case_name", ""),
                "judges": row.get("judges", ""),
                "precedential_status": row.get("precedential_status", ""),
                "citation_count": int(row.get("citation_count", 0) or 0),
                "scdb_id": row.get("scdb_id", ""),
                "nature_of_suit": row.get("nature_of_suit", ""),
                "syllabus": row.get("syllabus", ""),
            })
            matched += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  WARNING row {total}: {e}", file=sys.stderr)

    elapsed = time.time() - start
    print(f"\nPhase 1 done: {total:,} rows scanned, {matched:,} clusters matched, {errors} errors")
    print(f"Unique dockets with clusters: {len(clusters_by_docket):,}")
    print(f"Time: {elapsed/60:.1f} min")

    with open(f"{state_dir}/clusters_by_docket.json", "w") as f:
        json.dump(dict(clusters_by_docket), f)
    with open(f"{state_dir}/cluster_ids.json", "w") as f:
        json.dump(list(cluster_ids), f)

    print(f"State saved ({len(cluster_ids):,} cluster IDs)")


# ── Phase 2: Score + Build (clusters-only scoring) ────────────────

def phase_score(state_dir):
    print("Loading state from Phase 1...")
    with open(f"{state_dir}/docket_data.json") as f:
        docket_data = json.load(f)
    with open(f"{state_dir}/docket_nos.json") as f:
        docket_nos = json.load(f)
    with open(f"{state_dir}/clusters_by_docket.json") as f:
        clusters_by_docket = json.load(f)

    print(f"  {len(docket_data):,} dockets, "
          f"{sum(len(v) for v in clusters_by_docket.values()):,} clusters")

    # ── Score (clusters only — no opinions bulk needed) ──
    print("\n" + "=" * 60)
    print("SCORING (clusters-only: citations + published + SCOTUS)")
    print("=" * 60)

    scores = {}
    details = {}

    for did, nos_code in docket_nos.items():
        clusters = clusters_by_docket.get(did, [])
        if not clusters:
            continue

        published = 0
        unpublished = 0
        total_citations = 0
        has_scotus = False

        for cl in clusters:
            status = (cl.get("precedential_status") or "").lower()
            if "published" in status or "precedential" in status:
                published += 1
            elif "unpublished" in status:
                unpublished += 1

            total_citations += cl.get("citation_count", 0)

            if cl.get("scdb_id"):
                has_scotus = True

        score = (
            published * 10
            + unpublished * 2
            + total_citations * 5
            + (100 if has_scotus else 0)
        )

        scores[did] = score
        details[did] = {
            "score": score,
            "published_opinions": published,
            "unpublished_opinions": unpublished,
            "total_citations": total_citations,
            "total_clusters": len(clusters),
            "has_scotus": has_scotus,
        }

    print(f"Scored {len(scores):,} cases (those with >= 1 opinion cluster)")

    if scores:
        vals = sorted(scores.values(), reverse=True)
        print(f"Score range: {vals[-1]} - {vals[0]}")
        print(f"Median: {vals[len(vals)//2]}")
        print(f"Top 10: {vals[:10]}")

    # ── Build golden_set/ ──
    print("\n" + "=" * 60)
    print("BUILDING GOLDEN SET")
    print("=" * 60)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Group by NOS
    nos_cases = defaultdict(list)
    for did, score in scores.items():
        nos_code = docket_nos.get(did)
        if nos_code:
            nos_cases[nos_code].append((did, score))

    golden_index = {
        "created_at": datetime.utcnow().isoformat(),
        "top_n_per_category": TOP_N,
        "scoring_formula": "published*10 + unpublished*2 + citations*5 + scotus*100",
        "categories": {},
    }

    total_golden = 0
    # Collect all golden cluster IDs for Phase 3
    golden_cluster_ids = {}  # cluster_id -> case_dir path

    for nos_code in sorted(TARGET_NOS.keys()):
        nos_label = TARGET_NOS[nos_code]
        cases = nos_cases.get(nos_code, [])
        cases.sort(key=lambda x: x[1], reverse=True)
        top = cases[:TOP_N]

        cat_dir = os.path.join(OUTPUT_DIR, nos_label)
        os.makedirs(cat_dir, exist_ok=True)

        print(f"\n{nos_code} {nos_label}: {len(cases):,} scored -> top {len(top)}")

        cat_index = []

        for rank, (did, score) in enumerate(top, 1):
            docket = docket_data.get(did, {})
            case_name = docket.get("case_name", f"case_{did}")
            safe_name = sanitize_dirname(case_name)
            folder = f"{rank:03d}_{did}_{safe_name}"
            case_dir = os.path.join(cat_dir, folder)
            os.makedirs(case_dir, exist_ok=True)

            # Docket metadata (from cases2 data, enriched with score)
            enriched = dict(docket)
            enriched["_score"] = score
            enriched["_score_details"] = details.get(did, {})
            enriched["_rank_in_category"] = rank
            enriched["_nos_category"] = nos_label
            with open(os.path.join(case_dir, "docket.json"), "w") as f:
                json.dump(enriched, f, indent=2)

            # Each cluster gets its own subfolder; opinions added in Phase 3
            clusters = clusters_by_docket.get(did, [])
            if clusters:
                ops_dir = os.path.join(case_dir, "opinions")
                os.makedirs(ops_dir, exist_ok=True)

                for cl in clusters:
                    cl_dir = os.path.join(ops_dir, f"cluster_{cl['id']}")
                    os.makedirs(cl_dir, exist_ok=True)

                    with open(os.path.join(cl_dir, "cluster.json"), "w") as f:
                        json.dump(cl, f, indent=2)

                    golden_cluster_ids[cl["id"]] = cl_dir

            # Log top 3 per category
            if rank <= 3:
                d = details.get(did, {})
                print(f"  #{rank}: {case_name[:55]} "
                      f"(score={score}, pub={d.get('published_opinions',0)}, "
                      f"cite={d.get('total_citations',0)})")

            cat_index.append({
                "rank": rank,
                "docket_id": did,
                "case_name": case_name,
                "court_id": docket.get("court_id", ""),
                "date_filed": docket.get("date_filed", ""),
                "score": score,
                "score_details": details.get(did, {}),
                "folder": folder,
            })
            total_golden += 1

        with open(os.path.join(cat_dir, "index.json"), "w") as f:
            json.dump(cat_index, f, indent=2)

        golden_index["categories"][nos_label] = {
            "nos_code": nos_code,
            "total_with_opinions": len(cases),
            "top_n_saved": len(top),
            "top_score": top[0][1] if top else 0,
            "cutoff_score": top[-1][1] if top else 0,
        }

    golden_index["total_golden_cases"] = total_golden
    with open(os.path.join(OUTPUT_DIR, "index.json"), "w") as f:
        json.dump(golden_index, f, indent=2)

    # Save golden cluster IDs for Phase 3
    with open(f"{state_dir}/golden_cluster_paths.json", "w") as f:
        json.dump(golden_cluster_ids, f)

    print(f"\n{'=' * 60}")
    print(f"GOLDEN SET: {total_golden} cases across {len(TARGET_NOS)} categories")
    print(f"Cluster files to enrich in Phase 3: {len(golden_cluster_ids):,}")
    print(f"Saved to {OUTPUT_DIR}/")
    print("=" * 60)


# ── Phase 3: API-fetch opinions for golden set only ───────────────

def phase_opinions(state_dir):
    """Fetch full opinion data via CourtListener API for golden set clusters only.

    Resumable: skips clusters that already have opinion_*.json files.
    """
    token = os.environ.get("CL_API_TOKEN", "")

    with open(f"{state_dir}/golden_cluster_paths.json") as f:
        golden_cluster_paths = json.load(f)

    total = len(golden_cluster_paths)
    print(f"\n{'=' * 60}")
    print(f"PHASE 3: API-FETCH OPINIONS FOR {total:,} GOLDEN SET CLUSTERS")
    print("=" * 60)
    if token:
        print("  Using API token (5,000 req/hr limit)")
    else:
        print("  WARNING: No CL_API_TOKEN set, using anonymous rate limit")

    # Check how many already fetched (resumability)
    already_done = 0
    for cluster_id, cluster_dir in golden_cluster_paths.items():
        if os.path.isdir(cluster_dir):
            existing = [f for f in os.listdir(cluster_dir) if f.startswith("opinion_")]
            if existing:
                already_done += 1

    remaining = total - already_done
    print(f"  Already fetched: {already_done:,}, remaining: {remaining:,}")
    sys.stdout.flush()

    fetched = 0
    skipped = 0
    failed = 0
    start = time.time()

    for i, (cluster_id, cluster_dir) in enumerate(golden_cluster_paths.items(), 1):
        if (i - skipped) % 50 == 0 or i == 1:
            elapsed = time.time() - start
            rate = fetched / max(elapsed, 1) * 3600
            print(f"  [{i}/{total}] {fetched} fetched, {skipped} skipped, {failed} failed | "
                  f"{elapsed/60:.1f} min | ~{rate:.0f} req/hr")
            sys.stdout.flush()

        if not os.path.isdir(cluster_dir):
            failed += 1
            continue

        # Skip if already has opinion files (resumable)
        existing = [f for f in os.listdir(cluster_dir) if f.startswith("opinion_")]
        if existing:
            skipped += 1
            continue

        # Fetch opinions for this cluster
        url = f"{CL_API}/opinions/?cluster={cluster_id}&format=json"
        data = api_get(url, token=token)

        if data is None:
            failed += 1
            continue

        opinions = data.get("results", [])

        # Write a marker even if no opinions, so we don't re-fetch
        if not opinions:
            with open(os.path.join(cluster_dir, "opinion_none.json"), "w") as f:
                json.dump({"_note": "no opinions found via API"}, f)
            fetched += 1
            continue

        # Each opinion gets its own file in the cluster subfolder
        for op in opinions:
            op_id = op.get("id", "unknown")
            op_type = (op.get("type", "") or "").replace(" ", "_")
            filename = f"opinion_{op_id}_{op_type}.json" if op_type else f"opinion_{op_id}.json"

            opinion_record = {
                "id": op_id,
                "cluster_id": cluster_id,
                "type": op.get("type", ""),
                "author_str": op.get("author_str", ""),
                "per_curiam": op.get("per_curiam", False),
                "page_count": op.get("page_count"),
                "download_url": op.get("download_url", ""),
                "sha1": op.get("sha1", ""),
                "plain_text": op.get("plain_text", ""),
                "html_with_citations": op.get("html_with_citations", ""),
            }

            with open(os.path.join(cluster_dir, filename), "w") as f:
                json.dump(opinion_record, f, indent=2)

        fetched += 1

        # Respect rate limits: ~1 req/sec for anonymous, faster with token
        if not token:
            time.sleep(0.8)
        else:
            time.sleep(0.3)

    elapsed = time.time() - start
    print(f"\nPhase 3 done: {fetched:,} fetched, {skipped:,} skipped, {failed:,} failed")
    print(f"Time: {elapsed/60:.1f} min")


# ── CLI ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["clusters", "score", "opinions"])
    parser.add_argument("--state-dir", default="/tmp/golden_state")
    args = parser.parse_args()

    os.makedirs(args.state_dir, exist_ok=True)

    if args.phase == "clusters":
        phase_clusters(args.state_dir)
    elif args.phase == "score":
        phase_score(args.state_dir)
    elif args.phase == "opinions":
        phase_opinions(args.state_dir)


if __name__ == "__main__":
    main()
