"""
Shared crawler library for CourtListener API workflows.

Provides:
- Rate-limited API client
- Checkpoint/resume system
- Progress reporting
- Artifact saving with periodic commits

All workflows import from this single module to avoid code duplication.
"""

import requests
import json
import os
import sys
import time
import hashlib
from datetime import datetime, timedelta
from pathlib import Path


class RateLimiter:
    """Track API calls and enforce rate limits."""

    def __init__(self, max_per_hour=4800, buffer=200):
        self.max_per_hour = max_per_hour
        self.buffer = buffer
        self.effective_limit = max_per_hour - buffer
        self.calls = []  # timestamps of recent calls
        self.total_calls = 0

    def wait_if_needed(self):
        """Sleep if we're approaching the rate limit."""
        now = time.time()
        one_hour_ago = now - 3600

        # Remove calls older than 1 hour
        self.calls = [t for t in self.calls if t > one_hour_ago]

        if len(self.calls) >= self.effective_limit:
            # Calculate how long to wait for the oldest call to expire
            oldest = self.calls[0]
            wait_seconds = (oldest + 3600) - now + 1
            if wait_seconds > 0:
                print(f"  [RATE LIMIT] {len(self.calls)} calls in last hour. "
                      f"Sleeping {wait_seconds:.0f}s...")
                time.sleep(wait_seconds)

        self.calls.append(time.time())
        self.total_calls += 1

    def get_stats(self):
        now = time.time()
        one_hour_ago = now - 3600
        recent = [t for t in self.calls if t > one_hour_ago]
        return {
            "total_calls": self.total_calls,
            "calls_last_hour": len(recent),
            "remaining_this_hour": max(0, self.effective_limit - len(recent)),
        }


class CourtListenerClient:
    """Rate-limited CourtListener API client with retry logic."""

    def __init__(self, token=None, max_per_hour=4800):
        self.token = token or os.environ.get("COURTLISTENER_TOKEN", "")
        if not self.token:
            print("ERROR: No CourtListener API token provided")
            sys.exit(1)

        self.base_url = "https://www.courtlistener.com/api/rest/v4"
        self.headers = {"Authorization": f"Token {self.token}"}
        self.rate_limiter = RateLimiter(max_per_hour=max_per_hour)
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def get(self, endpoint, params=None, max_retries=3):
        """Make a GET request with rate limiting and retry logic."""
        self.rate_limiter.wait_if_needed()

        url = endpoint if endpoint.startswith("http") else f"{self.base_url}/{endpoint}"

        for attempt in range(max_retries):
            try:
                resp = self.session.get(url, params=params, timeout=30)

                if resp.status_code == 429:
                    wait = min(60 * (2 ** attempt), 300)
                    print(f"  [429] Rate limited. Waiting {wait}s (attempt {attempt+1}/{max_retries})")
                    time.sleep(wait)
                    continue

                if resp.status_code == 200:
                    return resp.json()

                if resp.status_code in (500, 502, 503, 504):
                    wait = 5 * (2 ** attempt)
                    print(f"  [{resp.status_code}] Server error. Waiting {wait}s (attempt {attempt+1}/{max_retries})")
                    time.sleep(wait)
                    continue

                # Non-retryable error
                print(f"  ERROR: {resp.status_code} - {resp.text[:300]}")
                return None

            except requests.RequestException as e:
                wait = 5 * (2 ** attempt)
                print(f"  [NETWORK] {e}. Waiting {wait}s (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)

        print(f"  FAILED after {max_retries} attempts")
        return None

    def paginate(self, endpoint, params=None, max_pages=None, callback=None):
        """
        Paginate through all results from an endpoint.

        Args:
            endpoint: API endpoint (e.g., "dockets/")
            params: Query parameters
            max_pages: Stop after this many pages (None = all)
            callback: Called with (page_num, results) after each page

        Yields:
            Individual result dicts
        """
        page = 0
        next_url = None

        while True:
            page += 1
            if max_pages and page > max_pages:
                break

            if next_url:
                data = self.get(next_url)
            else:
                data = self.get(endpoint, params=params)

            if not data:
                break

            results = data.get("results", [])
            if callback:
                callback(page, results)

            for result in results:
                yield result

            next_url = data.get("next")
            if not next_url:
                break


class Checkpoint:
    """Save and resume progress across workflow runs."""

    def __init__(self, filepath="checkpoint.json"):
        self.filepath = filepath
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.filepath):
            with open(self.filepath) as f:
                return json.load(f)
        return {}

    def save(self):
        os.makedirs(os.path.dirname(self.filepath) or ".", exist_ok=True)
        with open(self.filepath, "w") as f:
            json.dump(self.data, f, indent=2)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def is_completed(self, key):
        return self.data.get(f"{key}_completed", False)

    def mark_completed(self, key):
        self.data[f"{key}_completed"] = True
        self.data[f"{key}_completed_at"] = datetime.utcnow().isoformat()
        self.save()


class ProgressReporter:
    """Track and report crawl progress."""

    def __init__(self, total_expected=0):
        self.total_expected = total_expected
        self.collected = 0
        self.errors = 0
        self.start_time = time.time()
        self.last_report_time = time.time()
        self.report_interval = 900  # 15 minutes

    def add(self, count=1):
        self.collected += count

    def add_error(self):
        self.errors += 1

    def should_report(self):
        return (time.time() - self.last_report_time) >= self.report_interval

    def report(self, extra=""):
        elapsed = time.time() - self.start_time
        rate = self.collected / max(elapsed, 1) * 3600
        pct = (self.collected / self.total_expected * 100) if self.total_expected else 0

        if self.total_expected and rate > 0:
            remaining = (self.total_expected - self.collected) / (rate / 3600)
            eta = f"{remaining/60:.0f}m"
        else:
            eta = "unknown"

        print(f"\n{'=' * 60}")
        print(f"PROGRESS REPORT @ {datetime.utcnow().strftime('%H:%M:%S UTC')}")
        print(f"{'=' * 60}")
        print(f"  Collected: {self.collected:>8,} / {self.total_expected:>8,} ({pct:.1f}%)")
        print(f"  Errors:    {self.errors:>8,}")
        print(f"  Rate:      {rate:>8,.0f} /hour")
        print(f"  Elapsed:   {elapsed/60:>8.1f} min")
        print(f"  ETA:       {eta}")
        if extra:
            print(f"  Note:      {extra}")
        print(f"{'=' * 60}\n")

        self.last_report_time = time.time()


def save_json(data, filepath):
    """Save data as JSON, creating directories as needed."""
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    return filepath


def load_json(filepath, default=None):
    """Load JSON file, returning default if not found."""
    if os.path.exists(filepath):
        with open(filepath) as f:
            return json.load(f)
    return default if default is not None else {}
