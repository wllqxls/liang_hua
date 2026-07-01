# Progressive Parameter Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the manual narrow optimizer workflow with a single-coin, deterministic, progressive search that automatically explores timeframe pairs, strategies, lookbacks, and a bounded risk neighborhood.

**Architecture:** Keep the existing synchronous `/api/optimize` endpoint for compatibility and add a background-job API used by the browser. Put candidate generation and progressive orchestration in a focused `src/backtest/optimizer.py` module; routes provide the concrete backtest evaluator and store at most 20 in-memory jobs.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, threads, vanilla JavaScript, pytest

---

### Task 1: Define deterministic search candidates and budgets

**Files:**
- Create: `src/backtest/optimizer.py`
- Create: `tests/test_optimizer.py`

- [ ] Write failing tests proving that available timeframe pairs only use existing CSV files and require `context > entry`, that identical inputs produce identical stratified samples, and that position amount/backtest days are absent from candidate dimensions.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests\test_optimizer.py -q` and confirm failure because the module does not exist.
- [ ] Implement `SearchCandidate`, `SearchProgress`, `available_timeframe_pairs()`, `build_stage_one_candidates()`, and `build_stage_two_candidates()` with budgets `120 / 84 / 36`, fixed SHA-256-derived random seeds, and the approved risk multipliers.
- [ ] Re-run the focused tests and confirm they pass.

### Task 2: Add progressive orchestration and background job APIs

**Files:**
- Modify: `src/web/schemas.py`
- Modify: `src/web/routes.py`
- Modify: `tests/test_routes.py`

- [ ] Add failing route tests for `POST /api/optimize/jobs`, `GET /api/optimize/jobs/{job_id}`, one-active-job enforcement, full candidate timeframe fields, and deterministic completed results using monkeypatched evaluation.
- [ ] Add `context_timeframe` and `timeframe` to `OptimizationCandidate`; add `OptimizationJobCreated` and `OptimizationJobStatus` schemas with stage, progress, elapsed time, partial flag, result, and error.
- [ ] Implement an in-memory, lock-protected job registry capped at 20 entries and a daemon thread per accepted job. The worker runs stage one, stage two, out-of-sample/random validation, and long-window validation while updating progress and respecting 480/600-second deadlines.
- [ ] Keep `/api/optimize` working for compatibility; the new job worker reuses the existing quality, scoring, and validation functions.
- [ ] Run route tests and then all tests.

### Task 3: Switch the browser to job polling and complete parameter application

**Files:**
- Modify: `static/js/backtest.js`
- Modify: `templates/backtest.html`
- Modify: `tests/test_styles.py`

- [ ] Add a failing static contract test asserting the browser creates a search job, polls its status endpoint, renders phase/progress/elapsed time, and applies both timeframe fields.
- [ ] Change `optimizeParams()` to POST `/api/optimize/jobs`, poll once per second, render progress, stop on completion/failure, and always re-enable the button.
- [ ] Add environment and entry timeframe columns to the result table; update `applyOptimizationCandidate()` to write `context-timeframe` and `timeframe` along with strategy, lookbacks, leverage, TP, and SL.
- [ ] Bump the JavaScript cache query string and run focused plus full tests.

### Task 4: Verify runtime behavior and commit

**Files:**
- Verify only; no new production files.

- [ ] Start the local service without reload and confirm port 8000 listens.
- [ ] Create a search job for BTC/USDT, poll until at least progress is observable, and verify a second simultaneous job is rejected.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest -q` and require zero failures.
- [ ] Review `git diff` to ensure no secrets, data CSVs, or result JSONs are staged.
- [ ] Commit the plan, optimizer, schemas, routes, frontend, and tests with focused commit messages; do not push without a separate explicit request.

### Task 5: Expand leverage coverage for the top three candidates

**Files:**
- Modify: `src/backtest/optimizer.py`
- Modify: `tests/test_optimizer.py`

- [ ] Add a failing test proving ranks 1–3 each cover every value in `LEVERAGE_OPTIONS`, while ranks 4–12 only use the base leverage and its adjacent options.
- [ ] Change the stage-two budget from 72 to 84.
- [ ] Generate exactly one deterministic local mutation per leverage for each of the top three candidates, then generate at most six adjacent-leverage mutations for each remaining candidate.
- [ ] Run optimizer tests and the complete test suite.
- [ ] Commit and automatically push the verified change to the current GitHub branch.
