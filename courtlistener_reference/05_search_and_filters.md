# Search & Filtering - Complete Reference

CourtListener offers two distinct query systems: the **Database API** (structured filters) and the **Search API** (full-text search). This document covers both.

---

## 1. DATABASE API FILTERS (Django-style Field Lookups)

Used on endpoints like `/api/rest/v4/dockets/`, `/api/rest/v4/docket-entries/`, etc.

### Filter Syntax

Filters use Django-style field lookups appended with double underscores:

```
?field=value                    # Exact match
?field__gte=value              # Greater than or equal
?field__gt=value               # Greater than
?field__lte=value              # Less than or equal
?field__lt=value               # Less than
?field__range=val1,val2        # Range (inclusive)
?field__in=val1,val2,val3      # In list
?field__year=2024              # Year extraction
?field__month=6                # Month extraction
?field__day=15                 # Day extraction
```

### Exclusion Filters
Prepend `!` to any filter:
```
?!nature_of_suit=550           # Exclude NOS 550
?court__jurisdiction!=F        # Exclude Federal Appellate
```

### Date Format
Always use **ISO-8601**: `YYYY-MM-DD`
```
?date_filed__gte=2024-01-01
?date_filed__range=2024-01-01,2024-12-31
```

---

### Docket Filters (`/api/rest/v4/dockets/`)

| Filter | Type | Example |
|--------|------|---------|
| `id` | integer | `?id=67591026` |
| `court` | string | `?court=nysd` |
| `court__in` | list | `?court__in=nysd,nyed,njd` |
| `court__jurisdiction` | string | `?court__jurisdiction=FD` |
| `nature_of_suit` | string | `?nature_of_suit=190` |
| `cause` | string | `?cause=28:1332` |
| `jurisdiction_type` | string | `?jurisdiction_type=Diversity` |
| `docket_number` | string | `?docket_number=1:24-cv-01234` |
| `docket_number_core` | string | `?docket_number_core=2401234` |
| `pacer_case_id` | string | `?pacer_case_id=123456` |
| `assigned_to` | integer | `?assigned_to=1234` (person ID) |
| `referred_to` | integer | `?referred_to=5678` |
| `date_filed` | date | `?date_filed__gte=2024-01-01` |
| `date_terminated` | date | `?date_terminated__gte=1900-01-01` |
| `date_last_filing` | date | `?date_last_filing__gte=2024-01-01` |
| `date_created` | datetime | `?date_created__gte=2024-01-01` |
| `date_modified` | datetime | `?date_modified__gte=2024-01-01` |
| `source` | integer | `?source=1` |
| `source__in` | list | `?source__in=1,3,9` |
| `federal_dn_case_type` | string | `?federal_dn_case_type=cv` |

### Docket Entry Filters (`/api/rest/v4/docket-entries/`)

| Filter | Type | Example |
|--------|------|---------|
| `docket` | integer | `?docket=67591026` |
| `entry_number` | integer | `?entry_number=15` |
| `date_filed` | date | `?date_filed__gte=2024-01-01` |
| `date_created` | datetime | `?date_created__gte=2024-01-01` |

### RECAP Document Filters (`/api/rest/v4/recap-documents/`)

| Filter | Type | Example |
|--------|------|---------|
| `docket_entry__docket` | integer | `?docket_entry__docket=67591026` |
| `document_type` | integer | `?document_type=1` (main docs only) |
| `is_available` | boolean | `?is_available=true` |
| `is_free_on_pacer` | boolean | `?is_free_on_pacer=true` |
| `date_created` | datetime | `?date_created__gte=2024-01-01` |

### Party Filters (`/api/rest/v4/parties/`)

| Filter | Type | Example |
|--------|------|---------|
| `docket` | integer | `?docket=67591026` |
| `party_type` | string | Filter by party role |
| `name` | string | `?name=Apple` |

### Attorney Filters (`/api/rest/v4/attorneys/`)

| Filter | Type | Example |
|--------|------|---------|
| `docket` | integer | `?docket=67591026` |

---

### Discovering ALL Available Filters

