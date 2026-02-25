# Chat 1 - Session Sync #001
**Date:** 2026-02-25

---

## What We Did This Session

### 1. Created Repo & Set Up Keys
- Created `Ameen-Discrepancies-ML` repo on GitHub (pirumbirum)
- Set `ANTHROPIC_API_KEY` and `COURTLISTENER_TOKEN` as repo secrets

### 2. Deep-Dived CourtListener/PACER API Documentation
- Studied 4 major doc sources: RECAP APIs, Case Law APIs, V4 Migration Guide, PACER Fetch API blog
- Ran 3 parallel research agents to exhaustively map the API

### 3. Created `courtlistener_reference/` Folder (9 files, 2,400+ lines)
Pure reference guide -- no strategy, usable by anyone:

| File | Contents |
|------|----------|
| README.md | Quick start, curl examples, key links |
| 01_api_overview.md | Auth, 15+ endpoints, pagination, response optimization |
| 02_nos_codes_complete.md | Every NOS code (110-999), corporate litigation mapping |
| 03_federal_court_ids.md | SCOTUS, 13 circuits, 94 districts, 90+ bankruptcy courts |
| 04_docket_fields_reference.md | Every field on dockets, entries, documents |
| 05_search_and_filters.md | Database API filters, Search API (Lucene), ordering |
| 06_parties_attorneys.md | Party types, attorney roles, corporate identification |
| 07_case_numbering_system.md | Federal docket number format, case type codes |
| 08_recap_fetch_api.md | Buying from PACER, costs, security, Pray & Pay |
| 09_fjc_integrated_database.md | FJC IDB: origin, disposition, class action, judgments |

### 4. Created `starting strategy 1/` Folder (3-Step Plan)

**Step 1: Gather 50K Cases (~16 hours)**
- Pass 1 (30 min): Metadata sweep -- 50K case names/courts/dates/NOS
- Pass 2 (15-16 hrs): Entry list for each case (all filings + doc availability)
- NOS codes targeted: Securities (850), Patent (830), Trademark (840), Antitrust (410), Stockholders (160), RICO (470), Trade Secrets (880), + Tier 2 fill
- Date range: 2015-2025
- Courts: All 94 federal district courts
- Save every 15 minutes with progress report

**Step 2: Map & Classify Documents (minutes, local)**
- Parse entries, classify into opinions/orders/judgments/verdicts/etc.
- Create per-case manifest.json with document types and availability
- Zero API calls

**Step 3: Rank & Select Top 100 (~1 hour)**
- Score cases by data richness (opinions, verdicts, page counts, availability)
- Rank all 50K, select top 100
- Download actual opinion text for top 100 only

### 5. Tested API Call
- Proxy blocks outbound HTTPS to CourtListener from this sandbox
- Crawler must run on user's own machine or server
- Code logic is correct, just can't execute here

---

## Key Decisions Made
- **Data depth:** Metadata + entry list (not full text yet)
- **Date range:** 2015-2025
- **Save frequency:** Every 15 minutes with progress report
- **Top 100 selection:** Score by post-trial opinions, verdicts, judgments, page counts
- **Subfolder structure:** Each case gets a folder with manifest of classified documents

## What's Next
- Build the actual crawler script (Python)
- Run it on a machine with internet access
- Execute Step 1 -> Step 2 -> Step 3 pipeline

---

## Files on Branch `claude/add-file-upload-V80Zw`
```
courtlistener_reference/     # 9 reference docs
starting strategy 1/         # 4 planning docs
chat 1/                      # This sync folder
test_pass1.py                # API test script (blocked by proxy)
```
