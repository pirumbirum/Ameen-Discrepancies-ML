#!/usr/bin/env python3
"""
Enrich golden_set_general cases with docket entry counts from CourtListener API.

The /recap-documents/ endpoint requires special permission (has_recap_api_access),
so we use /docket-entries/ instead to get the count of court filings per case.

For each of the ~37K qualifying cases, makes 1 API call:
  GET /docket-entries/?docket={id}&format=json&page_size=1
  → reads 'count' from pagination (no need to fetch actual entries)

Falls back to /dockets/{id}/ if docket-entries also requires permission.

Runs in 4-hour sessions (--max-minutes 240) with checkpoint/resume.
Git commits every 30 minutes with progress stats.
~8 hours total = 2 workflow runs to complete.

Requires CL_API_TOKEN or COURTLISTENER_TOKEN env var.
"""

import argparse
import json
import os
import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CL_API = "https://www.courtlistener.com/api/rest/v4"
OUTPUT_DIR = "golden_set_general"
COUNTS_FILE = "golden_set_general/_entry_counts.json"
CHECKPOINT_FILE = "golden_set_general/_recap_checkpoint.json"

CALLS_PER_HOUR = 4600
MIN_SLEEP = 3600 / CALLS_PER_HOUR  # ~0.78s
GIT_COMMIT_INTERVAL = 1800  # 30 minutes
MAX_MINUTES = 240  # 4 hours default

CATEGORY_ORDER = [
    "banks", "trade_secret", "stockholders", "antitrust",
    "environmental", "rico", "securities", "trademark",
    "patent", "other_contract", "insurance",
]

# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
try:
    import requests
