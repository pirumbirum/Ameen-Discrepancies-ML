# Docket, Entry & Document Fields - Complete Reference

## 1. DOCKET OBJECT (`/api/rest/v4/dockets/`)

The Docket is the top-level object. It represents a single case in a single court.

### API Endpoints
```
GET  /api/rest/v4/dockets/                   # List (paginated)
GET  /api/rest/v4/dockets/{id}/              # Detail
GET  /api/rest/v4/dockets/{id}/parties/      # Nested parties
GET  /api/rest/v4/dockets/{id}/attorneys/    # Nested attorneys
```

---

### Identity & Metadata Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `resource_uri` | URL | Canonical API URL | `"https://...dockets/67591026/"` |
| `id` | integer | Primary key | `67591026` |
| `absolute_url` | string | Path on CL website | `"/docket/67591026/doe-v-smith/"` |
| `date_created` | datetime | When CL created the record | `"2024-01-15T10:30:00Z"` |
| `date_modified` | datetime | Last modification in CL | `"2024-06-01T14:22:00Z"` |
| `slug` | string | URL-friendly case name (max 75 chars) | `"doe-v-smith"` |
| `source` | integer | Bitmask for data origin (see below) | `9` |
| `blocked` | boolean | Blocked from search engine indexing | `false` |
| `date_blocked` | date (nullable) | When blocking was applied | `null` |

---

### Case Identification Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `case_name` | string | Standard case name | `"Doe v. Smith"` |
| `case_name_short` | string | Abridged name | `"Doe"` |
| `case_name_full` | string | Full unabridged name | `"John Doe v. Jane Smith et al."` |
| `docket_number` | string (nullable) | Full docket number | `"1:24-cv-01234-ABC"` |
| `docket_number_core` | string | Numeric-only format (max 20 chars) | `"2401234"` |
| `docket_number_raw` | string | Raw value from source | `"1:24-cv-01234"` |
| `docket_number_source` | integer | How cleaned: 0=Original, 1=Auto, 2=Manual | `0` |
| `pacer_case_id` | string (nullable) | PACER's internal case ID | `"123456"` |

---

### Federal Docket Number Parsed Fields (Added August 2024)

The federal docket number format is: `{office}:{yy}-{case_type}-{sequence}-{judge_initials}`

Example: `1:24-cv-01234-ABC` breaks down as:

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `federal_dn_office_code` | string (max 3) | Statistical district office code | `"1"` |
| `federal_dn_case_type` | string (max 6) | Case type code | `"cv"` |
| `federal_dn_judge_initials_assigned` | string (max 5) | Assigned judge initials | `"ABC"` |
| `federal_dn_judge_initials_referred` | string (max 5) | Referred judge initials | `"DEF"` |
| `federal_defendant_number` | integer (nullable) | Defendant number (criminal) | `1` |
| `parent_docket` | integer (nullable) | FK to parent docket (criminal multi-defendant) | `67590000` |

### Case Type Codes (from `federal_dn_case_type`)
| Code | Meaning |
|------|---------|
| `cv` | Civil |
| `cr` | Criminal |
| `mj` | Magistrate Judge |
| `mc` | Miscellaneous |
| `bk` | Bankruptcy |
| `ap` | Adversary Proceeding |
| `po` | Probation |
| `gj` | Grand Jury |

---

### Case Detail Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `cause` | string (max 2000) | Cause of action / statute | `"28:1332 Diversity-Contract Dispute"` |
| `nature_of_suit` | string (max 1000) | NOS code from PACER | `"190 Contract: Other"` |
| `jury_demand` | string (max 500) | Jury demand type | `"Plaintiff"` |
| `jurisdiction_type` | string (max 100) | Jurisdictional basis | `"Diversity"` |
| `mdl_status` | string (max 100) | MDL status | `"MDL Transfer"` |

### Jurisdiction Type Values (free-text, common values)
| Value | Meaning |
|-------|---------|
| `"Federal Question"` | Based on federal law (28 USC 1331) |
| `"Diversity"` | Parties from different states (28 USC 1332) |
| `"U.S. Government Plaintiff"` | Government is plaintiff |
| `"U.S. Government Defendant"` | Government is defendant |
| `""` | Not specified |

---

### All Date Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `date_filed` | date (nullable) | When case was filed | `"2024-01-15"` |
| `date_terminated` | date (nullable) | When case was closed | `"2024-09-30"` or `null` |
| `date_last_filing` | date (nullable) | Most recent filing activity | `"2024-06-15"` |
| `date_argued` | date (nullable) | When case was argued | `"2024-05-20"` |
| `date_reargued` | date (nullable) | Reargument date | `null` |
| `date_reargument_denied` | date (nullable) | Reargument denied date | `null` |
| `date_cert_granted` | date (nullable) | Certiorari granted date | `null` |
| `date_cert_denied` | date (nullable) | Certiorari denied date | `null` |
| `date_last_index` | datetime (nullable) | Last Elasticsearch indexing | `"2024-06-15T08:00:00Z"` |

