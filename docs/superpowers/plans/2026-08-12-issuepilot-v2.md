# IssuePilot V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade IssuePilot into a durable, repository-scoped GitHub investigation agent with real read-only tools, replayable trajectories, human pause/resume, and stronger evaluation.

**Architecture:** LangGraph owns the state machine and SQLite checkpoints. Focused adapters access fixed GitHub REST endpoints; a projection store exposes stable investigation/event API models to React.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, langgraph-checkpoint-sqlite, rank-bm25, SQLite, httpx, React 19, Vitest, Docker Compose.

---

### Task 1: Adopt licensed retrieval and provenance

**Files:** `pyproject.toml`, `src/issuepilot/retrieval.py`, `tests/test_retrieval.py`, `THIRD_PARTY_NOTICES.md`

- [ ] Write a failing test proving `HybridRetriever` exposes BM25Okapi scores while preserving the weak-match boundary.
- [ ] Run `pytest tests/test_retrieval.py -q` and observe the missing dependency/behavior failure.
- [ ] Add pinned `rank-bm25`, `langgraph`, and SQLite checkpoint packages; wrap `BM25Okapi` behind the existing `search()` API.
- [ ] Record direct dependency reuse and design-only references with license links in `THIRD_PARTY_NOTICES.md`.
- [ ] Run retrieval tests, Ruff, and `pip check`; commit.

### Task 2: Build real read-only GitHub evidence tools

**Files:** `src/issuepilot/github.py`, `src/issuepilot/investigation_tools.py`, `src/issuepilot/investigation_domain.py`, `tests/test_investigation_tools.py`

- [ ] Write failing HTTP-contract tests for fixed endpoints: repository/readme, issue search, failed workflow runs, and commits.
- [ ] Verify RED: expected methods and evidence models do not exist.
- [ ] Implement `RepositoryRef`, `EvidenceArtifact`, `GitHubEvidenceClient`, and an allowlisted `InvestigationToolRegistry` with bounded previews and safe errors.
- [ ] Add negative tests for malformed repository names, arbitrary tool names, secret redaction, 403, and 404.
- [ ] Run focused tests and commit.

### Task 3: Add a durable LangGraph investigation trajectory

**Files:** `src/issuepilot/investigation_graph.py`, `src/issuepilot/investigation_store.py`, `tests/test_investigation_graph.py`

- [ ] Write failing tests for `validate → retrieve → hypothesize → tools → synthesize → interrupt`, including ordered append-only events.
- [ ] Write a restart test that constructs a second service over the same SQLite files and resumes approval by thread id.
- [ ] Implement typed graph state, deterministic hypothesis formation, cited synthesis, `interrupt()` approval, and publishable-but-never-published finalization.
- [ ] Add no-evidence, reject, ungrounded-model, and duplicate-resume tests.
- [ ] Run graph/store tests and commit.

### Task 4: Expose investigation, replay, and approval APIs

**Files:** `src/issuepilot/api.py`, `tests/test_investigation_api.py`

- [ ] Write failing API tests for create/get/SSE/approve/reject and missing-id semantics.
- [ ] Implement `POST /api/investigations`, `GET /api/investigations/{id}`, `GET /api/investigations/{id}/events`, and `POST /api/investigations/{id}/approval`.
- [ ] Ensure SSE emits monotonically increasing ids and JSON event data without secrets.
- [ ] Run API and full backend tests; commit.

### Task 5: Replace the single-card UI with an investigation console

**Files:** `frontend/src/App.tsx`, `frontend/src/App.test.tsx`, `frontend/src/styles.css`

- [ ] Write a failing rendered interaction test for repository intake, hypotheses, tool evidence, ordered trajectory, and approve/reject.
- [ ] Implement typed API functions and split presentational sections inside `App.tsx` without introducing a state library.
- [ ] Render `awaiting_approval`, `approved`, `rejected`, and `insufficient_evidence` explicitly.
- [ ] Run Vitest and production build; commit.

### Task 6: Strengthen evaluation, CI, and portfolio evidence

**Files:** `src/issuepilot/evaluation.py`, `data/investigation_benchmark.json`, `docs/evidence/investigation-evaluation.json`, `.github/workflows/ci.yml`, `README.md`, `docs/demo/90-second-demo.md`

- [ ] Write failing evaluation tests for evidence recall, hypothesis support, citation grounding, trajectory completeness, and approval safety.
- [ ] Add a reproducible multi-case fixture and required quality floors; generate the committed report twice and compare hashes.
- [ ] Add license/dependency checks and the V2 evaluation artifact to CI.
- [ ] Update architecture, open-source attribution, truthful non-claims, and demo instructions.
- [ ] Run backend, frontend, audit, evaluation, Compose, diff, and secret gates; request code review; push a draft PR and merge only after CI approval.
