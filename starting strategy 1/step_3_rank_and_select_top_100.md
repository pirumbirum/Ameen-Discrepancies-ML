# Step 3: Rank 50K Cases and Select Top 100

## Objective
Score all 50,000 cases by data richness, rank them, and select the top 100 with the most substantive documentation (post-trial opinions, verdicts, judgments).

## Prerequisite
Step 2 complete: All 50K cases have manifest.json with classified documents.

---

## Scoring System

### Document Presence Scores

| Signal | Points | Detection |
|--------|--------|-----------|
| Post-trial opinion exists | +10 | `opinions` count > 0 |
| Each additional opinion | +5 | Per opinion beyond the first |
| Final judgment | +8 | `judgments` count > 0 |
| Jury or bench verdict | +8 | `verdicts` count > 0 |
| Summary judgment ruling | +6 | `summary_judgment_rulings` count > 0 |
| Motion to dismiss ruling | +5 | `motion_to_dismiss_rulings` count > 0 |
| Settlement/consent decree | +3 | `settlements` count > 0 |
| Briefs filed | +1 each | Up to +5 max |

### Document Quality Scores

| Signal | Points | Detection |
|--------|--------|-----------|
| Opinion with 20+ pages | +3 per | `page_count >= 20` on opinion documents |
| Opinion with 50+ pages | +5 per | `page_count >= 50` (very substantive) |
| Opinion available in RECAP | +2 per | `is_available=true` on opinion docs |
| Opinion free on PACER | +2 per | `is_free_on_pacer=true` |
| All opinions available | +5 bonus | Every opinion has `is_available=true` |

### Case Complexity Scores

| Signal | Points | Detection |
|--------|--------|-----------|
| 50+ docket entries | +3 | `total_entries >= 50` |
| 100+ docket entries | +5 | `total_entries >= 100` |
| 200+ docket entries | +8 | `total_entries >= 200` |
| Case lasted 2+ years | +3 | `date_terminated - date_filed >= 730 days` |
| Case lasted 5+ years | +5 | `date_terminated - date_filed >= 1825 days` |
| Case went to trial | +10 | Verdict exists OR trial-related entries |

### Negative Scores (Deprioritize)

| Signal | Points | Detection |
|--------|--------|-----------|
| Settled in < 6 months | -5 | Quick termination + settlement entry |
| < 10 docket entries | -5 | Very thin case |
| No opinions at all | -10 | `opinions` count = 0 |
| All documents sealed | -10 | All `is_sealed=true` |

---

## Ranking Output

```json
{
    "rankings": [
        {
            "rank": 1,
            "docket_id": 67591026,
            "case_name": "SEC v. Mega Corp Inc.",
            "court_id": "nysd",
            "nature_of_suit": "Securities",
            "score": 87,
            "score_breakdown": {
                "opinions": 25,
                "judgments": 8,
                "verdicts": 8,
                "quality": 16,
                "complexity": 18,
                "availability": 12
            },
            "opinion_count": 4,
            "opinions_available": 4,
            "total_entries": 312,
            "case_duration_days": 1287
        },
        {
            "rank": 2,
            ...
        }
    ],
    "total_scored": 50000,
    "top_100_min_score": 45,
    "top_100_avg_score": 62
}
```

---

## After Selection: Download Documents for Top 100

For the 100 selected cases, download actual document content:

### Free documents (RECAP available):
```
# Just download the PDF/text directly from CourtListener
GET /api/rest/v4/recap-documents/{id}/
# Access the file at filepath_local or via the absolute_url
```

### Free on PACER (opinions):
```
# Use RECAP Fetch API -- opinions are free on PACER
POST /api/rest/v4/recap-fetch/
{
    "request_type": 2,
    "pacer_doc_id": "...",
    "court_id": "nysd",
    "pacer_username": "...",
    "pacer_password": "..."
}
```

### Paid documents (if needed):
Same Fetch API, but charges your PACER account ($0.10/page, $3.00 cap).

### API Budget for Top 100

| Action | Calls | Cost |
|--------|-------|------|
| Download RECAP-available docs | ~300-500 | Free |
| Fetch opinions from PACER | ~100-200 | Free (opinions) |
| Fetch other docs from PACER | ~200-400 | $0.10/page |
| **Total** | **~600-1,100** | **Mostly free** |

---

## Final Output Per Case

```
cases/
  top_100/
    case_67591026/
      manifest.json           # Document classification + score
      metadata.json           # Full docket metadata
      entries.json            # All docket entries
      opinions/
        opinion_001.json      # Full text of opinion
        opinion_002.json
      orders/
        order_final_judgment.json
      verdicts/
        jury_verdict.json
```

---

## No Additional API Calls for Ranking

Scoring and ranking = pure local computation on existing data.
Only the final download of documents for the top 100 requires new API calls.