---

### Determining Case Status

**There is NO explicit case status field.** Infer from dates:

| Condition | Interpretation |
|-----------|---------------|
| `date_terminated` is **null** | Case is **OPEN/ACTIVE** |
| `date_terminated` has a value | Case is **CLOSED/TERMINATED** |
| `date_filed` exists, `date_terminated` null | Filed and currently active |
| `date_last_filing` is recent | Active with recent filings |

**Filtering by status:**
```
# Terminated cases (any termination date):
GET /api/rest/v4/dockets/?date_terminated__gte=1900-01-01

# Cases terminated in 2024:
GET /api/rest/v4/dockets/?date_terminated__range=2024-01-01,2024-12-31

# Note: There's no reliable ?date_terminated__isnull=true filter for open cases
```

---

### Judge & Panel Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `assigned_to` | URL (nullable) | FK to assigned judge | `"https://...people/1234/"` |
| `assigned_to_str` | string | Judge name as text | `"John G. Roberts, Jr."` |
| `referred_to` | URL (nullable) | FK to referred judge | `null` |
| `referred_to_str` | string | Referred judge name | `""` |
| `panel` | array of URLs | Empaneled judges (appellate) | `["https://...people/1/"]` |
| `panel_str` | string | Panel judge initials | `"JGR, SK, EK"` |

---

### Appellate-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `appeal_from` | URL (nullable) | FK to originating court |
| `appeal_from_str` | string | Originating court text |
| `appellate_fee_status` | string | Fee status |
| `appellate_case_type_information` | string | Case type classification |

---

### Relationship Fields

| Field | Type | Description |
|-------|------|-------------|
| `court` | URL | Hyperlink to Court object |
| `court_id` | string (read-only) | Court identifier, e.g., `"nysd"` |
| `original_court_info` | nested object (nullable) | OriginatingCourtInformation |
| `idb_data` | nested object (nullable) | FJC Integrated Database data |
| `bankruptcy_information` | URL (nullable, read-only) | Link to BankruptcyInformation |
| `clusters` | array of URLs | Related OpinionCluster objects |
| `audio_files` | array of URLs | Related oral argument Audio objects |
| `tags` | array of URLs | Associated tags |

---

### Source Field - Bitmask Values

The `source` field is a **bitmask** built from 7 base sources:

| Value | Constant | Meaning |
|-------|----------|---------|
| 1 | `RECAP` | RECAP browser extension uploads |
| 2 | `SCRAPER` | CourtListener's Juriscraper scrapers |
| 4 | `COLUMBIA` | Columbia Law Library archive |
| 8 | `IDB` | FJC Integrated Database |
| 16 | `HARVARD` | Harvard Caselaw Access Project |
| 32 | `DIRECT_INPUT` | Direct court input |
| 64 | `ANON_2020` | 2020 anonymous database |

Common combinations:
| Value | Sources |
|-------|---------|
| 0 | Default |
| 3 | RECAP + Scraper |
| 9 | RECAP + IDB |
| 11 | RECAP + Scraper + IDB |
| 127 | All sources |

---

### Internet Archive Fields

| Field | Type | Description |
|-------|------|-------------|
| `filepath_ia` | string | Path to docket page in Internet Archive |
| `filepath_ia_json` | string | Path to docket JSON in IA |
| `ia_upload_failure_count` | integer (nullable) | Failed IA upload count |
| `ia_needs_upload` | boolean (nullable) | Needs uploading to IA |
| `ia_date_first_change` | datetime (nullable) | First change after last IA upload |

---

## 2. DOCKET ENTRIES (`/api/rest/v4/docket-entries/`)

Each entry = one row on a PACER docket sheet.

### Endpoints
```
GET  /api/rest/v4/docket-entries/?docket={docket_id}
GET  /api/rest/v4/docket-entries/{id}/
```

### All Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `resource_uri` | URL | Canonical API URL | `"https://...docket-entries/12345/"` |
| `id` | integer | Primary key | `12345` |
| `docket` | URL | Hyperlink to parent docket | `"https://...dockets/67591026/"` |
| `date_created` | datetime | Record creation in CL | `"2024-02-01T10:00:00Z"` |
| `date_modified` | datetime | Last modification | `"2024-02-01T10:00:00Z"` |
| `date_filed` | date (nullable) | Filing date | `"2024-02-01"` |
| `time_filed` | time (nullable) | Filing time | `"14:30:00"` |
| `entry_number` | integer (nullable) | Sequential number on docket | `15` |
| `recap_sequence_number` | string (max 50) | Ordering for unnumbered entries | `"1"` |
| `pacer_sequence_number` | integer (nullable) | `de_seqno` from PACER | `42` |
| `description` | string | Full text description from PACER | `"MOTION to Dismiss..."` |
| `recap_documents` | array of objects | **Nested** RECAPDocument objects | `[{...}]` |
| `tags` | array of URLs | Associated tags | `[]` |

