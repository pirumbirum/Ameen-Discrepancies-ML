# Step 2: Map & Organize Associated Documents

## Objective
Parse the 50K cases from Step 1 and create per-case subfolders with structured manifests identifying all associated documents (post-trial opinions, orders, judgments, etc.).

## Prerequisite
Step 1 complete: 50K cases with metadata + entry list + RECAP document availability info.

---

## Process

### For Each Case, Parse Entries and Classify

Scan every docket entry's `description` field and classify it:

| Classification | Keywords in Description |
|---------------|----------------------|
| **Opinion** | `OPINION`, `MEMORANDUM OPINION`, `MEMORANDUM AND ORDER`, `FINDINGS OF FACT` |
| **Order** | `ORDER` (standalone or with context) |
| **Judgment** | `JUDGMENT`, `FINAL JUDGMENT`, `DEFAULT JUDGMENT` |
| **Verdict** | `JURY VERDICT`, `VERDICT`, `BENCH TRIAL` |
| **Summary Judgment** | `SUMMARY JUDGMENT` |
| **Motion to Dismiss Ruling** | `MOTION TO DISMISS` + `ORDER` or `OPINION` |
| **Settlement** | `SETTLEMENT`, `CONSENT DECREE`, `STIPULATION OF DISMISSAL` |
| **Complaint** | `COMPLAINT`, `AMENDED COMPLAINT` |
| **Answer** | `ANSWER` |
| **Motion** | `MOTION` (various types) |
| **Brief** | `BRIEF`, `MEMORANDUM OF LAW`, `MEMORANDUM IN SUPPORT` |
| **Discovery** | `DISCOVERY`, `DEPOSITION`, `INTERROGATOR` |
| **Other** | Everything else |

### Build Manifest Per Case

```json
{
    "docket_id": 67591026,
    "case_name": "SEC v. Mega Corp Inc.",
    "court_id": "nysd",
    "nature_of_suit": "Securities/Commodities/Exchange",
    "date_filed": "2018-03-15",
    "date_terminated": "2021-09-20",
    "total_entries": 247,
    "documents": {
        "opinions": [
            {
                "entry_number": 145,
                "date_filed": "2020-06-15",
                "description": "MEMORANDUM OPINION AND ORDER on Motion for Summary Judgment",
                "is_available": true,
                "is_free_on_pacer": true,
                "page_count": 42,
                "pacer_doc_id": "04506123456"
            }
        ],
        "orders": [...],
        "judgments": [...],
        "verdicts": [...],
        "summary_judgment_rulings": [...],
        "motion_to_dismiss_rulings": [...],
        "settlements": [...],
        "complaints": [...],
        "briefs": [...]
    },
    "counts": {
        "opinions": 3,
        "orders": 28,
        "judgments": 2,
        "verdicts": 1,
        "summary_judgment_rulings": 1,
        "motion_to_dismiss_rulings": 1,
        "settlements": 0,
        "complaints": 2,
        "briefs": 12
    },
    "availability": {
        "total_documents": 180,
        "available_in_recap": 95,
        "free_on_pacer": 12,
        "sealed": 3,
        "needs_purchase": 70
    }
}
```

---

## Folder Structure

```
cases/
  case_67591026/
    manifest.json            # Structured document classification above
  case_12345678/
    manifest.json
  ...
  (50,000 case subfolders)
```

---

## No Additional API Calls Needed

This step is pure local processing -- parsing the JSON data already collected in Step 1. Zero API calls.

**Estimated processing time:** Minutes (just JSON parsing and classification).