except ImportError:
    print("Installing requests...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests


class APIClient:
    """Rate-limited CourtListener client."""

    def __init__(self, token):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Token {token}",
            "User-Agent": "Ameen-EntryCounts/1.0",
        })
        self.call_timestamps = []
        self.total_calls = 0
        self.total_errors = 0
        self.endpoint_mode = None  # set during probe

    def _enforce_rate_limit(self):
        now = time.time()
        self.call_timestamps = [t for t in self.call_timestamps
                                if t > now - 3600]
        if len(self.call_timestamps) >= CALLS_PER_HOUR:
            wait = (self.call_timestamps[0] + 3600) - now + 1
            if wait > 0:
                print(f"  [RATE LIMIT] sleeping {wait:.0f}s")
                time.sleep(wait)
        if self.call_timestamps:
            since_last = now - self.call_timestamps[-1]
            if since_last < MIN_SLEEP:
                time.sleep(MIN_SLEEP - since_last)
        self.call_timestamps.append(time.time())
        self.total_calls += 1

    def probe_endpoints(self, test_docket_id):
        """Test which endpoints are accessible. Returns True if any work."""
        debug_file = os.path.join(OUTPUT_DIR, "_recap_debug.log")
        # Clear previous debug log
        try:
            with open(debug_file, "w") as f:
                f.write(f"=== Endpoint probe at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        except Exception:
            pass

        endpoints = [
            ("docket-entries",
             f"{CL_API}/docket-entries/?docket={test_docket_id}&format=json&page_size=1",
             lambda data: data.get("count", 0)),
            ("recap-documents",
             f"{CL_API}/recap-documents/?docket_entry__docket={test_docket_id}&format=json&page_size=1",
             lambda data: data.get("count", 0)),
            ("dockets-detail",
             f"{CL_API}/dockets/{test_docket_id}/?format=json",
             lambda data: len(data.get("docket_entries", []))),
        ]

        for name, url, extractor in endpoints:
            self._enforce_rate_limit()
            print(f"\n  Testing /{name}/ ...")
            print(f"    URL: {url}")
            try:
                resp = self.session.get(url, timeout=30)
                print(f"    Status: {resp.status_code}")
                self._log_debug(test_docket_id, url, resp)

                if resp.status_code == 200:
                    data = resp.json()
                    count = extractor(data)
                    print(f"    SUCCESS! count={count}")
                    print(f"    Response keys: {list(data.keys())}")
                    self.endpoint_mode = name
                    return True
                else:
                    body = resp.text[:200]
                    print(f"    FAILED: {body}")
            except Exception as e:
                print(f"    ERROR: {e}")

        print("\n  WARNING: No accessible endpoint found!")
        return False

    def get_entry_count(self, docket_id):
        """Get docket entry count. Returns int or None on error."""
        self._enforce_rate_limit()

        if self.endpoint_mode == "docket-entries":
            url = (f"{CL_API}/docket-entries/"
                   f"?docket={docket_id}"
                   f"&format=json&page_size=1")
        elif self.endpoint_mode == "recap-documents":
            url = (f"{CL_API}/recap-documents/"
                   f"?docket_entry__docket={docket_id}"
                   f"&format=json&page_size=1")
        elif self.endpoint_mode == "dockets-detail":
            url = f"{CL_API}/dockets/{docket_id}/?format=json"
        else:
            return None

        for attempt in range(3):
            try:
                resp = self.session.get(url, timeout=30)

                # Debug first few calls
                if self.total_calls <= 10 or (self.total_errors > 0 and self.total_errors <= 5):
                    self._log_debug(docket_id, url, resp)

                if resp.status_code == 200:
                    data = resp.json()
                    if self.endpoint_mode == "dockets-detail":
                        return len(data.get("docket_entries", []))
                    return data.get("count", 0)
                if resp.status_code == 429:
                    wait = 60 * (2 ** attempt)
                    print(f"    [429] Rate limited, waiting {wait}s")
                    time.sleep(wait)
                    self._enforce_rate_limit()
                    continue
                if resp.status_code == 401:
                    print("FATAL: 401 Unauthorized")
                    self._log_debug(docket_id, url, resp)
                    sys.exit(1)
                if resp.status_code == 403:
                    self.total_errors += 1
                    if self.total_errors <= 5:
                        print(f"    [403] Permission denied for docket {docket_id}")
                    return None
                if resp.status_code in (500, 502, 503, 504):
                    print(f"    [{resp.status_code}] Server error for docket {docket_id}")
                    time.sleep(5 * (2 ** attempt))
                    continue

                self.total_errors += 1
                if self.total_errors <= 10:
                    print(f"    [ERROR] docket={docket_id} "
                          f"HTTP {resp.status_code}: {resp.text[:200]}")
                return None
            except requests.RequestException as e:
                self.total_errors += 1
                print(f"    [NETWORK] docket={docket_id} error={e}")
                time.sleep(5 * (2 ** attempt))

        return None

    def _log_debug(self, docket_id, url, resp):
        """Write API debug info to a file that gets committed."""
        debug_file = os.path.join(OUTPUT_DIR, "_recap_debug.log")
        try:
            with open(debug_file, "a") as f:
                f.write(f"\n--- docket={docket_id} call#{self.total_calls} ---\n")
                f.write(f"URL: {url}\n")
                f.write(f"Status: {resp.status_code}\n")
                body = resp.text[:500]
                f.write(f"Body: {body}\n")
        except Exception:
            pass

    def stats_str(self):
        return f"API: {self.total_calls:,} calls, {self.total_errors:,} errors"


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {"completed_categories": [], "partial_category": None,
            "partial_idx": 0}


def save_checkpoint(ckpt):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(ckpt, f)


# ---------------------------------------------------------------------------
# Load/save counts
# ---------------------------------------------------------------------------

def load_counts():
    if os.path.exists(COUNTS_FILE):
        with open(COUNTS_FILE) as f:
            return json.load(f)
    return {}


def save_counts(counts):
    with open(COUNTS_FILE, "w") as f:
        json.dump(counts, f, indent=2)


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------

_last_git_time = 0


def git_commit(msg):
    global _last_git_time
    try:
        subprocess.run(["git", "add", "golden_set_general/"],
                       check=True, capture_output=True)
        result = subprocess.run(["git", "diff", "--cached", "--quiet"],
                                capture_output=True)
        if result.returncode == 0:
            return
        subprocess.run(["git", "commit", "-m", msg],
                       check=True, capture_output=True)
        # Pull-rebase to handle concurrent workflow commits
        subprocess.run(["git", "pull", "--rebase", "origin",
                        os.environ.get("GITHUB_REF_NAME", "")],
                       capture_output=True, timeout=60)
        subprocess.run(["git", "push"],
                       check=True, capture_output=True, timeout=120)
        print(f"  [git] committed + pushed: {msg}")
        _last_git_time = time.time()
    except Exception as e:
        print(f"  [git] WARNING: {e}")


def maybe_git_commit(msg):
    global _last_git_time
    if time.time() - _last_git_time >= GIT_COMMIT_INTERVAL:
        git_commit(msg)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-minutes", type=int, default=MAX_MINUTES)
    args = parser.parse_args()
    max_minutes = args.max_minutes

    token = (os.environ.get("CL_API_TOKEN", "")
             or os.environ.get("COURTLISTENER_TOKEN", ""))
    if not token:
        print("FATAL: Set CL_API_TOKEN or COURTLISTENER_TOKEN env var")
        sys.exit(1)

    client = APIClient(token)

    # Test basic API connectivity
    print("Testing API connection...")
    client._enforce_rate_limit()
    resp = client.session.get(f"{CL_API}/courts/?format=json&page_size=1",
                              timeout=30)
    if resp.status_code != 200:
        print(f"FATAL: API test failed ({resp.status_code})")
        sys.exit(1)
    print("API OK\n")

    # Load all docket IDs from golden_set_general
    print("Loading docket IDs from golden_set_general...")
    all_dockets = {}  # {cat: [docket_id, ...]}
    total_dockets = 0
    for cat in CATEGORY_ORDER:
        idx_file = os.path.join(OUTPUT_DIR, cat, "index.json")
        if not os.path.exists(idx_file):
            continue
        with open(idx_file) as f:
            idx = json.load(f)
        dids = [entry["docket_id"] for entry in idx]
        all_dockets[cat] = dids
        total_dockets += len(dids)
        print(f"  {cat:20s}: {len(dids):>6,}")
    print(f"  {'TOTAL':>20s}: {total_dockets:>6,}\n")

    # Probe endpoints to find one that works
    test_did = None
    for cat in CATEGORY_ORDER:
        if cat in all_dockets and all_dockets[cat]:
            test_did = all_dockets[cat][0]
            break

    if not test_did:
        print("FATAL: No docket IDs found")
        sys.exit(1)

    print(f"Probing API endpoints with docket {test_did}...")
    if not client.probe_endpoints(test_did):
        print("FATAL: No accessible endpoint found. "
              "The API token may lack permissions.")
        # Commit debug log so we can see it
        git_commit("entry_counts: FAILED — no accessible endpoint")
        sys.exit(1)

    print(f"\nUsing endpoint: {client.endpoint_mode}")

    # Load existing progress
    ckpt = load_checkpoint()
    counts = load_counts()

    # If switching from old recap_counts format, migrate
    old_counts_file = "golden_set_general/_recap_counts.json"
    if os.path.exists(old_counts_file) and not counts:
        try:
            with open(old_counts_file) as f:
                old = json.load(f)
            if old:
                print(f"  Migrating {len(old)} entries from old _recap_counts.json")
                counts.update(old)
        except Exception:
            pass

    already_done = len(counts)

    print("=" * 60)
    print(f"DOCKET ENTRY COUNT ENRICHMENT")
    print(f"  Endpoint: {client.endpoint_mode}")
    print(f"  Total dockets: {total_dockets:,}")
    print(f"  Already done: {already_done:,}")
    print(f"  Remaining: {total_dockets - already_done:,}")
    print(f"  Max time: {max_minutes} min")
    print(f"  Rate: ~{CALLS_PER_HOUR:,}/hour")
    eta_hours = (total_dockets - already_done) / CALLS_PER_HOUR
    print(f"  ETA for remaining: {eta_hours:.1f} hours")
    print("=" * 60)

    global _last_git_time
    _last_git_time = time.time()
    start_time = time.time()
    session_processed = 0
    hit_timeout = False

    for cat in CATEGORY_ORDER:
        if cat not in all_dockets:
            continue

        # Skip fully completed categories
        if cat in ckpt.get("completed_categories", []):
            cat_done = sum(1 for d in all_dockets[cat] if d in counts)
            print(f"\n{cat}: DONE (previous run) — {cat_done:,} counted")
            continue

        dids = all_dockets[cat]

        # Resume from partial checkpoint
        start_idx = 0
        if ckpt.get("partial_category") == cat:
            start_idx = ckpt.get("partial_idx", 0)

        print(f"\n{'=' * 60}")
        print(f"{cat}: {len(dids):,} dockets")
        if start_idx > 0:
            print(f"  Resuming from index {start_idx}")
        print("=" * 60)

        for i in range(start_idx, len(dids)):
            did = dids[i]

            # Time budget
            elapsed_min = (time.time() - start_time) / 60
            if elapsed_min >= max_minutes:
                print(f"\n  [TIMEOUT] {elapsed_min:.0f} min elapsed, "
                      f"stopping at {cat} [{i}/{len(dids)}]")
                ckpt["partial_category"] = cat
                ckpt["partial_idx"] = i
                save_checkpoint(ckpt)
                save_counts(counts)
                hit_timeout = True
                break

            # Skip if already counted
            if did in counts:
                continue

            # Progress every 50 dockets
            if session_processed % 50 == 0:
                total_done = len(counts)
                pct = total_done / max(total_dockets, 1) * 100
                remaining = total_dockets - total_done
                rate = session_processed / max(elapsed_min / 60, 0.01)
                eta_h = remaining / max(rate, 1)
                print(f"    [{total_done:,}/{total_dockets:,}] ({pct:.1f}%) "
                      f"| {cat} [{i}/{len(dids)}] "
                      f"| {client.stats_str()} "
                      f"| {elapsed_min:.0f}min elapsed "
                      f"| ETA {eta_h:.1f}h")
                sys.stdout.flush()

            # API call
            count = client.get_entry_count(did)
            if count is not None:
                counts[did] = count
            session_processed += 1

            # Checkpoint every 500
            if session_processed % 500 == 0:
                ckpt["partial_category"] = cat
                ckpt["partial_idx"] = i + 1
                save_checkpoint(ckpt)
                save_counts(counts)

            # Git commit every 30 min
            total_done = len(counts)
            maybe_git_commit(
                f"entry_counts: {total_done:,}/{total_dockets:,} "
                f"({cat} {i+1}/{len(dids)})")

        if hit_timeout:
            break

        # Only mark category completed if we actually got results
        cat_counted = sum(1 for d in dids if d in counts)
        if cat_counted == 0 and len(dids) > 0:
            print(f"  WARNING: {cat} got 0 counts for {len(dids)} dockets — "
                  f"NOT marking as completed (will retry)")
        else:
            ckpt.setdefault("completed_categories", []).append(cat)
        ckpt["partial_category"] = None
        ckpt["partial_idx"] = 0
        save_checkpoint(ckpt)
        save_counts(counts)

        cat_total = sum(counts.get(d, 0) for d in dids)
        git_commit(
            f"entry_counts: {cat} done — {cat_counted:,} dockets, "
            f"{cat_total:,} total entries")

    # Save final state
    save_counts(counts)
    save_checkpoint(ckpt)

    # Update category index.json files with entry counts
    count_field = "docket_entry_count"
    print(f"\nUpdating category index files with {count_field}...")
    for cat in CATEGORY_ORDER:
        idx_file = os.path.join(OUTPUT_DIR, cat, "index.json")
        if not os.path.exists(idx_file):
            continue
        with open(idx_file) as f:
            idx = json.load(f)
        updated = False
        for entry in idx:
            did = entry.get("docket_id", "")
            if did in counts and count_field not in entry:
                entry[count_field] = counts[did]
                updated = True
        if updated:
            with open(idx_file, "w") as f:
                json.dump(idx, f, indent=2)
            n = sum(1 for e in idx if count_field in e)
            print(f"  {cat:20s}: {n:,}/{len(idx):,} updated")

    # Final commit
    elapsed = time.time() - start_time
    total_done = len(counts)
    status = "COMPLETE" if not hit_timeout else "PARTIAL"
    remaining_cats = [c for c in CATEGORY_ORDER
                      if c in all_dockets
                      and c not in ckpt.get("completed_categories", [])]

    git_commit(
        f"entry_counts: {status} — {total_done:,}/{total_dockets:,} "
        f"({session_processed:,} this session, {elapsed/60:.0f}min)")

    # Report
    print(f"\n{'=' * 60}")
    print(f"RESULTS — {status}")
    print(f"  Endpoint used: {client.endpoint_mode}")
    print("=" * 60)
    for cat in CATEGORY_ORDER:
        if cat not in all_dockets:
            continue
        dids = all_dockets[cat]
        done = sum(1 for d in dids if d in counts)
        total = sum(counts.get(d, 0) for d in dids)
        avg = total / max(done, 1)
        mark = "DONE" if cat in ckpt.get("completed_categories", []) else "..."
        print(f"  {cat:20s}: {done:>6,}/{len(dids):>6,} counted  "
              f"total_entries={total:>8,}  avg={avg:>6.1f}  [{mark}]")

    total_entries = sum(counts.values())
    print(f"\n  Total: {total_done:,}/{total_dockets:,} dockets counted")
    print(f"  Total entries: {total_entries:,}")
    print(f"  This session: {session_processed:,} API calls in {elapsed/60:.1f} min")
    print(f"  {client.stats_str()}")

    if remaining_cats:
        print(f"\n  Remaining categories: {', '.join(remaining_cats)}")
        print("  Re-run to continue from checkpoint.")
    print("=" * 60)


if __name__ == "__main__":
    main()
