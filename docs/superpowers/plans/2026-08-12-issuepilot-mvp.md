# IssuePilot MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a reproducible GitHub issue diagnosis copilot with hybrid retrieval, controlled tools, approval, traces, evaluation, UI, Docker, and CI.

**Architecture:** A FastAPI backend owns deterministic data and workflow boundaries. A Vite React frontend renders evidence returned by typed APIs; optional live integrations remain adapters around a fully testable offline core.

**Tech Stack:** Python 3.12, FastAPI, SQLite, httpx, pytest, Ruff, React, TypeScript, Vite, Vitest, Docker Compose, GitHub Actions.

---

### Task 1: Repository baseline

- [x] Add Python and frontend manifests, README, environment example, and fixture provenance.
- [x] Verify dependency installation and empty test runners.
- [x] Commit the baseline.

### Task 2: Retrieval and ingestion core

- [x] Write failing tests for tokenization, hybrid ranking, duplicate handling, and bounded GitHub imports.
- [x] Implement domain types, SQLite repository, hybrid retrieval, and read-only GitHub client.
- [x] Run focused tests and commit.

### Task 3: Diagnosis, approval, and traces

- [x] Write failing tests for citation grounding, tool allowlists, fallback labeling, approvals, and redacted traces.
- [x] Implement the deterministic workflow and optional provider boundary.
- [x] Run focused tests and commit.

### Task 4: API and evidence console

- [x] Write failing API and rendered component tests.
- [x] Implement FastAPI routes and the React evidence console.
- [x] Run backend/frontend tests and builds, then commit.

### Task 5: Evaluation and delivery

- [x] Write failing evaluation threshold and reproducibility tests.
- [x] Add the synthetic benchmark, JSON report, Docker files, CI, and 90-second demo guide.
- [x] Run full verification, inspect scope, and commit.

### Task 6: Publish

- [x] Create the public GitHub repository, push the implementation branch, and open a draft PR.
- [x] Confirm CI and public evidence links.