### Ordering
```
?order_by=entry_number
?order_by=recap_sequence_number,entry_number    # Default PACER order
?order_by=date_filed,id
```

**Default page size: 20 entries per page**

---

## 3. RECAP DOCUMENTS (`/api/rest/v4/recap-documents/`)

Each document is a PDF or text file attached to a docket entry.

### Endpoints
```
GET  /api/rest/v4/recap-documents/
GET  /api/rest/v4/recap-documents/{id}/
```

### All Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `resource_uri` | URL | Canonical API URL | `"https://...recap-documents/98765/"` |
| `id` | integer | Primary key | `98765` |
| `absolute_url` | string | Path on CL website | `"/docket/67591026/15/"` |
| `date_created` | datetime | Record creation | `"2024-02-01T10:00:00Z"` |
| `date_modified` | datetime | Last modification | `"2024-02-01T12:00:00Z"` |
| `document_type` | integer | 1=Main document, 2=Attachment | `1` |
| `document_number` | string (max 32) | Document number in entry | `"15"` |
| `attachment_number` | integer (nullable) | Attachment sequence (null for main) | `null` |
| `pacer_doc_id` | string (max 64) | PACER's document ID | `"04506123456"` |
| `is_available` | boolean (nullable) | PDF available in RECAP | `true` |
| `is_free_on_pacer` | boolean (nullable) | Free as opinion on PACER | `false` |
| `is_sealed` | boolean (nullable) | Sealed on PACER | `false` |
| `description` | string | Short description | `"Exhibit A - Declaration..."` |
| `date_upload` | datetime (nullable) | When uploaded to RECAP | `"2024-02-01T11:00:00Z"` |
| `filepath_local` | string (max 1000) | Local PDF storage path | `"recap/gov.uscourts..."` |
| `filepath_ia` | string (max 1000) | Internet Archive path | `""` |
| `sha1` | string (max 40) | SHA1 hash of file | `"abc123def456..."` |
| `page_count` | integer (nullable) | Pages in PDF | `15` |
| `file_size` | integer (nullable) | File size in bytes | `245678` |
| `plain_text` | string | Full extracted text (can be huge) | `"UNITED STATES..."` |
| `ocr_status` | integer (nullable) | OCR status (see below) | `1` |
| `thumbnail` | file (nullable) | Thumbnail of first page | |
| `thumbnail_status` | integer | 0=Needed, 1=Complete, 2=Failed | `1` |
| `tags` | array of URLs | Associated tags | `[]` |

### `document_type` Values
| Value | Meaning |
|-------|---------|
| **1** | PACER Document (main filing) |
| **2** | Attachment (exhibit, etc.) |

**Note:** `document_type` is structural (main vs. attachment), NOT legal (complaint vs. motion). To identify the legal nature, use `description` fields or full-text search on `plain_text`.

### `ocr_status` Values
| Value | Meaning |
|-------|---------|
| 1 | OCR_COMPLETE |
| 2 | OCR_UNNECESSARY (already had text) |
| 3 | OCR_FAILED |
| 4 | OCR_NEEDED (not yet processed) |

### Unique Constraint
Each document uniquely identified by: `(docket_entry, document_number, attachment_number)`

---

## 4. BANKRUPTCY INFORMATION

| Field | Type | Description |
|-------|------|-------------|
| `docket` | FK/URL | Parent docket |
| `date_converted` | date (nullable) | Conversion date |
| `date_last_to_file_claims` | date (nullable) | Claims filing deadline |
| `date_last_to_file_govt` | date (nullable) | Government claims deadline |
| `date_debtor_dismissed` | date (nullable) | Debtor dismissal date |
| `chapter` | string | Bankruptcy chapter (7, 11, 13, etc.) |
| `trustee_str` | string | Trustee name |

---

## 5. ORIGINATING COURT INFORMATION (Appellate Cases)

| Field | Type | Description |
|-------|------|-------------|
| `docket_number` | string | Lower court docket number |
| `assigned_to` | FK/URL | Lower court judge |
| `assigned_to_str` | string | Lower court judge name |
| `court_reporter` | string | Court reporter name |
| `date_disposed` | date (nullable) | Disposition date |
| `date_filed` | date (nullable) | Filing date in lower court |
| `date_judgment` | date (nullable) | Judgment date |
| `date_filed_noa` | date (nullable) | Notice of appeal filed |
| `date_received_coa` | date (nullable) | Date received by COA |

---

## 6. FJC INTEGRATED DATABASE (`idb_data`)

Contains metadata from the Federal Judicial Center's regularly updated database of federal court cases. Available as a nested object on dockets or via separate endpoint.

---

## Sources
- CourtListener REST API: https://www.courtlistener.com/help/api/rest/
- CourtListener PACER APIs: https://www.courtlistener.com/help/api/rest/pacer/
- CourtListener GitHub: https://github.com/freelawproject/courtlistener
- Models source: https://github.com/freelawproject/courtlistener/blob/main/cl/search/models.py
