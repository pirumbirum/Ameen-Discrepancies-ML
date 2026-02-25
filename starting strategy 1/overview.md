# Starting Strategy 1 -- Overview

## Goal
Build a ranked dataset of the 100 richest federal corporate litigation cases, selected from a pool of 50,000.

---

## Pipeline

| Step | What | API Calls | Time | Output |
|------|------|-----------|------|--------|
| **Step 1** | Gather 50K cases (metadata + entries) | ~77,500 | ~16 hours | Raw case data |
| **Step 2** | Parse & classify documents per case | 0 | Minutes | Manifests with doc types |
| **Step 3** | Score, rank, select top 100, download docs | ~600-1,100 | ~1 hour | Final dataset |

## Key Design Decisions
- Save progress every 15 minutes (not just at completion)
- Checkpoint/resume on crash
- NOS codes as primary filter for corporate cases
- Text descriptions, not numeric codes, for NOS matching
- Omit `plain_text` in bulk pull, fetch only for top 100
- Tier 1 NOS codes first (inherently corporate), Tier 2 to fill

## Files
- `step_1_gather_50k_cases.md` -- Full spec for the bulk data pull
- `step_2_map_associated_docs.md` -- Document classification and manifest creation
- `step_3_rank_and_select_top_100.md` -- Scoring system and final selection
