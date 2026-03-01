#!/usr/bin/env python3
"""
Filter cases2/ to find cases with BOTH RECAP data AND opinion clusters.
Creates golden_set_general/ with qualifying cases organized by NOS category.

Strategy:
  1. Load all 275K docket IDs + metadata from cases2/metadata/
  2. Filter for RECAP locally via source field bitmask (bit 0 = RECAP)
  3. Batch-check CourtListener API for opinion clusters:
     /dockets/?id__in={80 ids}&fields=id,clusters&format=json
  4. Cases with BOTH → golden_set_general/{category}/{id}_{slug}/docket.json

Resumable via checkpoint file. ~3,400 API calls, ~40 min with token.

Usage:
  python3 scripts/filter_golden_general.py
  python3 scripts/filter_golden_general.py --dry-run    # count only, no folders
  python3 scripts/filter_golden_general.py --resume     # resume from checkpoint

Requires CL_API_TOKEN or COURTLISTENER_TOKEN environment variable.
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

CL_API = "https://www.courtlistener.com/api/rest/v4"
CASES2_DIR = "cases2/metadata"
OUTPUT_DIR = "golden_set_general"
CHECKPOINT_FILE = "golden_set_general/_checkpoint.json"
BATCH_SIZE = 80

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

_stats = {"api_calls": 0, "api_errors": 0, "bytes_downloaded": 0}


def api_get(url, token, retries=4, backoff=2):
    """GET from CourtListener API with retries and rate-limit handling."""
    headers = {
        "User-Agent": "Ameen-GoldenGeneral/1.0",
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
                print("    AUTH FAILED (401) — check CL_API_TOKEN")
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


def sanitize_slug(name, max_len=50):
    """Create filesystem-safe slug from case name."""
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'\s+', '_', name.strip())
    return name[:max_len] or "unnamed"


def has_recap(source_val):
    """Check if source bitmask includes RECAP (bit 0)."""
    try:
        return int(source_val) & 1 == 1
    except (ValueError, TypeError):
        return False


def load_cases2():
    """Load all cases from cases2/metadata/ grouped by category."""
    all_cases = {}
    total = 0
    for cat_name, nos_code in sorted(CATEGORIES.items()):
        filepath = os.path.join(CASES2_DIR, f"{cat_name}.json")
        if not os.path.exists(filepath):
            print(f"  WARNING: {filepath} not found, skipping")
            continue
        with open(filepath) as f:
            cases = json.load(f)
        all_cases[cat_name] = cases
        total += len(cases)
        print(f"  {cat_name:20s}: {len(cases):>8,} cases")
    print(f"  {'TOTAL':>20s}: {total:>8,}")
    return all_cases


def load_checkpoint():
    """Load checkpoint for resumability."""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {"completed_categories": [], "dockets_with_opinions": {}}


def save_checkpoint(checkpoint):
    """Save checkpoint for resumability."""
    os.makedirs(os.path.dirname(CHECKPOINT_FILE), exist_ok=True)
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(checkpoint, f)


def batch_check_opinions(docket_ids, token):
    """Check which docket IDs have opinion clusters via batch API call.

    Uses /dockets/?id__in=id1,id2,...&fields=id,clusters&format=json
    Returns set of docket IDs that have at least one cluster.
    """
    if not docket_ids:
        return set()

    ids_str = ",".join(str(did) for did in docket_ids)
    url = f"{CL_API}/dockets/?id__in={ids_str}&fields=id,clusters&format=json&page_size=100"

    has_opinions = set()
    while url:
        data, err = api_get(url, token)
        if err:
            if err == "401":
                print("FATAL: Authentication failed. Check your API token.")
                sys.exit(1)
            print(f"    Batch check error: {err}")
            break
        for docket in data.get("results", []):
            did = str(docket.get("id", ""))
            clusters = docket.get("clusters", [])
            if clusters:
                has_opinions.add(did)
        url = data.get("next")
        if url:
            time.sleep(0.15)

    return has_opinions


def process_category(cat_name, cases, token, checkpoint, dry_run=False):
    """Process a single category: batch-check opinions, filter, create output."""
    nos_code = CATEGORIES[cat_name]
    total = len(cases)

    # Build lookup by docket ID
    cases_by_id = {}
    recap_ids = []
    for case in cases:
        did = str(case.get("id", ""))
        if not did:
            continue
        cases_by_id[did] = case
        if has_recap(case.get("source", "")):
            recap_ids.append(did)

    print(f"\n  RECAP filter: {len(recap_ids):,} / {total:,} have RECAP")

    # Use cached opinion data if available
    cached_opinion_ids = set(checkpoint.get("dockets_with_opinions", {}).get(cat_name, []))
    if cached_opinion_ids:
        print(f"  Using cached opinion data: {len(cached_opinion_ids):,} dockets with opinions")
        opinion_ids = cached_opinion_ids
    else:
        # Batch-check API for opinion clusters
        print(f"  Checking opinions via API ({len(recap_ids):,} dockets, batches of {BATCH_SIZE})...")
        opinion_ids = set()
        batches = [recap_ids[i:i+BATCH_SIZE] for i in range(0, len(recap_ids), BATCH_SIZE)]

        for i, batch in enumerate(batches):
            if (i + 1) % 50 == 0 or i == 0:
                elapsed_pct = (i + 1) / len(batches) * 100
                print(f"    [{i+1}/{len(batches)}] ({elapsed_pct:.0f}%) "
                      f"found {len(opinion_ids):,} with opinions | "
                      f"API calls: {_stats['api_calls']:,}")
                sys.stdout.flush()

            batch_opinions = batch_check_opinions(batch, token)
            opinion_ids.update(batch_opinions)
            time.sleep(0.1)

        # Cache results
        if "dockets_with_opinions" not in checkpoint:
            checkpoint["dockets_with_opinions"] = {}
        checkpoint["dockets_with_opinions"][cat_name] = list(opinion_ids)
        save_checkpoint(checkpoint)

    # Intersect: RECAP + opinions
    qualifying_ids = set(recap_ids) & opinion_ids
    print(f"  Opinions found: {len(opinion_ids):,}")
    print(f"  BOTH recap + opinions: {len(qualifying_ids):,}")

    if dry_run:
        return qualifying_ids

    # Create output folders
    cat_dir = os.path.join(OUTPUT_DIR, cat_name)
    os.makedirs(cat_dir, exist_ok=True)

    cat_index = []
    for did in sorted(qualifying_ids):
        case = cases_by_id[did]
        case_name = case.get("case_name", f"case_{did}")
        slug = sanitize_slug(case_name)
        folder_name = f"{did}_{slug}"
        case_dir = os.path.join(cat_dir, folder_name)
        os.makedirs(case_dir, exist_ok=True)

        # Write docket metadata
        with open(os.path.join(case_dir, "docket.json"), "w") as f:
            json.dump(case, f, indent=2)

        cat_index.append({
            "docket_id": did,
            "case_name": case_name,
            "court_id": case.get("court_id", ""),
            "date_filed": case.get("date_filed", ""),
            "date_terminated": case.get("date_terminated", ""),
            "source": case.get("source", ""),
        })

    # Write category index
    with open(os.path.join(cat_dir, "index.json"), "w") as f:
        json.dump(cat_index, f, indent=2)

    return qualifying_ids


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Filter cases for golden_set_general")
    parser.add_argument("--dry-run", action="store_true", help="Count only, don't create folders")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    args = parser.parse_args()

    token = os.environ.get("CL_API_TOKEN", "") or os.environ.get("COURTLISTENER_TOKEN", "")
    if not token:
        print("FATAL: CL_API_TOKEN or COURTLISTENER_TOKEN environment variable required")
        sys.exit(1)
    print(f"Token OK (length={len(token)})")

    # Test API
    print("Testing API connection...")
    test, err = api_get(f"{CL_API}/courts/?format=json&page_size=1", token)
    if err:
        print(f"FATAL: API test failed: {err}")
        sys.exit(1)
    print("API connection OK\n")

    # Load cases
    print("Loading cases2 metadata...")
    all_cases = load_cases2()

    # Load checkpoint
    checkpoint = load_checkpoint() if args.resume else {"completed_categories": [], "dockets_with_opinions": {}}

    # Process each category
    print(f"\n{'=' * 60}")
    print("FILTERING: RECAP + OPINIONS")
    print("=" * 60)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    grand_total = 0
    grand_qualifying = 0
    category_stats = {}
    start = time.time()

    for cat_name in sorted(CATEGORIES.keys()):
        cases = all_cases.get(cat_name, [])
        if not cases:
            continue

        if cat_name in checkpoint.get("completed_categories", []) and not args.dry_run:
            # Already done, count from existing output
            cat_dir = os.path.join(OUTPUT_DIR, cat_name)
            idx_file = os.path.join(cat_dir, "index.json")
            if os.path.exists(idx_file):
                with open(idx_file) as f:
                    idx = json.load(f)
                count = len(idx)
                print(f"\n{'=' * 60}")
                print(f"{cat_name} (NOS {CATEGORIES[cat_name]}): ALREADY DONE — {count:,} qualifying")
                grand_total += len(cases)
                grand_qualifying += count
                category_stats[cat_name] = {
                    "total": len(cases),
                    "qualifying": count,
                }
                continue

        print(f"\n{'=' * 60}")
        print(f"{cat_name} (NOS {CATEGORIES[cat_name]}): {len(cases):,} cases")
        print("=" * 60)

        qualifying = process_category(cat_name, cases, token, checkpoint, dry_run=args.dry_run)
        count = len(qualifying)

        if not args.dry_run:
            checkpoint.setdefault("completed_categories", []).append(cat_name)
            save_checkpoint(checkpoint)

        grand_total += len(cases)
        grand_qualifying += count
        category_stats[cat_name] = {
            "total": len(cases),
            "qualifying": count,
        }

    # Write master index
    elapsed = time.time() - start
    index = {
        "description": "Cases with BOTH RECAP data AND opinion clusters",
        "source": "cases2/metadata/",
        "filter_criteria": {
            "recap": "source field bitmask bit 0 = 1",
            "opinions": "docket has at least one opinion cluster on CourtListener",
        },
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_cases_scanned": grand_total,
        "total_qualifying": grand_qualifying,
        "categories": category_stats,
        "api_stats": {
            "calls": _stats["api_calls"],
            "errors": _stats["api_errors"],
            "bytes_downloaded": _stats["bytes_downloaded"],
            "elapsed_minutes": round(elapsed / 60, 1),
        },
    }

    if not args.dry_run:
        with open(os.path.join(OUTPUT_DIR, "index.json"), "w") as f:
            json.dump(index, f, indent=2)

    # Final report
    print(f"\n{'=' * 60}")
    print("RESULTS")
    print("=" * 60)
    for cat_name in sorted(category_stats.keys()):
        s = category_stats[cat_name]
        pct = s["qualifying"] / max(s["total"], 1) * 100
        print(f"  {cat_name:20s}: {s['qualifying']:>6,} / {s['total']:>8,} ({pct:.1f}%)")
    print(f"  {'TOTAL':>20s}: {grand_qualifying:>6,} / {grand_total:>8,}")
    print(f"\n  API calls: {_stats['api_calls']:,}")
    print(f"  API errors: {_stats['api_errors']:,}")
    print(f"  Time: {elapsed/60:.1f} min")
    mb = _stats["bytes_downloaded"] / 1024 / 1024
    print(f"  Downloaded: {mb:.1f} MB")

    if args.dry_run:
        print("\n  [DRY RUN — no folders created]")
    else:
        print(f"\n  Output: {OUTPUT_DIR}/")
        print(f"  Cases: {grand_qualifying:,} case folders across {len(category_stats)} categories")

    print("=" * 60)


if __name__ == "__main__":
    main()
