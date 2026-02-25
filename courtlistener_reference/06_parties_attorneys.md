# Parties & Attorneys - Complete Reference

## 1. PARTIES (`/api/rest/v4/parties/`)

Parties are linked to dockets through a many-to-many relationship using the `PartyType` join table.

### Endpoints
```
GET  /api/rest/v4/parties/                  # List (paginated)
GET  /api/rest/v4/parties/{id}/             # Detail
GET  /api/rest/v4/dockets/{id}/parties/     # Parties for a specific docket
```

### Party Object Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `resource_uri` | URL | Canonical API URL | `"https://...parties/12345/"` |
| `id` | integer | Primary key | `12345` |
| `date_created` | datetime | Record creation | `"2024-01-15T10:30:00Z"` |
| `date_modified` | datetime | Last modification | `"2024-06-01T14:22:00Z"` |
| `name` | string | Party name | `"Apple Inc."` |
| `party_type` | object | Party's role in the case | See below |
| `attorneys` | array | Attorneys representing this party | Nested attorney objects |

### Party Type (Role in Case)

The `party_type` field (from the PartyType join table) contains the party's role. This is a **free-text** field as PACER stores it, not a strict enum. Common values include:

| Value | Meaning |
|-------|---------|
| `"Plaintiff"` | Filed the lawsuit |
| `"Defendant"` | Being sued |
| `"Petitioner"` | Filed a petition |
| `"Respondent"` | Responding to a petition |
| `"Appellant"` | Appealing a decision |
| `"Appellee"` | Responding to an appeal |
| `"Cross-Defendant"` | Cross-claim defendant |
| `"Cross-Complainant"` | Filed a cross-complaint |
| `"Counter-Claimant"` | Filed a counter-claim |
| `"Counter-Defendant"` | Counter-claim defendant |
| `"Third-Party Plaintiff"` | Filed third-party claim |
| `"Third-Party Defendant"` | Third-party defendant |
| `"Intervenor"` | Intervening party |
| `"Intervenor-Plaintiff"` | Intervening as plaintiff |
| `"Intervenor-Defendant"` | Intervening as defendant |
| `"Amicus"` | Friend of the court |
| `"Amicus Curiae"` | Friend of the court (formal) |
| `"Movant"` | Filing a motion |
| `"Mediator"` | Court-appointed mediator |
| `"Trustee"` | Bankruptcy trustee |
| `"Debtor"` | Bankruptcy debtor |
| `"Creditor"` | Bankruptcy creditor |
| `"Interested Party"` | Interested party |
| `"U.S. Trustee"` | U.S. Trustee (bankruptcy) |
| `"Garnishee"` | Garnishment target |
| `"In Re"` | Subject of an in re proceeding |
| `"Consolidated Plaintiff"` | In consolidated cases |
| `"Consolidated Defendant"` | In consolidated cases |
| `"MDL Plaintiff"` | In MDL proceedings |
| `"MDL Defendant"` | In MDL proceedings |

---

## 2. IDENTIFYING CORPORATE vs. INDIVIDUAL PARTIES

### No Explicit Party Entity Type Field

CourtListener does **NOT** have a `party_entity_type` or `is_corporation` field. The `name` field is the only identifier.

### Identifying Corporations by Name Patterns

Corporations can be identified by common suffixes and patterns in the `name` field:

**Corporate indicators:**
- `Inc.`, `Inc`, `Incorporated`
- `Corp.`, `Corp`, `Corporation`
- `LLC`, `L.L.C.`
- `LLP`, `L.L.P.`
- `LP`, `L.P.`
- `Ltd.`, `Ltd`, `Limited`
- `Co.`, `Company`
- `Group`, `Holdings`
- `Partners`, `Partnership`
- `Associates`, `& Associates`
- `Bank`, `Insurance`, `Financial`
- `Industries`, `International`
- `Technologies`, `Systems`
- `Foundation`, `Fund`
- `Trust`
- `N.A.` (National Association - banks)
- `P.C.` (Professional Corporation)
- `PLLC` (Professional Limited Liability Company)

**Government entity indicators:**
- `United States of America`
- `U.S.`, `USA`
- `State of`, `City of`, `County of`
- `Commissioner`, `Secretary`, `Director` (government officials)
- `Federal`, `Bureau`
- `Agency`, `Administration`, `Department`
- `EPA`, `SEC`, `FTC`, `DOJ`, `FDA`

**Individual indicators (absence of corporate suffixes):**
- First name + last name pattern
- No corporate suffix
- `et al.` (multiple individuals)
- `Estate of`, `In re` (can be either)

### Practical Detection Strategy

When filtering for corporate litigation, combine:
1. **NOS codes** that are inherently corporate (securities, antitrust, patent)
2. **Party name keyword search** for corporate suffixes
3. **Case name analysis** (most corporate cases have `Corp`, `Inc`, etc. in the name)

