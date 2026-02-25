# Step 1: Gather 50,000 Federal Corporate Litigation Cases

## Objective
Pull metadata + docket entry list (with document availability) for 50,000 federal corporate litigation cases from CourtListener API v4.

## Parameters
- **Date range:** 2015-2025 (10 years)
- **Courts:** All 94 federal district courts (`court__jurisdiction=FD`)
- **Data depth:** Metadata + entry list with RECAP document info (no `plain_text`)

---

## Two-Pass Architecture

### Pass 1: Metadata Sweep (Fast)

**Endpoint:** `/api/rest/v4/dockets/`

**Fields requested:**
```
?fields=id,case_name,case_name_full,docket_number,docket_number_core,
        court_id,nature_of_suit,cause,jurisdiction_type,date_filed,
        date_terminated,date_last_filing,assigned_to_str,referred_to_str,
        pacer_case_id,source,slug,federal_dn_case_type
```

**Filters:**
```
?court__jurisdiction=FD
&date_filed__gte=2015-01-01
&date_filed__lte=2025-12-31
&nature_of_suit=<NOS_TEXT>
&order_by=date_filed,id
```

**API calls:** ~2,500 (50K / 20 per page)
**Time:** ~30 minutes

### Pass 2: Entry Pull (Slower)

**Endpoint:** `/api/rest/v4/docket-entries/?docket={docket_id}&omit=recap_documents__plain_text`

For each of the 50K dockets, pull all docket entries. Each entry includes nested `recap_documents` with availability info but no full text.

**API calls:** ~75,000-100,000 (avg 1-3 pages per case)
**Time:** ~15-20 hours at 5,000 requests/hour

---

## NOS Code Targets

### Tier 1 -- Inherently Corporate (Pull First)

| NOS Text to Match | Category | Target Count |
|--------------------|----------|-------------|
| Securities | Securities/Commodities/Exchange (850) | ~8,000 |
| Patent | Patent (830) | ~10,000 |
| Trademark | Trademark (840) | ~8,000 |
| Antitrust | Antitrust (410) | ~2,000 |
| Stockholders | Stockholders' Suits (160) | ~2,000 |
| RICO | RICO (470) | ~1,500 |
| Trade Secret | Defend Trade Secrets Act (880) | ~1,500 |
| **Tier 1 subtotal** | | **~33,000** |

### Tier 2 -- High Corporate Overlap (Fill to 50K)

| NOS Text to Match | Category | Target Count |
|--------------------|----------|-------------|
| Other Contract | Other Contract (190) -- filter by corporate party names | ~10,000 |
| Insurance | Insurance (110) | ~3,000 |
| Banks | Banks and Banking (430) | ~2,000 |
| Environmental | Environmental Matters (893) | ~2,000 |
| **Tier 2 subtotal** | | **~17,000** |

### **Grand Total: ~50,000**

---

## NOS Filtering Strategy

The `nature_of_suit` field stores TEXT descriptions, not numeric codes. Use text matching:

```
# Database API:
?nature_of_suit=Securities
?nature_of_suit=Patent
?nature_of_suit=Antitrust

# For broader matching if needed:
# Use Search API with suitNature field
```

For NOS 190 (Other Contract) -- too broad, additionally filter using Search API with party name patterns:
```
GET /api/rest/v4/search/?type=d&suitNature=190&party_name=Inc
GET /api/rest/v4/search/?type=d&suitNature=190&party_name=Corp
GET /api/rest/v4/search/?type=d&suitNature=190&party_name=LLC
```

---

## Rate Limit Management

| Constraint | Value |
|------------|-------|
| Rate limit | 5,000 requests/hour |
| Page size | 20 results/page |
| Cache duration | 10 minutes |

**Strategy:**
- Track requests per hour with a rolling counter
- Sleep when approaching 4,800 calls/hour (leave 200 buffer)
- Exponential backoff on 429 responses
- Log every request with timestamp for debugging

---

## Checkpoint & Resume

- Save progress after every NOS code completes
- Checkpoint file tracks: last NOS code, last cursor URL, total cases collected
- If crawler crashes, resume from last checkpoint
- Each NOS code's results saved to separate JSON before merging

---

## Data Storage

```
cases/
  metadata/
    securities.json          # All docket metadata for Securities NOS
    patent.json
    trademark.json
    antitrust.json
    stockholders.json
    rico.json
    trade_secrets.json
    other_contract.json
    insurance.json
    banking.json
    environmental.json
  entries/
    {docket_id}.json         # Docket entries + RECAP doc info per case
  index.json                 # Master index: docket_id -> metadata summary
  checkpoint.json            # Resume state
```

---

## What Each Entry JSON Contains

```json
{
    "docket_id": 67591026,
    "entries": [
        {
            "id": 12345,
            "entry_number": 15,
            "date_filed": "2024-02-01",
            "description": "MEMORANDUM OPINION AND ORDER granting Defendant's Motion...",
            "recap_documents": [
                {
                    "id": 98765,
                    "document_type": 1,
                    "is_available": true,
                    "is_free_on_pacer": true,
                    "is_sealed": false,
                    "page_count": 35,
                    "pacer_doc_id": "04506123456",
                    "description": "Memorandum Opinion"
                }
            ]
        }
    ]
}
```

---

## Total API Budget

| Phase | Calls | Time |
|-------|-------|------|
| Pass 1 (metadata) | ~2,500 | ~30 min |
| Pass 2 (entries) | ~75,000 | ~15 hrs |
| **Total** | **~77,500** | **~16 hours** |
