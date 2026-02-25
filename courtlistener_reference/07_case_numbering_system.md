# Federal Case Numbering System

## PACER Docket Number Format

Federal case numbers follow this structure:

```
{office_code}:{year}-{case_type}-{sequence_number}-{judge_initials}
```

### Example: `1:24-cv-01234-ABC`

| Component | Value | Meaning |
|-----------|-------|---------|
| Office code | `1` | Statistical division/office within the district |
| Year | `24` | Last 2 digits of filing year (2024) |
| Case type | `cv` | Civil case |
| Sequence number | `01234` | Sequential case number within that year |
| Judge initials | `ABC` | Assigned judge's initials |

---

## Case Type Codes

| Code | Full Name | Description |
|------|-----------|-------------|
| `cv` | Civil | Civil lawsuits |
| `cr` | Criminal | Criminal prosecutions |
| `mj` | Magistrate Judge | Cases assigned to magistrate judges |
| `mc` | Miscellaneous | Miscellaneous proceedings |
| `bk` | Bankruptcy | Bankruptcy petitions |
| `ap` | Adversary Proceeding | Lawsuits within bankruptcy cases |
| `po` | Probation | Probation matters |
| `gj` | Grand Jury | Grand jury proceedings |
| `md` | MDL | Multi-District Litigation |

---

## Office Codes

The office code (first digit) identifies a statistical division within the district. These vary by district:

- Most districts use `1` through `9`
- Some districts (like SDNY) use specific office codes for borough/location
- The office code is sometimes omitted: `24-cv-01234` instead of `1:24-cv-01234`

---

## CourtListener Fields for Case Numbers

| Field | Content | Example |
|-------|---------|---------|
| `docket_number` | Full docket number (may include judge initials, consolidated numbers) | `"1:24-cv-01234-ABC"` |
| `docket_number_core` | Distilled numeric-only format (max 20 chars) | `"2401234"` |
| `docket_number_raw` | Raw value as found on source | `"1:24-cv-01234"` |
| `federal_dn_office_code` | Office code parsed out | `"1"` |
| `federal_dn_case_type` | Case type parsed out | `"cv"` |
| `federal_dn_judge_initials_assigned` | Assigned judge initials parsed out | `"ABC"` |
| `federal_dn_judge_initials_referred` | Referred judge initials parsed out | `""` |
| `federal_defendant_number` | Defendant number (criminal cases) | `null` or `1` |
| `parent_docket` | Parent docket ID (criminal multi-defendant) | `null` or docket ID |

---

## Criminal Case Number Variations

Criminal cases may have defendant-specific suffixes:

```
1:24-cr-00567-ABC-1     (Defendant 1)
1:24-cr-00567-ABC-2     (Defendant 2)
1:24-cr-00567-ABC-3     (Defendant 3)
```

In CourtListener:
- `federal_defendant_number` stores the defendant number
- `parent_docket` links to the main case docket

---

## Consolidated & MDL Case Numbers

Multidistrict litigation and consolidated cases may have special docket numbers:
```
1:24-md-03000-ABC       (MDL master case)
1:24-cv-01234-ABC       (Individual case transferred into MDL)
```

The `mdl_status` field on the docket tracks MDL information.

---

## Bankruptcy Case Numbers

Bankruptcy cases use a similar format:
```
1:24-bk-12345-ABC       (Bankruptcy petition)
1:24-ap-00001-ABC       (Adversary proceeding within bankruptcy)
```

---

## Appellate Case Numbers

Circuit courts use different numbering:
```
24-1234                 (5th Circuit style)
No. 24-1234             (With "No." prefix)
24-1234(L)              (Lead case in consolidated appeal)
24-1234(XAP)            (Cross-appeal)
```

---

## Searching by Docket Number

### Database API
```
GET /api/rest/v4/dockets/?docket_number=1:24-cv-01234
GET /api/rest/v4/dockets/?docket_number_core=2401234
GET /api/rest/v4/dockets/?federal_dn_case_type=cv
```

### Search API
```
GET /api/rest/v4/search/?type=d&q=docketNumber:"1:24-cv-01234"
GET /api/rest/v4/search/?type=d&docket_number=1:24-cv-01234
```

---

## PACER Case ID vs. Docket Number

| Field | What It Is | Example |
|-------|------------|---------|
| `docket_number` | The human-readable case number | `"1:24-cv-01234-ABC"` |
| `pacer_case_id` | PACER's internal database ID (opaque) | `"123456"` |
| `id` | CourtListener's internal ID | `67591026` |

The `pacer_case_id` is PACER's internal identifier -- different from the docket number. You need it for some PACER operations (like the Fetch API), but it's not the same as the human-readable case number.

---

## Sources
- PACER: https://pacer.uscourts.gov/
- CourtListener PACER APIs: https://www.courtlistener.com/help/api/rest/pacer/
- CourtListener API Changes: https://www.courtlistener.com/help/api/rest/changes/
