#!/usr/bin/env python3
"""Scrape CourtListener website pages and extract text content."""

import os
import re
import time
import urllib.request

OUTPUT_DIR = "research/site_pages"
os.makedirs(OUTPUT_DIR, exist_ok=True)

PAGES = [
    ("https://www.courtlistener.com/help/api/rest/pacer/", "pacer_api"),
    ("https://www.courtlistener.com/help/api/rest/recap/", "recap_api"),
    ("https://www.courtlistener.com/help/api/rest/", "rest_overview"),
    ("https://www.courtlistener.com/help/api/rest/search/", "search_api"),
    ("https://www.courtlistener.com/help/api/rest/case-law/", "case_law_api"),
    ("https://www.courtlistener.com/help/api/rest/citations/", "citations_api"),
    ("https://www.courtlistener.com/help/api/rest/judges/", "judges_api"),
    ("https://www.courtlistener.com/help/api/rest/financial-disclosures/", "financial_disclosures_api"),
    ("https://www.courtlistener.com/help/api/rest/visualizations/", "visualizations_api"),
    ("https://www.courtlistener.com/help/api/rest/fields/", "fields_api"),
    ("https://www.courtlistener.com/help/api/rest/permissions/", "permissions_api"),
    ("https://www.courtlistener.com/help/api/rest/changes/", "api_changes"),
    ("https://www.courtlistener.com/help/api/rest/alerts/", "alerts_api"),
    ("https://www.courtlistener.com/help/api/rest/webhooks/", "webhooks_api"),
    ("https://www.courtlistener.com/help/api/rest/v4/migration-guide/", "v4_migration"),
    ("https://www.courtlistener.com/help/api/", "api_overview"),
    ("https://www.courtlistener.com/help/api/bulk-data/", "bulk_data"),
    ("https://www.courtlistener.com/help/api/replication/", "replication"),
    ("https://www.courtlistener.com/help/coverage/", "coverage"),
    ("https://www.courtlistener.com/help/coverage/recap/", "recap_coverage"),
    ("https://www.courtlistener.com/help/coverage/opinions/", "opinion_coverage"),
    ("https://www.courtlistener.com/help/coverage/financial-disclosures/", "fd_coverage"),
    ("https://www.courtlistener.com/help/coverage/oral-arguments/", "oa_coverage"),
    ("https://www.courtlistener.com/help/", "help_main"),
    ("https://www.courtlistener.com/help/recap/", "help_recap"),
    ("https://www.courtlistener.com/help/recap/what-is-pacer/", "what_is_pacer"),
    ("https://www.courtlistener.com/help/search-operators/", "search_operators"),
    ("https://www.courtlistener.com/about/", "about"),
    ("https://www.courtlistener.com/faq/", "faq"),
    ("https://www.courtlistener.com/terms/", "terms"),
    ("https://www.courtlistener.com/recap/", "recap_main"),
    ("https://free.law/recap/", "freelaw_recap"),
    ("https://free.law/projects/recap/", "freelaw_recap_project"),
]


def strip_html(html):
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', '\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


for url, name in PAGES:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Ameen-Research/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        with open(os.path.join(OUTPUT_DIR, f"{name}.html"), "w") as f:
            f.write(html)

        text = strip_html(html)
        with open(os.path.join(OUTPUT_DIR, f"{name}.txt"), "w") as f:
            f.write(text)

        print(f"OK  {url}  ({len(text):,} chars)")
    except Exception as e:
        print(f"FAIL  {url}  {e}")
    time.sleep(0.5)

print("\nDone.")
