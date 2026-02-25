# Chat Sync #2 — Session 019xLwYKTKRXs2c4pJqQHMEP
**Synced at:** 2026-02-25 ~20:55 UTC

---

## Context
This is the continuation of our session after migrating everything from the old `Ameen` repo to the new `Ameen-Discrepancies-ML` (ML repo). The old Ameen repo is considered poisoned and should never be accessed again unless explicitly told.

## What Happened This Session

### 1. Repo Migration
- Cloned `pirumbirum/Ameen-Discrepancies-ML` (was empty)
- Copied over from old repo:
  - `courtlistener_reference/` — Pure CourtListener API guide (9 docs)
  - `starting strategy 1/` — 3-step pipeline plan (overview + steps 1-3)
  - `chat 1/` — Session sync folder
- Created new files in ML repo:
  - `.github/workflows/00_test_api_connection.yml` — Read-only API test
  - `.github/workflows/01_count_nos_volumes.yml` — Count cases per NOS code
  - `.github/workflows/02_pass1_metadata_sweep.yml` — Pass 1 metadata sweep
  - `.github/workflows/03_pass2_entry_pull.yml` — Pass 2 entry pull
  - `scripts/crawler_lib.py` — Shared library (rate limiter, checkpoint, progress)
  - `scripts/pass1_metadata_sweep.py` — Standalone Pass 1 script

### 2. Workflow Design — Safety & Isolation
All workflows are:
- `workflow_dispatch` (manual trigger only)
- Isolated from each other (failure in one can't poison others)
- Rate limited (4800/hr with 200 buffer)
- Checkpointed (resume on crash)
- Timeout-capped (can't run forever)

### 3. Dry Run Test
- First attempt failed instantly — inline heredoc Python had import issues
- Fixed by moving Python to standalone `scripts/pass1_metadata_sweep.py`
- Second attempt: **SUCCESS** in 7m43s (mostly GitHub Actions VM setup overhead)
- 14 API calls (2 pages x 7 Tier 1 NOS codes), data saved as artifacts
- Confirmed: API auth works, NOS filters work, pagination works, checkpoint works

### 4. Current State — About to Start Full Pass 1
- User wants full Pass 1 run NOW (not dry run)
- Every 15 minutes: commit data to `cases/` folder in repo + progress report
- Pipeline: Pull metadata for ~50K federal corporate litigation dockets
- Tier 1 NOS: Securities, Patent, Trademark, Antitrust, Stockholders, RICO, Trade Secret (~33K)
- Tier 2 NOS: Other Contract, Insurance, Banks, Environmental (~17K)
- Date range: 2015-2025
- Estimated: ~2,500 API calls, ~30 minutes

## Repo Secrets (set on ML repo)
- `COURTLISTENER_TOKEN` — CourtListener API token
- `ANTHROPIC_API_KEY` — Anthropic API key

## Branch
All work on: `claude/add-file-upload-V80Zw`

## Key Decisions
- EVERYTHING runs through GitHub Actions, never Claude Code sandbox (saves Claude usage)
- Old Ameen repo is dead, all work in ML repo only
- Workflows isolated — "if we fuck up one, the poison doesn't spread"
- Data saves every 15 minutes with progress reports
- Results committed to `cases/` folder in repo (not just artifacts)

## Strategy Recap (from starting strategy 1/)
1. **Step 1**: Gather 50K cases (Pass 1: metadata ~30min, Pass 2: entries ~16hrs)
2. **Step 2**: Parse & classify documents per case (local processing, minutes)
3. **Step 3**: Score, rank, select top 100, download docs (~1hr)
