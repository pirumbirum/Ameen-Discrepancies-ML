#!/usr/bin/env python3
"""
Filter cases2/ to find cases with BOTH RECAP data AND opinion clusters.
Creates golden_set_general/ with qualifying cases organized by NOS category.

Strategy:
  1. Download CourtListener's bulk opinion-clusters CSV from S3
  2. Extract per-docket opinion stats (cluster count, citations, dates, etc.)
  3. Load our cases2/metadata/ docket IDs, filter for RECAP
  4. Intersect: RECAP docket IDs ∩ cluster docket IDs = qualifying cases
  5. Write to golden_set_general/{category}/{id}_{slug}/docket.json
     with _opinion_stats embedded

No per-docket API calls needed. ~10 min total.
"""

import csv
import json
import io
import os
import re
import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BULK_CSV_URL = (
    "https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/"
    "bulk-data/opinion-clusters-2025-12-31.csv.bz2"
)
CASES2_DIR = "cases2/metadata"
OUTPUT_DIR = "golden_set_general"

CATEGORIES = {
    "antitrust":      "410",
    "banks":          "430",
    "environmental":  "893",
    "insurance":      "110",
    "other_contract": "190",
    "patent":         "830",
    "rico":           "470",
    "securities":     "850",
    "stockholders":   "160",
    "trade_secret":   "880",
    "trademark":      "840",
}

# Process smallest categories first for fastest initial results
CATEGORY_ORDER = [
    "banks", "trade_secret", "stockholders", "antitrust",
    "environmental", "rico", "securities", "trademark",
    "patent", "other_contract", "insurance",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sanitize_slug(name, max_len=50):
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'\s+', '_', name.strip())
    return name[:max_len] or "unnamed"


def has_recap(source_val):
    try:
        return int(source_val) & 1 == 1
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------

def git_commit(msg):
    try:
        subprocess.run(["git", "add", "golden_set_general/"],
                       check=True, capture_output=True)
        result = subprocess.run(["git", "diff", "--cached", "--quiet"],
                                capture_output=True)
        if result.returncode == 0:
            return
        subprocess.run(["git", "commit", "-m", msg],
                       check=True, capture_output=True)
        subprocess.run(["git", "push"],
                       check=True, capture_output=True, timeout=120)
        print(f"  [git] committed + pushed: {msg}")
    except Exception as e:
        print(f"  [git] WARNING: {e}")


# ---------------------------------------------------------------------------
# Step 1: Download bulk CSV and extract per-docket opinion stats
# ---------------------------------------------------------------------------