Send an OPTIONS request to any endpoint:
```bash
curl -X OPTIONS \
  --header 'Authorization: Token YOUR_TOKEN' \
  "https://www.courtlistener.com/api/rest/v4/dockets/" | jq '.filters'
```

The response lists every filterable field, its type, lookup types, and valid choices.

---

## 2. SEARCH API (`/api/rest/v4/search/`)

The Search API is powered by **ElasticSearch** and behaves differently from the database API.

### Search Types

| Parameter | Returns | Notes |
|-----------|---------|-------|
| `type=o` | Case law / opinions | Opinion search |
| `type=r` | Dockets with up to 3 nested documents | Default for PACER |
| `type=rd` | Flat list of PACER documents | Document-level results |
| `type=d` | Docket-only results | Fastest, no nested docs |

### Full-Text Query (`q=`)

The `q` parameter accepts Lucene-style query syntax:

```
?q=securities fraud                          # Simple keyword search
?q="securities fraud"                        # Exact phrase
?q=securities AND fraud                      # Boolean AND
?q=securities OR fraud                       # Boolean OR
?q=securities NOT fraud                      # Boolean NOT
?q=(securities OR commodities) AND fraud     # Grouped
?q=secur*                                    # Wildcard
?q="securities fraud"~5                      # Proximity (within 5 words)
```

### Fielded Search in Query String

You can target specific fields within the `q` parameter:

```
?q=caseName:(Apple Inc)                      # Search in case name
?q=caseName:(wade OR roe)                    # OR in case name
?q=court_id:nysd                             # Specific court
?q=party:Apple                               # Party name
?q=attorney:"Kirkland Ellis"                 # Attorney/firm
?q=description:motion dismiss                # Docket entry description
?q=suitNature:190                            # Nature of suit
?q=cause:"28:1332"                           # Cause of action
?q=assignedTo:"Roberts"                      # Assigned judge
?q=referredTo:"Smith"                        # Referred judge
?q=docketNumber:"1:24-cv-01234"             # Docket number
```

### Search API GET Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `q` | Full-text query | `?q=securities fraud` |
| `type` | Search type | `?type=d` |
| `court` | Court filter (space-separated) | `?court=nysd nyed` |
| `filed_after` | Filed after date | `?filed_after=2024-01-01` |
| `filed_before` | Filed before date | `?filed_before=2024-12-31` |
| `party_name` | Party name filter | `?party_name=Apple` |
| `attorney` | Attorney filter | `?attorney=Kirkland` |
| `nature_of_suit` | NOS filter | `?nature_of_suit=190` |
| `cause` | Cause of action | `?cause=28:1332` |
| `assigned_to` | Judge name | `?assigned_to=Roberts` |
| `referred_to` | Referred judge | `?referred_to=Smith` |
| `order_by` | Sort order | `?order_by=dateFiled desc` |
| `highlight` | Enable highlighting | `?highlight=on` |
| `cursor` | Pagination cursor | `?cursor=cD0yMDI0...` |

### Search API Field Names (camelCase)

The Search API uses **camelCase** field names, unlike the snake_case Database API:

| Search API Field | Database API Field |
|------------------|--------------------|
| `caseName` | `case_name` |
| `docketNumber` | `docket_number` |
| `suitNature` | `nature_of_suit` |
| `dateFiled` | `date_filed` |
| `dateArgued` | `date_argued` |
| `dateTerminated` | `date_terminated` |
| `assignedTo` | `assigned_to_str` |
| `referredTo` | `referred_to_str` |
| `court_id` | `court_id` |
| `party` | (party name) |
| `attorney` | (attorney name) |

### Performance Notes

- `type=d` and `type=r` use **cardinality aggregation** for result counts, with an error of +/-6% if results exceed 2,000
- `type=d` is significantly faster than `type=r` (no document nesting)
- When highlighting is disabled, first 500 characters of snippet fields are returned
- The Search API does NOT auto-expand court queries to child courts (unlike the website UI)

---

## 3. ORDERING / SORTING

