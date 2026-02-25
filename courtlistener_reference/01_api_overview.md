# CourtListener API v4 - Complete Overview

## Authentication
- **Header:** `Authorization: Token 8b856274a0e8309238fbd8732daa1498f2136b3e`
- **Rate Limit:** 5,000 requests/hour per authenticated user
- **Required:** All v4 endpoints require authentication (as of v4.3)
- **Anonymous requests:** Return `401 Unauthorized`
- **Account policy:** One account per project/person/organization

## Maintenance Window
- Thursdays 21:00-23:59 PT

---

## All V4 API Endpoints

| Endpoint | URL | Purpose |
|----------|-----|---------|
| **Dockets** | `/api/rest/v4/dockets/` | Case metadata, court, NOS codes |
| **Docket Entries** | `/api/rest/v4/docket-entries/` | Individual filings on a docket |
| **RECAP Documents** | `/api/rest/v4/recap-documents/` | PDFs/documents attached to entries |
| **Parties** | `/api/rest/v4/parties/` | Parties involved in cases |
| **Attorneys** | `/api/rest/v4/attorneys/` | Attorney details per case |
| **Opinions (Clusters)** | `/api/rest/v4/clusters/` | Opinion clusters (case law) |
| **Opinions** | `/api/rest/v4/opinions/` | Individual opinion text |
| **Citations** | `/api/rest/v4/citations/` | Citation relationships |
| **Courts** | `/api/rest/v4/courts/` | Court metadata |
| **Search** | `/api/rest/v4/search/` | Full-text search across everything |
| **RECAP Fetch** | `/api/rest/v4/recap-fetch/` | Buy & download from PACER |
| **RECAP Upload** | `/api/rest/v4/recap/` | Upload PACER data to CL |
| **Prayers** | `/api/rest/v4/prayers/` | Request docs not yet available |
| **Docket Alerts** | `/api/rest/v4/docket-alerts/` | Subscribe to case updates |
| **Bankruptcy Info** | `/api/rest/v4/bankruptcy-information/` | Bankruptcy-specific data |

---

## Data Model Hierarchy

```
Court
  +-- Docket (case metadata, NOS, parties, attorneys)
  |     +-- Docket Entries (individual filings)
  |     |     +-- RECAP Documents (PDFs, text)
  |     +-- Parties
  |     |     +-- Attorneys
  |     +-- Clusters (opinion groups)
  |     |     +-- Opinions (full text)
  |     |           +-- Citations
  |     +-- Audio (oral arguments)
  |     +-- OriginatingCourtInformation (appellate cases)
  |     +-- BankruptcyInformation (bankruptcy cases)
  |     +-- FJC Integrated Database (idb_data)
```

**Key constraint:** Docket entries, parties, and attorneys are NOT nested within docket responses (some dockets have thousands). You must query them via separate endpoints filtered by docket ID.

---

## Search API Types (`/api/rest/v4/search/`)

| Type Parameter | Returns | Use Case |
|---------------|---------|----------|
| `type=o` | Case law / opinions | Finding judicial opinions |
| `type=r` | Dockets with up to 3 nested documents | Browsing cases with preview docs |
| `type=rd` | Flat list of PACER documents | Finding specific documents |
| `type=d` | Docket-only results (fastest) | Case listing, metadata only |

---

## Pagination (Cursor-Based, v4)

v4 uses **cursor-based pagination** (not offset-based). No page number jumping.

### Response Structure
```json
{
    "count": "URL to call with ?count=on for total count",
    "next": "URL for next page (null if last)",
    "previous": "URL for previous page (null if first)",
    "results": [...]
}
```

### Default Page Size: 20 results per page

### Iterating Through All Results
```python
import requests

url = "https://www.courtlistener.com/api/rest/v4/dockets/?court=nysd"
headers = {"Authorization": "Token YOUR_TOKEN"}

while url:
    response = requests.get(url, headers=headers).json()
    for docket in response["results"]:
        process(docket)
    url = response["next"]  # None when done
```

### Deep Pagination Rules
1. Navigate ONLY through `next` and `previous` links
2. Do NOT change GET parameters while maintaining a cursor (causes 404)
3. Supported ordering for deep pagination: `id`, `date_modified`, `date_created`
4. Always use a tie-breaking field: `?order_by=date_filed,id`
5. Null values sort last regardless of order direction
6. Results cached for 10 minutes
7. Use `?count=on` separately to get total count

---

## Response Optimization

### `fields` - Select Only These Fields
```
GET /api/rest/v4/dockets/67591026/?fields=case_name,docket_number,date_filed,court_id
```

### `omit` - Exclude These Fields
```
GET /api/rest/v4/docket-entries/?docket=67591026&omit=recap_documents__plain_text
```

### Nested Field Selection (double-underscore notation)
```
?fields=recap_documents__document_number,recap_documents__description
?omit=recap_documents__plain_text
```

**Critical for performance:** Always use `omit=recap_documents__plain_text` when listing docket entries to avoid massive payloads.

---

## RECAP Fetch API (Buying from PACER)

- **Free API** but uses your PACER credentials to purchase
- PACER charges go to your account ($0.10/page, $3.00 cap/document)
- PACER fees under $30/quarter are waived
- **Asynchronous:** POST request -> queued -> completed in seconds
- **Request types:** `request_type=1` (docket), `2` (PDF), `3` (attachment page)
- Your PACER password is used once to get cookies, then discarded immediately

---

## Pray & Pay System
- Request documents not yet in RECAP Archive
- Get notified via webhook or email when someone else buys it
- Free Law Project members get higher daily prayer limits

---

## Discovering All Filters (OPTIONS Request)
```bash
curl -X OPTIONS \
  --header 'Authorization: Token YOUR_TOKEN' \
  "https://www.courtlistener.com/api/rest/v4/dockets/"
```
The `filters` key lists all available filter fields, types, lookup types, and valid choices.