def download_cluster_stats():
    """Stream-download the bulk opinion-clusters CSV from S3 and extract
    per-docket opinion statistics.

    Returns dict: {docket_id_str: {opinion_cluster_count, total_citation_count, ...}}
    """
    print("Downloading opinion-clusters bulk CSV from CourtListener S3...")
    print(f"  URL: {BULK_CSV_URL}")
    t0 = time.time()

    proc = subprocess.Popen(
        f'curl -sL "{BULK_CSV_URL}" | bunzip2',
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    csv.field_size_limit(sys.maxsize)
    reader = csv.DictReader(
        io.TextIOWrapper(proc.stdout, encoding="utf-8", errors="replace"),
        escapechar='\\',
    )

    # Collect per-docket stats while streaming
    cluster_stats = {}  # docket_id -> stats dict
    rows_read = 0

    for row in reader:
        did = row.get("docket_id")
        if not did:
            rows_read += 1
            continue
        did = did.strip()

        if did not in cluster_stats:
            cluster_stats[did] = {
                "opinion_cluster_count": 0,
                "total_citation_count": 0,
                "precedential_statuses": [],
                "opinion_dates": [],
                "has_disposition": False,
                "has_syllabus": False,
                "has_procedural_history": False,
                "has_arguments": False,
                "has_headnotes": False,
                "has_summary": False,
            }

        s = cluster_stats[did]
        s["opinion_cluster_count"] += 1

        try:
            s["total_citation_count"] += int(row.get("citation_count", 0) or 0)
        except (ValueError, TypeError):
            pass

        ps = (row.get("precedential_status") or "").strip()
        if ps and ps not in s["precedential_statuses"]:
            s["precedential_statuses"].append(ps)

        df = (row.get("date_filed") or "").strip()
        if df:
            s["opinion_dates"].append(df)

        if (row.get("disposition") or "").strip():
            s["has_disposition"] = True
        if (row.get("syllabus") or "").strip():
            s["has_syllabus"] = True
        if (row.get("procedural_history") or "").strip():
            s["has_procedural_history"] = True
        if (row.get("arguments") or "").strip():
            s["has_arguments"] = True
        if (row.get("headnotes") or "").strip():
            s["has_headnotes"] = True
        if (row.get("summary") or "").strip():
            s["has_summary"] = True

        rows_read += 1
        if rows_read % 500_000 == 0:
            elapsed = time.time() - t0
            print(f"    {rows_read:,} rows processed, "
                  f"{len(cluster_stats):,} unique docket IDs, "
                  f"{elapsed:.0f}s elapsed")
            sys.stdout.flush()

    proc.wait()
    elapsed = time.time() - t0

    if proc.returncode != 0:
        stderr = proc.stderr.read().decode(errors="replace")
        print(f"  WARNING: download process exited with code {proc.returncode}")
        if stderr:
            print(f"  stderr: {stderr[:500]}")

    # Finalize stats: compute date ranges from opinion_dates
    for did, s in cluster_stats.items():
        dates = sorted(s["opinion_dates"])
        if dates:
            s["earliest_opinion_date"] = dates[0]
            s["latest_opinion_date"] = dates[-1]
        else:
            s["earliest_opinion_date"] = None
            s["latest_opinion_date"] = None
        del s["opinion_dates"]  # don't store raw list

    print(f"  Done: {rows_read:,} total rows, "
          f"{len(cluster_stats):,} unique docket IDs with opinion clusters")
    print(f"  Time: {elapsed:.1f}s")

    if len(cluster_stats) == 0:
        print("FATAL: No docket IDs extracted from bulk CSV")
        sys.exit(1)

    return cluster_stats


# ---------------------------------------------------------------------------
# Step 2: Load cases2 metadata and filter
# ---------------------------------------------------------------------------

def load_and_filter(cluster_stats):
    """Load all categories from cases2/metadata, filter for RECAP + opinions.

    Returns dict: {category: [qualifying_cases]}
    Each case gets an _opinion_stats field merged in.
    """
    print("\nLoading cases2 metadata and filtering...")

    results = {}
    grand_total = 0
    grand_recap = 0
    grand_qualifying = 0

    for cat_name in CATEGORY_ORDER:
        if cat_name not in CATEGORIES:
            continue

        fp = os.path.join(CASES2_DIR, f"{cat_name}.json")
        if not os.path.exists(fp):
            print(f"  WARNING: {fp} not found, skipping")
            continue

        with open(fp) as f:
            cases = json.load(f)

        total = len(cases)
        recap_count = 0
        qualifying = []

        for case in cases:
            did = str(case.get("id", ""))
            if not did:
                continue
            if has_recap(case.get("source", "")):
                recap_count += 1
                if did in cluster_stats:
                    case["_opinion_stats"] = cluster_stats[did]
                    qualifying.append(case)

        results[cat_name] = qualifying
        grand_total += total
        grand_recap += recap_count
        grand_qualifying += len(qualifying)

        pct = len(qualifying) / max(total, 1) * 100
        print(f"  {cat_name:20s}: {total:>8,} total -> "
              f"{recap_count:>8,} RECAP -> "
              f"{len(qualifying):>6,} qualifying ({pct:.1f}%)")

    print(f"\n  {'TOTAL':>20s}: {grand_total:>8,} total -> "
          f"{grand_recap:>8,} RECAP -> "
          f"{grand_qualifying:>6,} qualifying")

    return results


# ---------------------------------------------------------------------------
# Step 3: Write output
# ---------------------------------------------------------------------------

def write_output(results):
    """Write qualifying cases to golden_set_general/."""
    print("\nWriting output to golden_set_general/...")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    category_stats = {}

    for cat_name in CATEGORY_ORDER:
        qualifying = results.get(cat_name, [])
        if not qualifying and cat_name not in results:
            continue

        cat_dir = os.path.join(OUTPUT_DIR, cat_name)
        os.makedirs(cat_dir, exist_ok=True)

        cat_index = []
        for case in qualifying:
            did = str(case.get("id", ""))
            case_name = case.get("case_name", f"case_{did}")
            slug = sanitize_slug(case_name)
            folder_name = f"{did}_{slug}"
            case_dir = os.path.join(cat_dir, folder_name)
            os.makedirs(case_dir, exist_ok=True)

            with open(os.path.join(case_dir, "docket.json"), "w") as f:
                json.dump(case, f, indent=2)

            ostats = case.get("_opinion_stats", {})
            cat_index.append({
                "docket_id": did,
                "case_name": case_name,
                "court_id": case.get("court_id", ""),
                "date_filed": case.get("date_filed", ""),
                "date_terminated": case.get("date_terminated", ""),
                "source": case.get("source", ""),
                "opinion_cluster_count": ostats.get("opinion_cluster_count", 0),
                "total_citation_count": ostats.get("total_citation_count", 0),
                "precedential_statuses": ostats.get("precedential_statuses", []),
                "has_disposition": ostats.get("has_disposition", False),
                "has_syllabus": ostats.get("has_syllabus", False),
                "has_procedural_history": ostats.get("has_procedural_history", False),
                "has_arguments": ostats.get("has_arguments", False),
                "has_headnotes": ostats.get("has_headnotes", False),
                "has_summary": ostats.get("has_summary", False),
                "earliest_opinion_date": ostats.get("earliest_opinion_date"),
                "latest_opinion_date": ostats.get("latest_opinion_date"),
            })

        with open(os.path.join(cat_dir, "index.json"), "w") as f:
            json.dump(cat_index, f, indent=2)

        # Aggregate category-level stats
        total_clusters = sum(c.get("opinion_cluster_count", 0) for c in cat_index)
        total_citations = sum(c.get("total_citation_count", 0) for c in cat_index)
        with_disposition = sum(1 for c in cat_index if c.get("has_disposition"))
        with_syllabus = sum(1 for c in cat_index if c.get("has_syllabus"))

        category_stats[cat_name] = {
            "qualifying": len(qualifying),
            "total_opinion_clusters": total_clusters,
            "total_citations": total_citations,
            "cases_with_disposition": with_disposition,
            "cases_with_syllabus": with_syllabus,
        }

        print(f"  {cat_name:20s}: {len(qualifying):>6,} cases, "
              f"{total_clusters:>6,} clusters, "
              f"{total_citations:>6,} citations")

    return category_stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    start_time = time.time()

    print("=" * 60)
    print("GOLDEN SET GENERAL — FULL RUN")
    print("Filter: RECAP source + opinion clusters")
    print("Enrichment: opinion stats from bulk CSV")
    print("=" * 60)

    # Step 1: Download CSV and extract per-docket opinion stats
    cluster_stats = download_cluster_stats()

    # Step 2: Load cases2, filter for RECAP, intersect with cluster stats
    results = load_and_filter(cluster_stats)

    # Step 3: Write output with opinion stats embedded
    category_stats = write_output(results)

    # Master index
    elapsed = time.time() - start_time
    grand_qualifying = sum(s["qualifying"] for s in category_stats.values())
    grand_clusters = sum(s["total_opinion_clusters"] for s in category_stats.values())
    grand_citations = sum(s["total_citations"] for s in category_stats.values())

    index = {
        "description": "Cases with BOTH RECAP data AND opinion clusters",
        "source_data": "cases2/metadata/",
        "cluster_source": BULK_CSV_URL,
        "filter_criteria": {
            "recap": "source bitmask bit 0 = 1",
            "opinions": "docket_id appears in CourtListener opinion-clusters bulk CSV",
        },
        "opinion_stats_fields": [
            "opinion_cluster_count", "total_citation_count",
            "precedential_statuses", "has_disposition", "has_syllabus",
            "has_procedural_history", "has_arguments", "has_headnotes",
            "has_summary", "earliest_opinion_date", "latest_opinion_date",
        ],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_qualifying": grand_qualifying,
        "total_opinion_clusters": grand_clusters,
        "total_citations": grand_citations,
        "categories": category_stats,
        "elapsed_minutes": round(elapsed / 60, 1),
    }
    with open(os.path.join(OUTPUT_DIR, "index.json"), "w") as f:
        json.dump(index, f, indent=2)

    # Git commit
    git_commit(
        f"golden_set_general: COMPLETE — "
        f"{grand_qualifying:,} cases, {grand_clusters:,} clusters, "
        f"{grand_citations:,} citations")

    # Report
    print(f"\n{'=' * 60}")
    print("RESULTS")
    print("=" * 60)
    for cat_name in CATEGORY_ORDER:
        s = category_stats.get(cat_name)
        if not s:
            continue
        print(f"  {cat_name:20s}: {s['qualifying']:>6,} cases  "
              f"{s['total_opinion_clusters']:>6,} clusters  "
              f"{s['total_citations']:>6,} citations  "
              f"{s['cases_with_disposition']:>5,} w/disposition")
    print(f"\n  {'TOTAL':>20s}: {grand_qualifying:>6,} cases  "
          f"{grand_clusters:>6,} clusters  "
          f"{grand_citations:>6,} citations")
    print(f"\n  Time: {elapsed / 60:.1f} min")
    print("=" * 60)


if __name__ == "__main__":
    main()