### Database API Ordering
```
?order_by=date_filed                    # Ascending
?order_by=-date_filed                   # Descending (prefix with -)
?order_by=date_filed,id                 # Multi-field with tie-breaking
```

Common orderings:
```
?order_by=id
?order_by=date_modified
?order_by=date_created
?order_by=date_filed,id
?order_by=-date_filed,-id              # Newest first
```

### Deep Pagination Ordering (cursor-based)

These fields support deep pagination:
| Endpoint | Supported Fields |
|----------|-----------------|
| Most endpoints | `id`, `date_modified`, `date_created` |
| `/recap-fetch/` | Also `date_completed` |
| `/alerts/`, `/docket-alerts/` | Only `date_created` |

### Search API Ordering
```
?order_by=dateFiled desc               # Newest filed first
?order_by=dateFiled asc                # Oldest filed first
?order_by=score desc                   # Best match first (default)
```

---

## 4. RESPONSE OPTIMIZATION

### Select Fields (`fields` parameter, v4.2+)
```
?fields=id,case_name,docket_number,date_filed,court_id
```

### Exclude Fields (`omit` parameter)
```
?omit=recap_documents__plain_text
```

### Nested Field Syntax (double underscore)
```
?fields=recap_documents__document_number,recap_documents__description
?omit=recap_documents__plain_text
```

### Practical Examples
```
# Lightweight docket listing:
GET /api/rest/v4/dockets/?court=nysd&fields=id,case_name,docket_number,date_filed,date_terminated,nature_of_suit

# Docket entries without massive text:
GET /api/rest/v4/docket-entries/?docket=67591026&omit=recap_documents__plain_text

# Just availability info:
GET /api/rest/v4/recap-documents/?fields=id,document_type,is_available,page_count,file_size
```

---

## 5. COMMON QUERY RECIPES

### Securities fraud cases in SDNY, 2024
```
GET /api/rest/v4/dockets/?court=nysd&nature_of_suit=850&date_filed__gte=2024-01-01&date_filed__lte=2024-12-31
```

### All open antitrust cases
```
GET /api/rest/v4/search/?type=d&suitNature=410&q=NOT dateTerminated:[* TO *]
```

### Patent cases with available documents
```
GET /api/rest/v4/search/?type=r&suitNature=830&q=is_available:true
```

### Cases with a specific corporate party
```
GET /api/rest/v4/search/?type=d&party_name=Apple Inc
```

### RICO cases filed after 2020
```
GET /api/rest/v4/dockets/?nature_of_suit=470&date_filed__gte=2020-01-01
```

### All docket entries for a specific case
```
GET /api/rest/v4/docket-entries/?docket=67591026&order_by=entry_number&omit=recap_documents__plain_text
```

### Get total count of matching dockets
```
GET /api/rest/v4/dockets/?court=nysd&nature_of_suit=190&count=on
```

---

## 6. RATE LIMITS & BEST PRACTICES

| Aspect | Detail |
|--------|--------|
| Rate limit | 5,000 queries/hour per authenticated user |
| Page size | 20 results per page (default) |
| Cache | Results cached for 10 minutes |
| Auth required | Yes, all v4 endpoints (since v4.3) |
| Maintenance | Thursdays 21:00-23:59 PT |

### Best Practices
1. Always use `fields` or `omit` to reduce payload size
2. Use `type=d` instead of `type=r` when you don't need documents
3. Use database API filters for precise queries, search API for fuzzy matching
4. Always include tie-breaking field in ordering: `?order_by=date_filed,id`
5. Use `count=on` separately rather than counting results yourself
6. Respect rate limits -- implement exponential backoff on 429 responses

---

## Sources
- CourtListener REST API: https://www.courtlistener.com/help/api/rest/
- CourtListener Search API: https://www.courtlistener.com/help/api/rest/search/
- Search Operators: https://www.courtlistener.com/help/search-operators/
- PACER Data APIs: https://www.courtlistener.com/help/api/rest/pacer/
- V4 Migration Guide: https://www.courtlistener.com/help/api/rest/v4/migration-guide/
