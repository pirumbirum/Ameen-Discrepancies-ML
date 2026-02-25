# FJC Integrated Database (IDB) - Complete Reference

The Federal Judicial Center's Integrated Database is a regularly updated source of enriched metadata about federal court cases. CourtListener includes this data as the `idb_data` nested object on dockets.

---

## Accessing IDB Data

### Via Docket Object
```
GET /api/rest/v4/dockets/{id}/?fields=idb_data
```

The `idb_data` field is a nested object on the Docket response.

### Via Bulk Data
Available as a separate table in CourtListener's bulk data downloads.

---

## Origin Codes (How the Case Entered the Court)

| Code | Description |
|------|-------------|
| 1 | Original Proceeding |
| 2 | Removed from State Court |
| 3 | Remanded for Further Action |
| 4 | Reinstated/Reopened |
| 5 | Transferred from Another District (28 USC 1404) |
| 6 | Multidistrict Litigation (28 USC 1407) |
| 7 | Appeal to District Judge of Magistrate Judge Decision |
| 8 | Second Reopen |
| 9 | Third Reopen |
| 10 | Fourth Reopen |
| 11 | Fifth Reopen |
| 12 | Sixth Reopen |
| 13 | MDL Originating in the District (since July 2016) |

---

## IDB Jurisdiction Codes

| Code | Description |
|------|-------------|
| 1 | Government Plaintiff |
| 2 | Government Defendant |
| 3 | Federal Question |
| 4 | Diversity of Citizenship |
| 5 | Local Question |

---

## Procedural Progress

### Before Issue Joined
| Value | Description |
|-------|-------------|
| 1 | No court action |
| 2 | Order entered |
| 3 | Hearing held |
| 4 | Order decided |

### After Issue Joined
| Value | Description |
|-------|-------------|
| 5 | No court action |
| 6 | Judgment on motion |
| 7 | Pretrial conference held |
| 8 | During court trial |
| 9 | During jury trial |
| 10 | After court trial |
| 11 | After jury trial |
| 12 | Other |
| 13 | Request for trial de novo after arbitration |

---

## Disposition Codes

### Transfers and Remands
| Value | Description |
|-------|-------------|
| 0 | Transfer to another district |
| 1 | Remand to state court |
| 2 | MDL transfer |
| 10 | Remand to U.S. agency |

### Dismissals
| Value | Description |
|-------|-------------|
| 3 | Want of prosecution |
| 4 | Lack of jurisdiction |
| 5 | Voluntary dismissal |
| 6 | Settled |
| 7 | Other dismissal |

### Judgments
| Value | Description |
|-------|-------------|
| 8 | Default judgment |
| 9 | Consent judgment |
| 11 | Motion before trial |
| 12 | Jury verdict |
| 13 | Directed verdict |
| 14 | Court trial |
| 15 | Arbitrator award |
| 16 | Stayed pending bankruptcy |
| 17 | Other judgment |
| 18 | Statistical closing |
| 19 | Appeal affirmed (magistrate) |
| 20 | Appeal denied (magistrate) |

---

## Arbitration Choices

| Code | Description |
|------|-------------|
| M | Mandatory |
| V | Voluntary |
| E | Exempt |
| Y | Yes, but type unknown |

---

## Class Action Status

| Code | Description |
|------|-------------|
| D | Denied |
| G | Granted |

---

## Nature of Judgment

| Code | Description |
|------|-------------|
| 1 | No monetary award |
| 2 | Monetary award only |
| 3 | Monetary award and other |
| 4 | Injunction |
| 5 | Forfeiture/foreclosure/condemnation |
| 6 | Costs only |
| 7 | Costs and attorney fees |

---

## Judgment Favors

| Code | Description |
|------|-------------|
| 1 | Plaintiff |
| 2 | Defendant |
| 3 | Both |
| 4 | Unknown |

---

## Pro Se Status

| Code | Description |
|------|-------------|
| 0 | No pro se plaintiffs or defendants |
| 1 | Pro se plaintiffs, no pro se defendants |
| 2 | Pro se defendants, no pro se plaintiffs |
| 3 | Both pro se plaintiffs and defendants |

---

## Why IDB Data Matters

The FJC IDB provides structured metadata that PACER itself doesn't always surface clearly:

1. **Origin codes** tell you HOW the case entered the court (original filing vs. transfer vs. removal from state court)
2. **Disposition codes** tell you HOW the case ended (settlement vs. jury verdict vs. default judgment)
3. **Class action status** tells you whether class certification was granted or denied
4. **Nature of judgment** and **judgment favors** tell you WHO won and WHAT they got
5. **Pro se status** helps identify cases with self-represented parties (less likely to be corporate)
6. **Procedural progress** tells you how far the case got before resolution

This data is invaluable for analyzing outcomes and filtering cases by resolution type.

---

## Sources
- CourtListener Bulk Data: https://www.courtlistener.com/help/api/bulk-data/
- CourtListener PACER APIs: https://www.courtlistener.com/help/api/rest/pacer/
- CourtListener GitHub (models): https://github.com/freelawproject/courtlistener/blob/main/cl/recap/models.py
- FJC Integrated Database: https://www.fjc.gov/research/idb
