#!/usr/bin/env python3
"""
Build golden_set/: top 100 cases per NOS category ranked by judicial opinion activity.

Three-phase pipeline (each reads from stdin via streaming bulk CSV):
  Phase 1 (clusters): Stream opinion-clusters CSV, match to our 275K docket IDs
  Phase 2 (opinions): Stream opinions CSV, match to clusters from Phase 1
  Phase 3 (score):    Score all cases, build golden_set/ with top 100 per category

State is persisted between phases in --state-dir (default /tmp/golden_state).
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from io import TextIOWrapper

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

    reader = csv.DictReader(
        TextIOWrapper(sys.stdin.buffer, encoding='utf-8', errors='replace')
    )

    if reader.fieldnames:
        print(f"Columns ({len(reader.fieldnames)}): {', '.join(reader.fieldnames[:10])}...")
        sys.stdout.flush()

    for row in reader:
        total += 1
        if total % 500_000 == 0:
            elapsed = time.time() - start
            print(f"  [{total/1e6:.1f}M] {matched:,} matched | {elapsed/60:.1f} min")
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

    elapsed = time.time() - start
    print(f"\nPhase 1 done: {total:,} rows scanned, {matched:,} clusters matched")
    print(f"Unique dockets with clusters: {len(clusters_by_docket):,}")
    print(f"Time: {elapsed/60:.1f} min")

    with open(f"{state_dir}/clusters_by_docket.json", "w") as f:
        json.dump(dict(clusters_by_docket), f)
    with open(f"{state_dir}/cluster_ids.json", "w") as f:
        json.dump(list(cluster_ids), f)

    print(f"State saved ({len(cluster_ids):,} cluster IDs for Phase 2)")


# ── Phase 2: Opinions ──────────────────────────────────────────────

def phase_opinions(state_dir):
    with open(f"{state_dir}/cluster_ids.json") as f:
        cluster_ids = set(json.load(f))
    print(f"Loaded {len(cluster_ids):,} cluster IDs from Phase 1")

    print("\n" + "=" * 60)
    print("PHASE 2: STREAMING OPINIONS CSV")
    print("=" * 60)

    opinions_by_cluster = defaultdict(list)
    total = 0
    matched = 0
    start = time.time()

    reader = csv.DictReader(
        TextIOWrapper(sys.stdin.buffer, encoding='utf-8', errors='replace')
    )

    if reader.fieldnames:
        print(f"Columns ({len(reader.fieldnames)}): {', '.join(reader.fieldnames[:10])}...")
        sys.stdout.flush()

    for row in reader:
        total += 1
        if total % 500_000 == 0:
            elapsed = time.time() - start
            print(f"  [{total/1e6:.1f}M] {matched:,} matched | {elapsed/60:.1f} min")
            sys.stdout.flush()

        cluster_id = str(row.get("cluster_id", ""))
        if cluster_id not in cluster_ids:
            continue

        opinions_by_cluster[cluster_id].append({
            "id": str(row.get("id", "")),
            "cluster_id": cluster_id,
            "type": row.get("type", ""),
            "author_str": row.get("author_str", ""),
            "per_curiam": row.get("per_curiam", ""),
            "page_count": row.get("page_count", ""),
            "download_url": row.get("download_url", ""),
            "sha1": row.get("sha1", ""),
        })
        matched += 1

    elapsed = time.time() - start
    print(f"\nPhase 2 done: {total:,} rows scanned, {matched:,} opinions matched")
    print(f"Time: {elapsed/60:.1f} min")

    with open(f"{state_dir}/opinions_by_cluster.json", "w") as f:
        json.dump(dict(opinions_by_cluster), f)

    print("State saved")


# ── Phase 3: Score + Build ─────────────────────────────────────────

def phase_score(state_dir):
    print("Loading state from Phases 1-2...")
    with open(f"{state_dir}/docket_data.json") as f:
        docket_data = json.load(f)
    with open(f"{state_dir}/docket_nos.json") as f:
        docket_nos = json.load(f)
    with open(f"{state_dir}/clusters_by_docket.json") as f:
        clusters_by_docket = json.load(f)
    with open(f"{state_dir}/opinions_by_cluster.json") as f:
        opinions_by_cluster = json.load(f)

    print(f"  {len(docket_data):,} dockets, "
          f"{sum(len(v) for v in clusters_by_docket.values()):,} clusters, "
          f"{sum(len(v) for v in opinions_by_cluster.values()):,} opinions")

    # ── Score ──
    print("\n" + "=" * 60)
    print("SCORING")
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
        dissents = 0
        concurrences = 0
        total_opinions = 0
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

            for op in opinions_by_cluster.get(cl["id"], []):
                total_opinions += 1
                op_type = (op.get("type") or "").lower()
                if "dissent" in op_type:
                    dissents += 1
                elif "concur" in op_type:
                    concurrences += 1

        score = (
            published * 10
            + unpublished * 2
            + total_citations * 5
            + concurrences * 3
            + dissents * 8
            + (100 if has_scotus else 0)
        )

        scores[did] = score
        details[did] = {
            "score": score,
            "published_opinions": published,
            "unpublished_opinions": unpublished,
            "total_citations": total_citations,
            "dissents": dissents,
            "concurrences": concurrences,
            "total_opinions": total_opinions,
            "total_clusters": len(clusters),
            "has_scotus": has_scotus,
        }

    print(f"Scored {len(scores):,} cases (those with ≥1 opinion cluster)")

    if scores:
        vals = sorted(scores.values(), reverse=True)
        print(f"Score range: {vals[-1]} – {vals[0]}")
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
        "scoring_formula": "published*10 + unpublished*2 + citations*5 + concurrences*3 + dissents*8 + scotus*100",
        "categories": {},
    }

    total_golden = 0

    for nos_code in sorted(TARGET_NOS.keys()):
        nos_label = TARGET_NOS[nos_code]
        cases = nos_cases.get(nos_code, [])
        cases.sort(key=lambda x: x[1], reverse=True)
        top = cases[:TOP_N]

        cat_dir = os.path.join(OUTPUT_DIR, nos_label)
        os.makedirs(cat_dir, exist_ok=True)

        print(f"\n{nos_code} {nos_label}: {len(cases):,} scored → top {len(top)}")

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

            # Opinion clusters + nested opinions
            clusters = clusters_by_docket.get(did, [])
            if clusters:
                ops_dir = os.path.join(case_dir, "opinions")
                os.makedirs(ops_dir, exist_ok=True)

                for cl in clusters:
                    record = dict(cl)
                    record["opinions"] = opinions_by_cluster.get(cl["id"], [])
                    with open(os.path.join(ops_dir, f"cluster_{cl['id']}.json"), "w") as f:
                        json.dump(record, f, indent=2)

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

    print(f"\n{'=' * 60}")
    print(f"GOLDEN SET: {total_golden} cases across {len(TARGET_NOS)} categories")
    print(f"Saved to {OUTPUT_DIR}/")
    print("=" * 60)


# ── CLI ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["clusters", "opinions", "score"])
    parser.add_argument("--state-dir", default="/tmp/golden_state")
    args = parser.parse_args()

    os.makedirs(args.state_dir, exist_ok=True)

    if args.phase == "clusters":
        phase_clusters(args.state_dir)
    elif args.phase == "opinions":
        phase_opinions(args.state_dir)
    elif args.phase == "score":
        phase_score(args.state_dir)


if __name__ == "__main__":
    main()
