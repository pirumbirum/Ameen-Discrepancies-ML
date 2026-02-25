# CourtListener API Reference Guide

A comprehensive reference for the CourtListener REST API v4 and PACER data system. This guide covers everything you need to search, filter, and retrieve federal court case data programmatically.

---

## Files

| File | Contents |
|------|----------|
| [01_api_overview.md](01_api_overview.md) | API basics: authentication, all endpoints, pagination, response optimization, rate limits |
| [02_nos_codes_complete.md](02_nos_codes_complete.md) | Complete list of Nature of Suit codes with categories, plus corporate litigation mapping |
| [03_federal_court_ids.md](03_federal_court_ids.md) | All federal court identifiers: SCOTUS, circuits, district courts, bankruptcy courts, specialized courts |
| [04_docket_fields_reference.md](04_docket_fields_reference.md) | Complete field reference for dockets, docket entries, RECAP documents, bankruptcy info |
| [05_search_and_filters.md](05_search_and_filters.md) | All search/filter parameters for database API and search API, with query recipes |
| [06_parties_attorneys.md](06_parties_attorneys.md) | Party and attorney data model, party types, corporate identification patterns |
| [07_case_numbering_system.md](07_case_numbering_system.md) | Federal case number format, case type codes, docket number parsing |
| [08_recap_fetch_api.md](08_recap_fetch_api.md) | RECAP Fetch API for purchasing documents from PACER, costs, security model |
| [09_fjc_integrated_database.md](09_fjc_integrated_database.md) | FJC Integrated Database: origin codes, disposition, class action status, judgment outcomes |

---

## Quick Start

### Authentication
```bash
curl -H "Authorization: Token YOUR_TOKEN" \
  "https://www.courtlistener.com/api/rest/v4/dockets/?court=nysd"
```

### Search for Cases
```bash
# By Nature of Suit (securities fraud in SDNY)
curl -H "Authorization: Token YOUR_TOKEN" \
  "https://www.courtlistener.com/api/rest/v4/dockets/?court=nysd&nature_of_suit=850"

# Full-text search
curl -H "Authorization: Token YOUR_TOKEN" \
  "https://www.courtlistener.com/api/rest/v4/search/?type=d&q=securities%20fraud&court=nysd"

# By party name
curl -H "Authorization: Token YOUR_TOKEN" \
  "https://www.courtlistener.com/api/rest/v4/search/?type=d&party_name=Apple%20Inc"
```

### Get Docket Entries
```bash
curl -H "Authorization: Token YOUR_TOKEN" \
  "https://www.courtlistener.com/api/rest/v4/docket-entries/?docket=67591026&omit=recap_documents__plain_text"
```

---

## Key Links

- **API Documentation:** https://www.courtlistener.com/help/api/rest/
- **PACER Data APIs:** https://www.courtlistener.com/help/api/rest/pacer/
- **Search Operators:** https://www.courtlistener.com/help/search-operators/
- **Available Jurisdictions:** https://www.courtlistener.com/help/api/jurisdictions/
- **V4 Migration Guide:** https://www.courtlistener.com/help/api/rest/v4/migration-guide/
- **API Change Log:** https://www.courtlistener.com/help/api/rest/changes/
- **CourtListener GitHub:** https://github.com/freelawproject/courtlistener
- **Courts-DB GitHub:** https://github.com/freelawproject/courts-db
- **Free Law Project:** https://free.law/

---

## Rate Limits
- 5,000 requests/hour per authenticated user
- Maintenance: Thursdays 21:00-23:59 PT
- Results cached for 10 minutes