```python
# Example: Identify corporate parties by name
corporate_indicators = [
    'Inc.', 'Inc,', 'Corp.', 'Corp,', 'Corporation',
    'LLC', 'L.L.C.', 'LLP', 'L.L.P.', 'Ltd.', 'Limited',
    'Co.', 'Company', 'Holdings', 'Group', 'Partners',
    'Industries', 'International', 'Technologies',
    'Bank', 'Insurance', 'Financial', 'N.A.',
]

def is_likely_corporate(party_name):
    name_upper = party_name.upper()
    for indicator in corporate_indicators:
        if indicator.upper() in name_upper:
            return True
    return False
```

---

## 3. ATTORNEYS (`/api/rest/v4/attorneys/`)

### Endpoints
```
GET  /api/rest/v4/attorneys/                # List (paginated)
GET  /api/rest/v4/attorneys/{id}/           # Detail
GET  /api/rest/v4/dockets/{id}/attorneys/   # Attorneys for a specific docket
```

### Attorney Object Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `resource_uri` | URL | Canonical API URL | `"https://...attorneys/67890/"` |
| `id` | integer | Primary key | `67890` |
| `date_created` | datetime | Record creation | `"2024-01-15T10:30:00Z"` |
| `date_modified` | datetime | Last modification | `"2024-06-01T14:22:00Z"` |
| `name` | string | Attorney name | `"John D. Lawyer"` |
| `contact_raw` | string | Raw contact info from PACER | Multi-line string with firm, address, phone, email |
| `phone` | string | Phone number | `"(212) 555-1234"` |
| `fax` | string | Fax number | `"(212) 555-1235"` |
| `email` | string | Email address | `"jlawyer@kirkland.com"` |
| `roles` | array | Attorney roles | See below |

### Attorney Roles

| Value | Meaning |
|-------|---------|
| `"LEAD ATTORNEY"` | Lead attorney for the party |
| `"ATTORNEY TO BE NOTICED"` | Attorney to receive notices |
| `"PRO HAC VICE"` | Admitted for this case only |
| `"TERMINATED"` | No longer representing the party |
| `"GOVERNMENT ATTORNEY"` | Government lawyer |
| `"PRO SE"` | Self-represented |
| `"NOTICE ATTORNEY"` | Attorney to be noticed |
| `"CJA APPOINTMENT"` | Criminal Justice Act appointment |
| `"SELF-REPRESENTED"` | Pro se alternative label |

### Identifying Law Firms

CourtListener does NOT have a dedicated `law_firm` field. Firm information is embedded in `contact_raw`:

```
John D. Lawyer
Kirkland & Ellis LLP
601 Lexington Avenue
New York, NY 10022
Phone: (212) 446-4800
Email: john.lawyer@kirkland.com
```

To extract firm names, parse the `contact_raw` field (second line is typically the firm name).

### Searching for Attorneys/Firms

**Via Search API:**
```
GET /api/rest/v4/search/?type=d&attorney=Kirkland
GET /api/rest/v4/search/?type=d&q=attorney:"Kirkland Ellis"
```

**Via Database API:**
No direct firm filter exists on the attorneys endpoint. You must search via the Search API or parse `contact_raw`.

---

## 4. RELATIONSHIP MODEL

```
Docket
  |
  +-- PartyType (join table) ---> Party
  |     |
  |     +-- party_type (role: "Plaintiff", "Defendant", etc.)
  |     |
  |     +-- Attorney (through AttorneyOrganizationAssociation)
  |           |
  |           +-- name
  |           +-- contact_raw (contains firm info)
  |           +-- phone, fax, email
  |           +-- roles
  |
  +-- PartyType ---> Another Party
        |
        +-- Attorney
```

### Key Points:
- Parties are linked to dockets through `PartyType` (many-to-many)
- Attorneys are linked to parties within the context of a specific docket
- One attorney can represent different parties in different cases
- The same party entity may appear with slightly different names across cases
- Parties and attorneys are queried via separate endpoints (not nested in docket responses due to volume)

---

## 5. SEARCH API PARTY/ATTORNEY FIELDS

| Search Parameter | Description | Example |
|------------------|-------------|---------|
| `party_name` | Filter by party name | `?party_name=Apple` |
| `attorney` | Filter by attorney name | `?attorney=Kirkland` |
| `q=party:NAME` | Fielded party search | `?q=party:"Apple Inc"` |
| `q=attorney:NAME` | Fielded attorney search | `?q=attorney:"Jones Day"` |

---

## Sources
- CourtListener PACER APIs: https://www.courtlistener.com/help/api/rest/pacer/
- CourtListener REST API: https://www.courtlistener.com/help/api/rest/
- Search Operators: https://www.courtlistener.com/help/search-operators/
- CourtListener GitHub (models): https://github.com/freelawproject/courtlistener/blob/main/cl/search/models.py
- CourtListener GitHub (people_db models): https://github.com/freelawproject/courtlistener/blob/main/cl/people_db/models.py
