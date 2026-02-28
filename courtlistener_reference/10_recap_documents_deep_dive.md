# RECAP Documents API - Deep Dive Reference

## Table of Contents
1. [What RECAP Data Is Available](#1-what-recap-data-is-available)
2. [The Data Model: Dockets -> Entries -> Documents](#2-the-data-model)
3. [The recap-documents Endpoint](#3-the-recap-documents-endpoint)
4. [The docket-entries Endpoint](#4-the-docket-entries-endpoint)
5. [Search API for RECAP (type=r, type=rd, type=d)](#5-search-api-for-recap)
6. [RECAP Document Fields Reference](#6-recap-document-fields-reference)
7. [Strategies for Scoring RECAP Data Richness](#7-strategies-for-scoring-recap-data-richness)
8. [Bulk Data: What Is and Is NOT Available](#8-bulk-data)
9. [The Docket Source Bitmask](#9-docket-source-bitmask)
10. [Concrete API Recipes](#10-concrete-api-recipes)

---

## 1. What RECAP Data Is Available

The RECAP Archive contains:
- **Nearly every federal case** (60M+ dockets with basic metadata)
- **Hundreds of millions of docket entries** (~100K new entries/day)
- **Tens of millions of PDF documents** (thousands of new docs/day)
- **150M+ document metadata records** (short descriptions from RSS feeds, added early 2023)

Key distinction: A "RECAP document" record can exist in two states:
- **`is_available=true`**: The actual PDF has been downloaded and is stored in the RECAP Archive
- **`is_available=false`**: CourtListener knows the document exists on PACER (has metadata like `pacer_doc_id`, `description`) but the PDF has NOT been downloaded yet

This means most dockets have document *metadata* (entry descriptions, document numbers) but only a fraction have the actual downloadable PDFs.

---

## 2. The Data Model

```
Docket (case-level)
  |
  +-- DocketEntry (one row on the PACER docket sheet)
  |     |
  |     +-- RECAPDocument (document_type=1, main document)
  |     +-- RECAPDocument (document_type=2, attachment/exhibit)
  |     +-- RECAPDocument (document_type=2, attachment/exhibit)
  |
  +-- DocketEntry
  |     +-- RECAPDocument (main)
  ...
```

### Key Relationships
- **Docket -> DocketEntry**: One-to-many via `docket_entry.docket` FK
- **DocketEntry -> RECAPDocument**: One-to-many via `recap_document.docket_entry` FK
- **Reverse access**: `docket_entry.recap_documents` (plural) gives all documents for an entry
- **Unique constraint**: Each document uniquely identified by `(docket_entry, document_number, attachment_number)`

### Important Design Constraint
Docket entries and RECAP documents are **NOT nested** in docket API responses. A single docket can have thousands of entries, so they must be queried separately:
```
GET /api/rest/v4/docket-entries/?docket={docket_id}
GET /api/rest/v4/recap-documents/?docket_entry__docket={docket_id}
```

---

## 3. The recap-documents Endpoint

### Base URL
```
GET https://www.courtlistener.com/api/rest/v4/recap-documents/
GET https://www.courtlistener.com/api/rest/v4/recap-documents/{id}/
```

### All Available Filters (from source code RECAPDocumentFilter)

| Filter | Lookup Types | Example |
|--------|-------------|---------|
| `id` | exact, gte, gt, lte, lt, range | `?id__gte=100` |
| `docket_entry__docket` | (via DocketEntryFilter -> DocketFilter) | `?docket_entry__docket=67591026` |
| `docket_entry` | (via DocketEntryFilter) | `?docket_entry=12345` |
| `date_created` | exact, gte, gt, lte, lt, range | `?date_created__gte=2024-01-01` |
| `date_modified` | exact, gte, gt, lte, lt, range | `?date_modified__gte=2024-01-01` |
| `date_upload` | exact, gte, gt, lte, lt, range | `?date_upload__gte=2024-01-01` |
| `document_type` | exact | `?document_type=1` (main docs), `?document_type=2` (attachments) |
| `document_number` | exact, gte, gt, lte, lt | `?document_number=15` |
| `pacer_doc_id` | exact, in | `?pacer_doc_id=04506123456` |
| `is_available` | exact | `?is_available=true` |
| `is_free_on_pacer` | exact | `?is_free_on_pacer=true` |
| `sha1` | exact | `?sha1=abc123...` |
| `ocr_status` | exact, gte, gt, lte, lt, range | `?ocr_status=1` |
| `tags` | (via TagFilter) | |

### Chaining Through Relationships

Because `docket_entry` links to `DocketEntryFilter` which links to `DocketFilter`, you can chain filters:
```
# All available docs for a specific docket:
?docket_entry__docket=67591026&is_available=true

# All available docs in SDNY:
?docket_entry__docket__court=nysd&is_available=true

# All main docs for a docket (no attachments):
?docket_entry__docket=67591026&document_type=1
```

### Ordering Options
```
?order_by=id              # Default: -id (newest first)
?order_by=date_created
?order_by=date_modified
?order_by=date_upload
```

### Response Optimization
```
# Minimal fields for counting/scanning:
?fields=id,document_type,is_available,page_count,file_size,document_number

# Exclude the massive plain_text field:
?omit=plain_text

# Just check availability:
?fields=id,is_available,page_count
```

---

## 4. The docket-entries Endpoint

### Base URL
```
GET https://www.courtlistener.com/api/rest/v4/docket-entries/
GET https://www.courtlistener.com/api/rest/v4/docket-entries/{id}/
```

### All Available Filters (from DocketEntryFilter source)

| Filter | Lookup Types | Example |
|--------|-------------|---------|
| `id` | exact, gte, gt, lte, lt, range | `?id__gte=100` |
| `docket` | (via DocketFilter, full chain) | `?docket=67591026` |
| `entry_number` | exact, gte, gt, lte, lt, range, isnull | `?entry_number=15` |
| `date_created` | exact, gte, gt, lte, lt, range | `?date_created__gte=2024-01-01` |
| `date_modified` | exact, gte, gt, lte, lt, range | `?date_modified__gte=2024-01-01` |
| `date_filed` | exact, gte, gt, lte, lt, range, year, month, day | `?date_filed__gte=2024-01-01` |
| `pacer_sequence_number` | exact, gte, gt, lte, lt, range, isnull | |
| `recap_documents` | (via RECAPDocumentFilter) | See below |
| `tags` | (via TagFilter) | |

### Critical: Nested RECAP Documents in Response

When you query docket-entries, each entry includes its RECAP documents as **nested objects**:
```json
{
    "id": 12345,
    "docket": "https://...dockets/67591026/",
    "entry_number": 15,
    "description": "MOTION to Dismiss...",
    "date_filed": "2024-02-01",
    "recap_documents": [
        {
            "id": 98765,
            "document_type": 1,
            "document_number": "15",
            "attachment_number": null,
            "is_available": true,
            "page_count": 25,
            "description": "",
            "pacer_doc_id": "04506123456",
            "filepath_local": "recap/gov.uscourts...",
            "plain_text": "UNITED STATES..."
        },
        {
            "id": 98766,
            "document_type": 2,
            "attachment_number": 1,
            "is_available": false,
            "description": "Exhibit A - Declaration..."
        }
    ]
}
```

### Performance Warning
**Always use `?omit=recap_documents__plain_text`** when listing docket entries. The `plain_text` field can be enormous (entire extracted document text) and will cause massive payloads.

### Ordering Options
```
?order_by=entry_number
?order_by=recap_sequence_number,entry_number    # PACER natural order
?order_by=date_filed,id
?order_by=id
?order_by=date_created
?order_by=date_modified
```

---

## 5. Search API for RECAP

The Search API (`/api/rest/v4/search/`) uses Elasticsearch, not the database. It has different field names (camelCase), different filters, and different behavior.

### type=r (Dockets with Nested Documents)

**Returns**: A list of dockets, each with up to 3 nested matching documents in `recap_documents`.

```
GET /api/rest/v4/search/?type=r&q=securities+fraud&court=nysd
```

**Response structure**:
```json
{
    "count": 1234,
    "document_count": 5678,
    "next": "...",
    "results": [
        {
            "docket_id": 67591026,
            "caseName": "Doe v. Smith",
            "docketNumber": "1:24-cv-01234",
            "court": "Southern District of New York",
            "court_id": "nysd",
            "dateFiled": "2024-01-15",
            "dateTerminated": null,
            "assignedTo": "Judge Roberts",
            "suitNature": "850",
            "docket_absolute_url": "/docket/67591026/...",
            "docket_slug": "doe-v-smith",
            "more_docs": true,
            "recap_documents": [
                {
                    "id": 98765,
                    "short_description": "Motion to Dismiss",
                    "description": "MOTION to Dismiss...",
                    "document_number": 15,
                    "attachment_number": null,
                    "document_type": "PACER Document",
                    "is_available": true,
                    "page_count": 25,
                    "entry_date_filed": "2024-02-01",
                    "entry_number": 15,
                    "pacer_doc_id": "04506123456",
                    "plain_text": "...",
                    "snippet": "<mark>securities</mark> fraud..."
                }
            ]
        }
    ]
}
```

**Key fields**:
- `more_docs`: `true` if more than 3 documents matched (only 3 are nested)
- `document_count`: total matching documents across all dockets (approximate, +/-6% if >2000)
- `count`: total matching dockets (approximate, +/-6% if >2000)

### type=rd (Flat Document List)

**Returns**: A flat list of individual RECAP documents (like type=r in v3).

```
GET /api/rest/v4/search/?type=rd&q=securities+fraud&court=nysd
```

**Response structure**: Each result is a single document with its parent docket info:
```json
{
    "count": 5678,
    "results": [
        {
            "docket_id": 67591026,
            "caseName": "Doe v. Smith",
            "court_id": "nysd",
            "short_description": "Motion to Dismiss",
            "description": "MOTION to Dismiss...",
            "document_number": 15,
            "document_type": "PACER Document",
            "is_available": true,
            "page_count": 25,
            "entry_date_filed": "2024-02-01",
            "pacer_doc_id": "04506123456"
        }
    ]
}
```

**Note**: Party and attorney fields are NOT available in type=rd results (they are docket-level fields).

### type=d (Docket-Only, Fastest)

**Returns**: Dockets without any nested documents. Fastest option.

```
GET /api/rest/v4/search/?type=d&suitNature=850&court=nysd
```

**Important**: You CAN query on document-level fields even though they are not returned. This means you can ask "find dockets that have available RECAP documents" without getting the documents back.

### Search API Query Fields (for `q=` parameter)

These are the fields you can use in fielded queries within the `q` parameter:

**Docket-level fields**:
| Field | Example |
|-------|---------|
| `caseName` | `caseName:(Apple Inc)` |
| `docketNumber` | `docketNumber:"1:24-cv-01234"` |
| `suitNature` | `suitNature:850` |
| `cause` | `cause:"28:1332"` |
| `assignedTo` | `assignedTo:"Roberts"` |
| `referredTo` | `referredTo:"Smith"` |
| `court` | `court:"Southern District"` |
| `court_id` | `court_id:nysd` |
| `party` | `party:Apple` |
| `attorney` | `attorney:"Kirkland Ellis"` |
| `chapter` | `chapter:11` |
| `trustee_str` | `trustee_str:"Smith"` |
| `pacer_case_id` | `pacer_case_id:123456` |

**Document-level fields**:
| Field | Example |
|-------|---------|
| `description` | `description:"motion to dismiss"` |
| `short_description` | `short_description:"disclosure statement"` |
| `document_type` | `document_type:"PACER Document"` |
| `document_number` | `document_number:15` |
| `attachment_number` | `attachment_number:1` |
| `is_available` | `is_available:true` |
| `page_count` | `page_count:[200 TO *]` (range query) |
| `plain_text` | `plain_text:"securities fraud"` |
| `entry_number` | `entry_number:15` |

### Search API GET Parameters (Sidebar Filters)

| Parameter | Description | Example |
|-----------|-------------|---------|
| `type` | Search type | `type=r`, `type=rd`, `type=d` |
| `q` | Main query | `q=securities fraud` |
| `court` | Court filter (space-separated) | `court=nysd nyed` |
| `filed_after` | Filed after date | `filed_after=2024-01-01` |
| `filed_before` | Filed before date | `filed_before=2024-12-31` |
| `party_name` | Party filter | `party_name=Apple` |
| `attorney` | Attorney filter | `attorney=Kirkland` |
| `nature_of_suit` | NOS filter | `nature_of_suit=850` |
| `cause` | Cause of action | `cause=28:1332` |
| `assigned_to` | Judge name | `assigned_to=Roberts` |
| `referred_to` | Referred judge | `referred_to=Smith` |
| `available_only` | Only available docs | `available_only=on` |
| `document_number` | Document number | `document_number=15` |
| `order_by` | Sort order | `order_by=dateFiled desc` |
| `highlight` | Enable highlighting | `highlight=on` |

### Important: `available_only=on`

This is the key filter for finding cases with actual downloadable RECAP PDFs. Use it as a GET parameter (not in `q=`):
```
GET /api/rest/v4/search/?type=r&suitNature=850&available_only=on
```

---

## 6. RECAP Document Fields Reference

### Complete Field List (Database API)

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `id` | integer | No | Primary key |
| `resource_uri` | URL | No | Canonical API URL |
| `absolute_url` | string | No | Path on CL website |
| `date_created` | datetime | No | Record creation timestamp |
| `date_modified` | datetime | No | Last modification timestamp |
| `date_upload` | datetime | Yes | When PDF was uploaded to RECAP |
| `document_type` | integer | No | **1** = PACER Document (main), **2** = Attachment |
| `document_number` | string(32) | No | Document number within entry |
| `attachment_number` | integer | Yes | Attachment sequence (null for main docs) |
| `pacer_doc_id` | string(64) | No | PACER's internal document ID |
| `is_available` | boolean | Yes | **PDF available in RECAP Archive** |
| `is_free_on_pacer` | boolean | Yes | Free as opinion on PACER |
| `is_sealed` | boolean | Yes | Document sealed on PACER |
| `description` | text | No | Short description from PACER |
| `filepath_local` | string(1000) | No | Local PDF storage path |
| `filepath_ia` | string(1000) | No | Internet Archive path |
| `sha1` | string(40) | No | SHA1 hash of PDF file |
| `page_count` | integer | Yes | **Number of pages in PDF** |
| `file_size` | integer | Yes | **File size in bytes** |
| `plain_text` | text | No | **Full extracted text** (can be enormous) |
| `ocr_status` | integer | Yes | 1=Complete, 2=Unnecessary, 3=Failed, 4=Needed |
| `thumbnail` | file | Yes | Thumbnail of first page |
| `thumbnail_status` | integer | No | 0=Needed, 1=Complete, 2=Failed |
| `tags` | array | No | Associated tags |

### Fields Available in Search Results (Elasticsearch)

| Field | Type | Notes |
|-------|------|-------|
| `id` | integer | Document PK |
| `docket_id` | integer | Parent docket PK |
| `docket_entry_id` | integer | Parent entry PK |
| `caseName` | text | Case name (camelCase) |
| `docketNumber` | text | Docket number |
| `court_id` | text | Court ID |
| `dateFiled` | date | Case filing date |
| `description` | text | Full description |
| `short_description` | text | Short description |
| `document_type` | text | "PACER Document" or "Attachment" (string, not integer) |
| `document_number` | long | Document number |
| `attachment_number` | integer | Attachment number |
| `entry_number` | long | Entry number on docket |
| `entry_date_filed` | date | Entry filing date |
| `is_available` | boolean | PDF available |
| `page_count` | integer | Pages in PDF |
| `pacer_doc_id` | keyword | PACER doc ID |
| `filepath_local` | keyword | PDF path (not indexed) |
| `absolute_url` | keyword | CL URL (not indexed) |
| `plain_text` | text | Full extracted text |
| `cites` | list[integer] | IDs of cited opinions |

---

## 7. Strategies for Scoring RECAP Data Richness

### Strategy 1: Direct Count via recap-documents Endpoint (Most Accurate, Slowest)

For a single docket, make 2 API calls:
```python
# Count of documents with actual PDFs available
resp1 = GET /api/rest/v4/recap-documents/
    ?docket_entry__docket={docket_id}
    &is_available=true
    &fields=id
    &page_size=1

available_count = resp1.json()["count"]  # Note: "count" may be a URL, use count=on

# Count of all known document records (including unavailable)
resp2 = GET /api/rest/v4/recap-documents/
    ?docket_entry__docket={docket_id}
    &fields=id
    &page_size=1

total_count = resp2.json()["count"]

richness_ratio = available_count / total_count if total_count > 0 else 0
```

**Cost**: 2 API calls per docket. For 275K dockets = 550K calls = ~110 hours at rate limit.

### Strategy 2: Page-Level Detail (More Granular)

Get page counts and file sizes for available documents:
```python
resp = GET /api/rest/v4/recap-documents/
    ?docket_entry__docket={docket_id}
    &is_available=true
    &fields=id,page_count,file_size,document_type
    &page_size=100

# Compute richness score
total_pages = sum(d["page_count"] or 0 for d in all_results)
total_files = len(all_results)
main_docs = sum(1 for d in all_results if d["document_type"] == 1)
attachments = sum(1 for d in all_results if d["document_type"] == 2)
```

**Cost**: 1+ API calls per docket (paginated at 20/page).

### Strategy 3: Search API for Batch Discovery (Fastest for Filtering)

Use type=r search to find dockets with rich RECAP data in bulk:
```
GET /api/rest/v4/search/
    ?type=r
    &suitNature=850
    &available_only=on
    &court=nysd
    &order_by=dateFiled desc
```

This returns dockets that have *at least some* available documents. Use `document_count` in the response to gauge total matching docs.

**Limitation**: You only get up to 3 nested documents per docket. Use `more_docs=true` to identify dockets with richer data.

### Strategy 4: Docket Source Bitmask Pre-Filter (Best for Bulk)

The `source` field on dockets is a bitmask. RECAP = 1. Any docket whose source includes the RECAP bit (source & 1 != 0) has data from RECAP.

From the bulk data CSV (`search_docket` table), filter:
```python
# Source values that include RECAP (bit 0 set):
# 1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29, 31,
# 33, 35, 37, 39, 41, 43, 45, 47, 49, 51, 53, 55, 57, 59, 61, 63,
# 65, 67, 69, 71, 73, 75, 77, 79, 81, 83, 85, 87, 89, 91, 93, 95,
# 97, 99, 101, 103, 105, 107, 109, 111, 113, 115, 117, 119, 121, 123, 125, 127
# i.e., any odd number from 1 to 127

recap_dockets = df[df["source"] % 2 == 1]  # source bitmask has RECAP bit set
```

**But this only tells you the docket has SOME RECAP data, not how much.**

### Strategy 5: Combined Efficient Approach (Recommended)

1. **Pre-filter with bulk data**: Download `search_docket` CSV. Filter to your NOS codes + courts. Check `source` bitmask for RECAP bit. This gives you candidate docket IDs (~free, no API calls).

2. **Batch count via docket-entries endpoint**: For each candidate, get entry count:
   ```
   GET /api/rest/v4/docket-entries/?docket={id}&page_size=1
   ```
   Response includes `count` telling you how many entries exist.

3. **Spot-check richness**: For dockets with many entries, count available documents:
   ```
   GET /api/rest/v4/recap-documents/?docket_entry__docket={id}&is_available=true&page_size=1
   ```

4. **Rank by ratio**: `available_docs / total_entries` gives RECAP richness.

### Strategy 6: Search API Aggregation Trick

Use type=d search with document-level query but docket-level results:
```
GET /api/rest/v4/search/?type=d&suitNature=850&q=is_available:true&court=nysd
```
This finds dockets that have at least one available document, without returning the documents. Very fast for identifying which dockets have RECAP data.

---

## 8. Bulk Data

### What IS Available in Bulk

The bulk data CSV exports (regenerated quarterly) include:
- **`search_docket`** - Full docket metadata including `source` bitmask, `case_name`, `nature_of_suit`, `court_id`, dates, etc.
- **`search_court`** - Court metadata
- **`search_opinioncluster`** and **`search_opinion`** - Case law
- **`search_citation`** and **`search_opinionscited`** - Citations
- **`recap_fjcintegrateddatabase`** - FJC IDB data
- People, financial disclosures, oral arguments

### What is NOT Available in Bulk

**`search_docketentry` and `search_recapdocument` tables are NOT included in the public bulk data exports.**

This is confirmed by examining the `make_bulk_data.sh` script on GitHub. The 32 exported tables do not include docket entries or RECAP documents.

### Implications

- You **cannot** get RECAP document availability data from bulk downloads
- You **can** get docket `source` bitmask from bulk data to identify which dockets have RECAP-sourced data
- For actual document-level data, you must use the REST API
- CourtListener offers **custom bulk data services** at means-based pricing for researchers who need docket entry or RECAP document data in bulk

### Bulk Data Access

```
S3 Bucket: com-courtlistener-storage
Prefix: bulk-data/
Browse: https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/list.html?prefix=bulk-data/
Format: CSV (bzip2 compressed), generated with PostgreSQL COPY TO
Schedule: Quarterly (last day of March, June, September, December)
```

---

## 9. Docket Source Bitmask

The `source` field on dockets is a bitmask built from 7 base values:

| Bit | Value | Constant | Meaning |
|-----|-------|----------|---------|
| 0 | 1 | `RECAP` | RECAP browser extension or RECAP-related uploads |
| 1 | 2 | `SCRAPER` | CourtListener's Juriscraper scrapers |
| 2 | 4 | `COLUMBIA` | Columbia Law Library archive |
| 3 | 8 | `IDB` | FJC Integrated Database |
| 4 | 16 | `HARVARD` | Harvard Caselaw Access Project |
| 5 | 32 | `DIRECT_INPUT` | Direct court input |
| 6 | 64 | `ANON_2020` | 2020 anonymous database |

### Checking for RECAP Data

```python
has_recap = (source & 1) == 1  # Bit 0 (RECAP) is set
# Or equivalently:
has_recap = source % 2 == 1    # source is odd
```

### Common Source Values

| Value | Binary | Sources |
|-------|--------|---------|
| 0 | 0000000 | Default (no known source) |
| 1 | 0000001 | RECAP only |
| 2 | 0000010 | Scraper only |
| 3 | 0000011 | RECAP + Scraper |
| 8 | 0001000 | IDB only |
| 9 | 0001001 | RECAP + IDB |
| 10 | 0001010 | Scraper + IDB |
| 11 | 0001011 | RECAP + Scraper + IDB |

### Filtering via API

```
# Dockets with RECAP source (exact match for source=1 only):
GET /api/rest/v4/dockets/?source=1

# Dockets with any source that includes RECAP:
GET /api/rest/v4/dockets/?source__in=1,3,5,7,9,11,13,15,...
# (all odd numbers up to 127)
```

The internal code uses `Docket.RECAP_SOURCES` which is a cached list of all source values where the RECAP bit is set.

---

## 10. Concrete API Recipes

### Recipe 1: Count Available RECAP Documents for a Docket

```python
import requests

HEADERS = {"Authorization": "Token YOUR_TOKEN"}
BASE = "https://www.courtlistener.com/api/rest/v4"

def count_recap_docs(docket_id):
    """Count available and total RECAP docs for a docket."""
    # Available PDFs
    r1 = requests.get(f"{BASE}/recap-documents/", headers=HEADERS, params={
        "docket_entry__docket": docket_id,
        "is_available": "true",
        "page_size": 1,
        "fields": "id",
    })
    available = r1.json().get("count", 0)

    # Total document records
    r2 = requests.get(f"{BASE}/recap-documents/", headers=HEADERS, params={
        "docket_entry__docket": docket_id,
        "page_size": 1,
        "fields": "id",
    })
    total = r2.json().get("count", 0)

    return {"available": available, "total": total}
```

### Recipe 2: Get Page Counts for All Available Documents

```python
def get_page_counts(docket_id):
    """Get page counts for all available docs in a docket."""
    url = f"{BASE}/recap-documents/"
    params = {
        "docket_entry__docket": docket_id,
        "is_available": "true",
        "document_type": 1,  # Main docs only
        "fields": "id,page_count,file_size,document_number,description",
        "order_by": "document_number",
    }
    all_docs = []
    while url:
        r = requests.get(url, headers=HEADERS, params=params)
        data = r.json()
        all_docs.extend(data["results"])
        url = data["next"]
        params = None  # next URL includes all params
    return all_docs
```

### Recipe 3: Search for Data-Rich Dockets by NOS

```python
def find_rich_dockets(nos_code, court=None):
    """Find dockets with available RECAP docs for a given NOS."""
    params = {
        "type": "r",
        "suitNature": nos_code,
        "available_only": "on",
        "order_by": "dateFiled desc",
    }
    if court:
        params["court"] = court

    r = requests.get(f"{BASE}/search/", headers=HEADERS, params=params)
    data = r.json()
    return {
        "docket_count": data.get("count", 0),
        "document_count": data.get("document_count", 0),
        "results": data.get("results", []),
    }
```

### Recipe 4: Identify Dockets with Many RECAP Documents

```python
def find_most_documented_dockets(nos_code, court=None):
    """Use type=r with available_only to find data-rich dockets."""
    # Step 1: Get candidate dockets
    candidates = find_rich_dockets(nos_code, court)

    # Step 2: For each, count the actual available docs
    enriched = []
    for docket in candidates["results"][:20]:  # Top 20
        did = docket["docket_id"]
        counts = count_recap_docs(did)
        enriched.append({
            "docket_id": did,
            "case_name": docket.get("caseName", ""),
            "date_filed": docket.get("dateFiled", ""),
            "court_id": docket.get("court_id", ""),
            "available_docs": counts["available"],
            "total_docs": counts["total"],
            "richness": counts["available"] / counts["total"] if counts["total"] > 0 else 0,
        })

    return sorted(enriched, key=lambda x: x["available_docs"], reverse=True)
```

### Recipe 5: Bulk Data Pre-Filter + API Enrichment

```python
import pandas as pd

def bulk_prefilter_then_api(nos_codes, courts, bulk_csv_path):
    """
    Step 1: Filter bulk data CSV for candidate dockets.
    Step 2: Use API to check RECAP richness.
    """
    # Load bulk docket data
    df = pd.read_csv(bulk_csv_path)

    # Filter to target NOS codes and courts
    candidates = df[
        (df["nature_of_suit"].str.contains('|'.join(nos_codes), na=False)) &
        (df["court_id"].isin(courts)) &
        (df["source"] % 2 == 1)  # Has RECAP bit set
    ]

    print(f"Found {len(candidates)} candidate dockets with RECAP source")

    # Sample and check actual document availability
    results = []
    for _, row in candidates.sample(min(100, len(candidates))).iterrows():
        counts = count_recap_docs(row["id"])
        if counts["available"] > 0:
            results.append({
                "docket_id": row["id"],
                "case_name": row["case_name"],
                "court_id": row["court_id"],
                "nos": row["nature_of_suit"],
                "source": row["source"],
                **counts,
            })

    return pd.DataFrame(results)
```

---

## Sources

- CourtListener REST API: https://www.courtlistener.com/help/api/rest/
- CourtListener PACER APIs: https://www.courtlistener.com/help/api/rest/pacer/
- CourtListener Search API: https://www.courtlistener.com/help/api/rest/search/
- Advanced Search Operators: https://www.courtlistener.com/help/search-operators/
- RECAP Archive Coverage: https://www.courtlistener.com/help/coverage/recap/
- Bulk Data: https://www.courtlistener.com/help/api/bulk-data/
- V4 Migration Guide: https://www.courtlistener.com/help/api/rest/v4/migration-guide/
- GitHub - models.py: https://github.com/freelawproject/courtlistener/blob/main/cl/search/models.py
- GitHub - filters.py: https://github.com/freelawproject/courtlistener/blob/main/cl/search/filters.py
- GitHub - api_views.py: https://github.com/freelawproject/courtlistener/blob/main/cl/search/api_views.py
- GitHub - documents.py: https://github.com/freelawproject/courtlistener/blob/main/cl/search/documents.py
- GitHub - docket_sources.py: https://github.com/freelawproject/courtlistener/blob/main/cl/search/docket_sources.py
- GitHub - make_bulk_data.sh: https://github.com/freelawproject/courtlistener/blob/main/scripts/make_bulk_data.sh
- GitHub Discussion #6274: https://github.com/freelawproject/courtlistener/discussions/6274
