#!/usr/bin/env python3
"""
Filter cases2/ to find cases with BOTH RECAP data AND opinion clusters.
Creates golden_set_general/ with qualifying cases organized by NOS category.

Strategy:
  1. Load all 275K docket IDs from cases2/metadata/
  2. Filter for RECAP locally (source bitmask bit 0)
  3. Check each docket individually via /dockets/{id}/ for opinion clusters
  4. Write qualifying cases to golden_set_general/{category}/{id}_{slug}/docket.json
  5. Git commit every 30 minutes to persist progress

Built from scratch. No external script imports.
Uses single-resource API calls (not batch id__in) for reliable cluster detection.

Requires CL_API_TOKEN or COURTLISTENER_TOKEN env var.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# Config (overridden by --test)
# ---------------------------------------------------------------------------
CL_API = "https://www.courtlistener.com/api/rest/v4"
CASES2_DIR = "cases2/metadata"
OUTPUT_DIR = "golden_set_general"
CHECKPOINT_FILE = "golden_set_general/_checkpoint.json"
CHECKPOINT_EVERY = 100  # save checkpoint every N dockets checked
CALLS_PER_HOUR = 4600  # CourtListener allows 5000; 400 buffer
MIN_SLEEP = 3600 / CALLS_PER_HOUR  # ~0.78s between calls
GIT_COMMIT_INTERVAL = 1800  # 30 minutes

# Test mode overrides
TEST_CATEGORIES = ["banks", "trade_secret"]  # 2 smallest
TEST_CASES_PER_CAT = 20  # small sample for quick validation
TEST_CHECKPOINT_EVERY = 10  # save often in test mode
TEST_GIT_COMMIT_INTERVAL = 60  # 1 minute

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

# ---------------------------------------------------------------------------
# HTTP — standalone, uses requests with connection pooling
# ---------------------------------------------------------------------------
try:
    import requests
except ImportError:
    print("Installing requests...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests


class APIClient:
    """Rate-limited CourtListener client with connection pooling and retries."""

    def __init__(self, token):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Token {token}",
            "User-Agent": "Ameen-GoldenGeneral/2.0",
        })
        self.call_timestamps = []  # sliding window for rate limiting
        self.total_calls = 0
        self.total_errors = 0
        self.total_bytes = 0

    def _enforce_rate_limit(self):
        """Proactive rate limiting — sleep BEFORE hitting the limit."""
        now = time.time()
        one_hour_ago = now - 3600
        # Clean old entries
        self.call_timestamps = [t for t in self.call_timestamps if t > one_hour_ago]

        if len(self.call_timestamps) >= CALLS_PER_HOUR:
            oldest = self.call_timestamps[0]
            wait = (oldest + 3600) - now + 1
            if wait > 0:
                print(f"  [RATE LIMIT] {len(self.call_timestamps)} calls in last hour, "
                      f"sleeping {wait:.0f}s")
                time.sleep(wait)

        # Always enforce minimum gap between calls
        if self.call_timestamps:
            since_last = now - self.call_timestamps[-1]
            if since_last < MIN_SLEEP:
                time.sleep(MIN_SLEEP - since_last)

        self.call_timestamps.append(time.time())
        self.total_calls += 1

    def get(self, url, max_retries=4):
        """GET with rate limiting, retries, and exponential backoff."""
        self._enforce_rate_limit()

        for attempt in range(max_retries):
            try:
                resp = self.session.get(url, timeout=30)

                if resp.status_code == 200:
                    self.total_bytes += len(resp.content)
                    return resp.json()

                if resp.status_code == 429:
                    wait = min(60 * (2 ** attempt), 300)
                    print(f"    [429] Rate limited, waiting {wait}s "
                          f"(attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait)
                    self._enforce_rate_limit()
                    continue

                if resp.status_code == 401:
                    print("    FATAL: 401 Unauthorized — check your API token")
                    sys.exit(1)

                if resp.status_code in (500, 502, 503, 504):
                    wait = 5 * (2 ** attempt)
                    print(f"    [{resp.status_code}] Server error, waiting {wait}s "
                          f"(attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait)
                    continue

                # Other error
                self.total_errors += 1
                print(f"    HTTP {resp.status_code}: {resp.text[:200]}")
                return None

            except requests.RequestException as e:
                wait = 5 * (2 ** attempt)
                self.total_errors += 1
                print(f"    Network error: {e}, waiting {wait}s "
                      f"(attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)

        print(f"    FAILED after {max_retries} attempts")
        return None

    def stats_str(self):
        mb = self.total_bytes / 1024 / 1024
        return (f"API calls: {self.total_calls:,} | "
                f"errors: {self.total_errors:,} | "
                f"downloaded: {mb:.1f} MB")


# ---------------------------------------------------------------------------
# Checkpoint — saves and resumes progress
# ---------------------------------------------------------------------------

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {
        "completed_categories": [],
        "partial": {},  # {category: {last_batch_idx: N, opinion_ids: [...]}}
    }


def save_checkpoint(ckpt):
    os.makedirs(os.path.dirname(CHECKPOINT_FILE) or ".", exist_ok=True)
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(ckpt, f)


# ---------------------------------------------------------------------------
# Git — commit progress periodically
# ---------------------------------------------------------------------------

_last_git_commit_time = 0


def git_commit(msg):
    """Stage golden_set_general/, commit if changes, push."""
    global _last_git_commit_time
    try:
        subprocess.run(["git", "add", "golden_set_general/"],
                       check=True, capture_output=True)
        # Check if anything staged
        result = subprocess.run(["git", "diff", "--cached", "--quiet"],
                                capture_output=True)
        if result.returncode == 0:
            print("    [git] nothing new to commit")
            return
        subprocess.run(["git", "commit", "-m", msg],
                       check=True, capture_output=True)
        subprocess.run(["git", "push"],
                       check=True, capture_output=True, timeout=60)
        print(f"    [git] committed + pushed: {msg}")
        _last_git_commit_time = time.time()
    except Exception as e:
        print(f"    [git] WARNING: {e}")


def maybe_git_commit(msg):
    """Commit if 30+ minutes since last commit."""
    global _last_git_commit_time
    if time.time() - _last_git_commit_time >= GIT_COMMIT_INTERVAL:
        git_commit(msg)


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
# Core logic
# ---------------------------------------------------------------------------

def check_opinions_single(client, docket_ids):
    """Check which docket IDs have opinion clusters.

    Fetches each docket individually via /dockets/{id}/ to reliably get
    the clusters field. The list endpoint with id__in + fields=clusters
    is unreliable on CourtListener's API.

    Returns set of string docket IDs that have clusters.
    """
    if not docket_ids:
        return set()

    has_opinions = set()
    for i, did in enumerate(docket_ids):
        url = (f"{CL_API}/dockets/{did}/"
               f"?fields=id,clusters"
               f"&format=json")
        data = client.get(url)

        # Debug: print first response structure
        if i == 0 and client.total_calls <= 5:
            if data:
                print(f"    [DEBUG] Sample response keys: {list(data.keys())}")
                print(f"    [DEBUG] Sample: id={data.get('id')}, "
                      f"clusters={data.get('clusters', [])[:3]}")
            else:
                print(f"    [DEBUG] First request returned None (error)")

        if data is None:
            continue  # skip errors, don't abort whole batch
        clusters = data.get("clusters", [])
        if clusters:
            has_opinions.add(str(did))

    return has_opinions


def process_category(cat_name, cases, client, ckpt, start_time,
                     case_limit=None, checkpoint_every=100, test_mode=False):
    """Process one category: check each docket for opinions, filter, write output."""
    total = len(cases)

    # Build lookup + RECAP filter
    cases_by_id = {}
    recap_ids = []
    for case in cases:
        did = str(case.get("id", ""))
        if not did:
            continue
        cases_by_id[did] = case
        if has_recap(case.get("source", "")):
            recap_ids.append(did)

    print(f"  RECAP filter: {len(recap_ids):,} / {total:,}")

    # In test mode, limit cases
    if case_limit and len(recap_ids) > case_limit:
        print(f"  TEST MODE: limiting to {case_limit} cases "
              f"(from {len(recap_ids):,})")
        recap_ids = recap_ids[:case_limit]

    # Check for partial progress on this category
    partial = ckpt.get("partial", {}).get(cat_name, {})
    start_idx = partial.get("last_checked_idx", 0)
    opinion_ids = set(partial.get("opinion_ids", []))

    if start_idx > 0:
        print(f"  Resuming from index {start_idx} "
              f"(already found {len(opinion_ids):,} with opinions)")

    num_ids = len(recap_ids)
    print(f"  Checking opinions: {num_ids:,} dockets (1 API call each)")

    for i in range(start_idx, num_ids):
        did = recap_ids[i]

        # Progress every 50 dockets
        if i % 50 == 0 or i == start_idx:
            pct = (i + 1) / num_ids * 100
            elapsed = (time.time() - start_time) / 60
            print(f"    [{i + 1}/{num_ids}] ({pct:.0f}%) "
                  f"opinions so far: {len(opinion_ids):,} | "
                  f"{client.stats_str()} | {elapsed:.1f}min elapsed")
            sys.stdout.flush()

        result = check_opinions_single(client, [did])
        opinion_ids.update(result)

        # Save partial checkpoint periodically
        if (i + 1) % checkpoint_every == 0:
            if "partial" not in ckpt:
                ckpt["partial"] = {}
            ckpt["partial"][cat_name] = {
                "last_checked_idx": i + 1,
                "opinion_ids": list(opinion_ids),
            }
            save_checkpoint(ckpt)

        # Git commit every 30 minutes
        maybe_git_commit(
            f"golden_set_general: {cat_name} {i + 1}/{num_ids} "
            f"({len(opinion_ids):,} with opinions)")

    # Clear partial progress for this category
    if "partial" in ckpt and cat_name in ckpt["partial"]:
        del ckpt["partial"][cat_name]

    # Intersect RECAP + opinions
    qualifying_ids = set(recap_ids) & opinion_ids
    print(f"  Opinions found: {len(opinion_ids):,}")
    print(f"  BOTH recap + opinions: {len(qualifying_ids):,}")

    # Write output folders
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

    with open(os.path.join(cat_dir, "index.json"), "w") as f:
        json.dump(cat_index, f, indent=2)

    return qualifying_ids


def main():
    parser = argparse.ArgumentParser(
        description="Filter cases for golden_set_general")
    parser.add_argument("--test", action="store_true",
                        help="Test mode: 2 categories, 160 cases each, "
                             "fast checkpoints, extra debug output")
    args = parser.parse_args()

    test_mode = args.test

    # Apply test overrides
    global GIT_COMMIT_INTERVAL
    if test_mode:
        GIT_COMMIT_INTERVAL = TEST_GIT_COMMIT_INTERVAL
        print("=" * 60)
        print("TEST MODE")
        print(f"  Categories: {TEST_CATEGORIES}")
        print(f"  Cases per category: {TEST_CASES_PER_CAT}")
        print(f"  Checkpoint every: {TEST_CHECKPOINT_EVERY} dockets")
        print(f"  Git commit interval: {TEST_GIT_COMMIT_INTERVAL}s")
        print("=" * 60)

    # Token
    token = (os.environ.get("CL_API_TOKEN", "")
             or os.environ.get("COURTLISTENER_TOKEN", ""))
    if not token:
        print("FATAL: Set CL_API_TOKEN or COURTLISTENER_TOKEN env var")
        sys.exit(1)
    print(f"Token OK (length={len(token)})")

    # Build client
    client = APIClient(token)

    # Test API
    print("\nTesting API connection...")
    test_resp = client.get(f"{CL_API}/courts/?format=json&page_size=1")
    if test_resp is None:
        print("FATAL: API test failed")
        sys.exit(1)
    print(f"API OK (got {test_resp.get('count', '?')} courts)\n")

    # Determine which categories to load
    if test_mode:
        cats_to_load = {k: v for k, v in CATEGORIES.items()
                        if k in TEST_CATEGORIES}
    else:
        cats_to_load = CATEGORIES

    # Load cases
    print("Loading cases2 metadata...")
    all_cases = {}
    grand_total_loaded = 0
    for cat_name in sorted(cats_to_load.keys()):
        fp = os.path.join(CASES2_DIR, f"{cat_name}.json")
        if not os.path.exists(fp):
            print(f"  WARNING: {fp} not found, skipping")
            continue
        with open(fp) as f:
            cases = json.load(f)
        all_cases[cat_name] = cases
        grand_total_loaded += len(cases)
        print(f"  {cat_name:20s}: {len(cases):>8,}")
    print(f"  {'TOTAL':>20s}: {grand_total_loaded:>8,}\n")

    # Checkpoint — fresh start in test mode
    if test_mode:
        ckpt = {"completed_categories": [], "partial": {}}
    else:
        ckpt = load_checkpoint()

    # Process
    mode_label = "TEST RUN" if test_mode else "FULL RUN"
    print("=" * 60)
    print(f"FILTERING: RECAP + OPINIONS ({mode_label})")
    print("=" * 60)

    global _last_git_commit_time
    _last_git_commit_time = time.time()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    start_time = time.time()
    grand_total = 0
    grand_qualifying = 0
    category_stats = {}

    for cat_name in sorted(cats_to_load.keys()):
        cases = all_cases.get(cat_name, [])
        if not cases:
            continue

        # Skip completed categories
        if cat_name in ckpt.get("completed_categories", []):
            cat_dir = os.path.join(OUTPUT_DIR, cat_name)
            idx_file = os.path.join(cat_dir, "index.json")
            if os.path.exists(idx_file):
                with open(idx_file) as f:
                    idx = json.load(f)
                count = len(idx)
                print(f"\n{cat_name}: DONE — {count:,} qualifying")
                grand_total += len(cases)
                grand_qualifying += count
                category_stats[cat_name] = {
                    "total": len(cases), "qualifying": count}
                continue

        print(f"\n{'=' * 60}")
        print(f"{cat_name} (NOS {cats_to_load[cat_name]}): {len(cases):,} cases")
        print("=" * 60)

        qualifying = process_category(
            cat_name, cases, client, ckpt, start_time,
            case_limit=TEST_CASES_PER_CAT if test_mode else None,
            checkpoint_every=TEST_CHECKPOINT_EVERY if test_mode else CHECKPOINT_EVERY,
            test_mode=test_mode)
        count = len(qualifying)

        # Mark completed
        ckpt.setdefault("completed_categories", []).append(cat_name)
        save_checkpoint(ckpt)

        grand_total += len(cases)
        grand_qualifying += count
        category_stats[cat_name] = {
            "total": len(cases), "qualifying": count}

        # Git commit after each category
        git_commit(
            f"golden_set_general{'[TEST]' if test_mode else ''}: "
            f"{cat_name} done — {count:,} qualifying cases")

    # Master index
    elapsed = time.time() - start_time
    index = {
        "description": "Cases with BOTH RECAP data AND opinion clusters",
        "mode": "test" if test_mode else "full",
        "source": "cases2/metadata/",
        "filter_criteria": {
            "recap": "source bitmask bit 0 = 1",
            "opinions": "docket has >= 1 opinion cluster on CourtListener",
        },
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_scanned": grand_total,
        "total_qualifying": grand_qualifying,
        "categories": category_stats,
        "api_stats": {
            "calls": client.total_calls,
            "errors": client.total_errors,
            "bytes_mb": round(client.total_bytes / 1024 / 1024, 1),
            "elapsed_minutes": round(elapsed / 60, 1),
        },
    }
    with open(os.path.join(OUTPUT_DIR, "index.json"), "w") as f:
        json.dump(index, f, indent=2)

    # Final commit
    git_commit(
        f"golden_set_general{'[TEST]' if test_mode else ''}: COMPLETE — "
        f"{grand_qualifying:,} cases across {len(category_stats)} categories")

    # Report
    print(f"\n{'=' * 60}")
    print(f"RESULTS ({mode_label})")
    print("=" * 60)
    for cat_name in sorted(category_stats.keys()):
        s = category_stats[cat_name]
        pct = s["qualifying"] / max(s["total"], 1) * 100
        print(f"  {cat_name:20s}: {s['qualifying']:>6,} / {s['total']:>8,} "
              f"({pct:.1f}%)")
    print(f"  {'TOTAL':>20s}: {grand_qualifying:>6,} / {grand_total:>8,}")
    print(f"\n  {client.stats_str()}")
    print(f"  Time: {elapsed / 60:.1f} min")

    if test_mode:
        # Print validation summary
        print(f"\n{'=' * 60}")
        print("TEST VALIDATION")
        print("=" * 60)
        checks = []

        # 1. API worked
        checks.append(("API auth + connection",
                        client.total_calls > 0 and client.total_errors == 0))
        # 2. Rate limiting — no 429s means it worked
        checks.append(("Rate limiting (no 429s)",
                        client.total_errors == 0))
        # 3. Got qualifying cases
        checks.append(("Found qualifying cases",
                        grand_qualifying > 0))
        # 4. Output dirs created
        dirs_ok = all(
            os.path.isdir(os.path.join(OUTPUT_DIR, c))
            for c in TEST_CATEGORIES)
        checks.append(("Output directories created", dirs_ok))
        # 5. docket.json files exist
        docket_count = sum(
            1 for root, dirs, files in os.walk(OUTPUT_DIR)
            if "docket.json" in files)
        checks.append((f"docket.json files written ({docket_count})",
                        docket_count > 0))
        # 6. Category index files
        idx_ok = all(
            os.path.exists(os.path.join(OUTPUT_DIR, c, "index.json"))
            for c in TEST_CATEGORIES)
        checks.append(("Category index.json files", idx_ok))
        # 7. Master index
        checks.append(("Master index.json",
                        os.path.exists(os.path.join(OUTPUT_DIR, "index.json"))))
        # 8. Checkpoint
        checks.append(("Checkpoint file",
                        os.path.exists(CHECKPOINT_FILE)))
        # 9. Checkpoint has completed categories
        ckpt_ok = len(ckpt.get("completed_categories", [])) == len(TEST_CATEGORIES)
        checks.append((f"Checkpoint tracks {len(TEST_CATEGORIES)} completed cats",
                        ckpt_ok))

        all_pass = True
        for name, passed in checks:
            status = "PASS" if passed else "FAIL"
            if not passed:
                all_pass = False
            print(f"  [{status}] {name}")

        print("=" * 60)
        if all_pass:
            print("ALL CHECKS PASSED")
        else:
            print("SOME CHECKS FAILED — review logs above")
            sys.exit(1)

    print("=" * 60)


if __name__ == "__main__":
    main()
