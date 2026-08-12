# IssuePilot V2 Design

## Goal

Turn the MVP into a durable, read-only GitHub repository investigation agent. A run must form hypotheses, call real GitHub evidence tools, persist a replayable trajectory, pause for human approval, and resume safely after process restart.

## Open-source reuse

| Source | License | Reuse in IssuePilot |
| --- | --- | --- |
| [LangGraph](https://github.com/langchain-ai/langgraph) | MIT | `StateGraph`, durable checkpoints, and human `interrupt`/resume; used as a dependency rather than reimplemented |
| [langgraph-checkpoint-sqlite](https://pypi.org/project/langgraph-checkpoint-sqlite/) | MIT | Local durable checkpoint storage |
| [rank-bm25](https://github.com/dorianbrown/rank_bm25) | Apache-2.0 | Replace the hand-written BM25 formula with the maintained `BM25Okapi` implementation |
| [mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent) | MIT | Design reference for an append-only, replayable trajectory; no Bash execution and no source copied |
| [OpenHands](https://github.com/OpenHands/OpenHands) | MIT outside `enterprise/` | Design reference for event-stream communication; no enterprise code and no source copied |
| [SWE-bench](https://github.com/SWE-bench/SWE-bench) | MIT | Evaluation methodology reference; keep offline fixtures explicit and reproducible |

`THIRD_PARTY_NOTICES.md` will record dependencies, licenses, and the exact boundary between direct library reuse and design inspiration.

## Architecture

The API creates one LangGraph thread per investigation. Nodes run in a fixed, inspectable graph: validate repository → retrieve local evidence → form hypotheses → execute allowlisted GitHub tools → synthesize a cited draft → interrupt for approval → finalize a publishable payload without posting it. The SQLite checkpointer owns resumable graph state; the application repository owns investigation metadata and an append-only event projection for UI replay.

GitHub access is restricted to a parsed `owner/repository` identifier and fixed read endpoints. Tools are `search_issues`, `read_repository_context`, `inspect_failed_workflows`, and `inspect_recent_commits`. Tokens are optional, never persisted, and redacted from errors/events. No shell, clone, arbitrary URL, mutation, comment, or workflow rerun capability exists.

## API and UI

- `POST /api/investigations` starts a repository-scoped investigation and returns its persisted state.
- `GET /api/investigations/{id}` reloads the durable projection.
- `GET /api/investigations/{id}/events` returns SSE-formatted replayable events.
- `POST /api/investigations/{id}/approval` resumes the interrupted graph with approve/reject input.
- The React console adds repository intake, hypothesis cards, a tool/evidence timeline, checkpoint state, and approve/reject controls.

## Evidence and failure rules

Every hypothesis is `proposed`, `supported`, `rejected`, or `insufficient_evidence`. Tool observations carry a source URL and bounded preview. A publishable draft must reference every evidence id it claims. GitHub 403/404/rate-limit failures become safe tool observations instead of tracebacks. No relevant evidence means `insufficient_evidence` and approval remains blocked.

## Verification

Tests cover graph pause/resume across a new service instance, tool endpoint allowlists, token redaction, SSE replay order, cited synthesis, no-evidence blocking, React rendering/interactions, and evaluation metrics. CI runs backend tests/lint/format/evaluation, frontend tests/build/audit, dependency license checks, and Docker builds. The README distinguishes synthetic regression evidence from any live GitHub run.
