#!/usr/bin/env python3
"""Test what CourtListener endpoints and RECAP files our token can access."""

import json
import os
import sys
import urllib.request
import urllib.error

TOKEN = os.environ.get("CL_API_TOKEN", "") or os.environ.get("COURTLISTENER_TOKEN", "")
BASE = "https://www.courtlistener.com/api/rest/v4"

if not TOKEN:
    print("FATAL: No token")
    sys.exit(1)


def hit(label, url):
    try:
        req = urllib.request.Request(url, headers={
            "Authorization": f"Token {TOKEN}",
            "User-Agent": "Ameen-AccessTest/1.0",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            print(f"  OK    {label}")
            return data
    except urllib.error.HTTPError as e:
        print(f"  {e.code}   {label}")
        return None
    except Exception as e:
        print(f"  ERR   {label}: {e}")
        return None


results = {}

print("=" * 60)
print("ENDPOINT ACCESS TEST")
print("=" * 60)

# Test each endpoint
endpoints = [
    ("dockets", f"{BASE}/dockets/?page_size=1"),
    ("docket-entries", f"{BASE}/docket-entries/?page_size=1"),
    ("recap-documents", f"{BASE}/recap-documents/?page_size=1"),
    ("recap-query", f"{BASE}/recap-query/?docket_entry__docket__court=dcd&pacer_doc_id__in=04505578698"),
    ("clusters", f"{BASE}/clusters/?page_size=1"),
    ("opinions", f"{BASE}/opinions/?page_size=1"),
    ("courts", f"{BASE}/courts/?page_size=1"),
    ("parties", f"{BASE}/parties/?page_size=1"),
    ("attorneys", f"{BASE}/attorneys/?page_size=1"),
    ("people", f"{BASE}/people/?page_size=1"),
    ("search (type=d)", f"{BASE}/search/?type=d&q=test"),
    ("search (type=r)", f"{BASE}/search/?type=r&q=test"),
    ("search (type=rd)", f"{BASE}/search/?type=rd&q=test"),
    ("search (type=o)", f"{BASE}/search/?type=o&q=test"),
    ("audio", f"{BASE}/audio/?page_size=1"),
    ("fjc-integrated-database", f"{BASE}/fjc-integrated-database/?page_size=1"),
    ("recap-fetch (GET)", f"{BASE}/recap-fetch/?page_size=1"),
    ("recap (upload, GET)", f"{BASE}/recap/?page_size=1"),
    ("prayers", f"{BASE}/prayers/"),
    ("financial-disclosures", f"{BASE}/financial-disclosures/?page_size=1"),
    ("tags", f"{BASE}/tags/?page_size=1"),
]

for label, url in endpoints:
    data = hit(label, url)
    if data:
        count = data.get("count", "N/A")
        results[label] = {"status": "OK", "count": count}
    else:
        results[label] = {"status": "DENIED"}

print()
print("=" * 60)
print("RECAP DOCUMENT FILE ACCESS TEST")
print("=" * 60)

# Try to get an available RECAP document with filepath_local
print("\n1. Finding an available RECAP document...")
doc_data = hit("recap-documents (available)",
               f"{BASE}/recap-documents/?is_available=true&page_size=1"
               f"&fields=id,filepath_local,filepath_ia,is_available,page_count,file_size,description,document_type")

if doc_data and doc_data.get("results"):
    doc = doc_data["results"][0]
    print(f"\n   Document ID: {doc.get('id')}")
    print(f"   is_available: {doc.get('is_available')}")
    print(f"   filepath_local: {doc.get('filepath_local')}")
    print(f"   filepath_ia: {doc.get('filepath_ia')}")
    print(f"   page_count: {doc.get('page_count')}")
    print(f"   file_size: {doc.get('file_size')}")
    print(f"   description: {doc.get('description', '')[:100]}")
    print(f"   document_type: {doc.get('document_type')}")

    # Try to download the actual PDF
    fp = doc.get("filepath_local")
    if fp:
        pdf_url = f"https://storage.courtlistener.com/{fp}"
        print(f"\n2. Trying to download PDF from: {pdf_url}")
        try:
            req = urllib.request.Request(pdf_url, headers={
                "Authorization": f"Token {TOKEN}",
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                content_type = resp.headers.get("Content-Type", "")
                content_length = resp.headers.get("Content-Length", "unknown")
                # Read just the first 1KB to verify
                first_bytes = resp.read(1024)
                is_pdf = first_bytes[:5] == b"%PDF-"
                print(f"   OK — Content-Type: {content_type}, Size: {content_length}")
                print(f"   Starts with %PDF-: {is_pdf}")
                results["pdf_download"] = {"status": "OK", "content_type": content_type, "is_pdf": is_pdf}
        except urllib.error.HTTPError as e:
            print(f"   FAILED — HTTP {e.code}")
            results["pdf_download"] = {"status": f"HTTP_{e.code}"}
        except Exception as e:
            print(f"   FAILED — {e}")
            results["pdf_download"] = {"status": f"ERROR: {e}"}

    # Also try the Internet Archive path
    ia = doc.get("filepath_ia")
    if ia:
        print(f"\n3. Trying Internet Archive: {ia}")
        try:
            req = urllib.request.Request(ia)
            with urllib.request.urlopen(req, timeout=30) as resp:
                content_type = resp.headers.get("Content-Type", "")
                first_bytes = resp.read(1024)
                is_pdf = first_bytes[:5] == b"%PDF-"
                print(f"   OK — Content-Type: {content_type}")
                print(f"   Starts with %PDF-: {is_pdf}")
                results["ia_download"] = {"status": "OK", "is_pdf": is_pdf}
        except urllib.error.HTTPError as e:
            print(f"   FAILED — HTTP {e.code}")
            results["ia_download"] = {"status": f"HTTP_{e.code}"}
        except Exception as e:
            print(f"   FAILED — {e}")
else:
    print("   Could not find an available RECAP document")

print()
print("=" * 60)
print("RECAP DOCUMENT TEXT ACCESS TEST")
print("=" * 60)

# Try to get plain_text from a RECAP document
print("\n4. Getting plain_text from a RECAP document...")
text_data = hit("recap-doc with text",
                f"{BASE}/recap-documents/?is_available=true&page_size=1"
                f"&fields=id,plain_text,ocr_status")

if text_data and text_data.get("results"):
    doc = text_data["results"][0]
    text = doc.get("plain_text", "")
    print(f"   Document ID: {doc.get('id')}")
    print(f"   OCR status: {doc.get('ocr_status')}")
    print(f"   plain_text length: {len(text)} chars")
    if text:
        print(f"   First 300 chars: {text[:300]}")
        results["plain_text"] = {"status": "OK", "length": len(text)}
    else:
        print("   (empty)")
        results["plain_text"] = {"status": "EMPTY"}

print()
print("=" * 60)
print("DOCKET ENTRY + NESTED DOCS TEST")
print("=" * 60)

# Find a docket with entries
print("\n5. Getting docket entries with nested RECAP docs...")
# Use a known busy docket from search
search_data = hit("search for busy docket",
                  f"{BASE}/search/?type=r&available_only=on&q=*")

if search_data and search_data.get("results"):
    docket_id = search_data["results"][0].get("docket_id")
    print(f"   Using docket_id: {docket_id}")

    entries = hit("docket-entries for docket",
                  f"{BASE}/docket-entries/?docket={docket_id}&page_size=3"
                  f"&omit=recap_documents__plain_text")
    if entries and entries.get("results"):
        print(f"   Entry count: {entries.get('count')}")
        for e in entries["results"][:2]:
            print(f"   Entry #{e.get('entry_number')}: {e.get('description','')[:80]}")
            for rd in e.get("recap_documents", [])[:2]:
                print(f"     Doc {rd.get('id')}: available={rd.get('is_available')}, "
                      f"pages={rd.get('page_count')}, type={rd.get('document_type')}")
        results["docket_entries_nested"] = {"status": "OK", "count": entries.get("count")}

print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)

for label, r in sorted(results.items()):
    print(f"  {label:35s}: {r}")

# Save results
os.makedirs("research", exist_ok=True)
with open("research/access_test_results.json", "w") as f:
    json.dump(results, f, indent=2, default=str)
print("\nSaved to research/access_test_results.json")
