# IssuePilot V4

Durable, evidence-first GitHub repository investigation agent for an AI application/backend portfolio.

IssuePilot accepts one or a bounded batch of repository failure reports, executes five allowlisted GitHub read tools, forms explicit hypotheses, scores evidence risk, produces a cited draft and verification plan, then pauses at a durable human approval checkpoint. Every result can be exported as a deterministic, hash-verifiable audit bundle. It never executes proposed commands, clones a repository, changes GitHub state, or publishes a comment.

## What makes V4 an agent system

| Capability | Verifiable implementation |
| --- | --- |
| Stateful workflow | LangGraph nodes: validate → tools → hypothesize → plan → assess → synthesize → approval interrupt |
| Durable execution | `langgraph-checkpoint-sqlite`; restart/resume is covered by an automated test |
| Real tools | Fixed GitHub REST calls for README, issues, failed Actions runs, commits, and bounded relevant source files |
| Evidence discipline | Every observation has an id, source URL, bounded preview, and originating tool |
| Human control | Approve/reject resumes the graph; no-evidence investigations cannot be approved |
| Replay | Ordered append-only events exposed as SSE and rendered in the React trajectory |
| Retrieval | Apache-2.0 `rank-bm25` supplies BM25Plus; deterministic vector reranking remains explicit |
| Verification plan | Evidence-linked argv steps are proposed for a human to run; IssuePilot executes none of them |
| Quality policy | Explicit grounded-evidence, multiple-source, and tool-health checks produce a low/medium/high review risk |
| Operations | Batch intake is capped at five; deterministic ZIP exports include projection, ordered events, and SHA-256 manifest |
| Evaluation | Six-case synthetic gate checks recall, precision, hypotheses, citations, plan grounding, quality policy, trajectory, and approval safety |

The latest V4 result is [`docs/evidence/investigation-evaluation.json`](docs/evidence/investigation-evaluation.json). All eight metrics, including exact plan grounding and policy accuracy against source/distractor cases, are `1.0` on the committed synthetic regression fixture. That is a reproducibility claim, not production accuracy.

The portfolio acceptance screenshot is [`docs/assets/issuepilot-v4.png`](docs/assets/issuepilot-v4.png), captured from a real browser after a live read-only investigation of this public repository.

## Open-source foundations

- [LangGraph](https://github.com/langchain-ai/langgraph) and [langgraph-checkpoint-sqlite](https://pypi.org/project/langgraph-checkpoint-sqlite/) (MIT) are used directly for graph execution and checkpoints.
- [rank-bm25](https://github.com/dorianbrown/rank_bm25) (Apache-2.0) is used directly for lexical scoring.
- [mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent), [OpenHands](https://github.com/OpenHands/OpenHands), and [SWE-bench](https://github.com/SWE-bench/SWE-bench) informed trajectory/event/evaluation design; their source was not copied.

See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for the exact reuse boundary.

## Run with Docker

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open `http://localhost:8080`. API documentation is at `http://localhost:8000/docs`.

`GITHUB_TOKEN` is optional for public repositories and raises the API rate limit. It is sent only in the authorization header and is never stored in checkpoints, projections, events, or evaluation files.

## Run in development

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m uvicorn issuepilot.api:app --reload
```

In a second terminal:

```powershell
Set-Location frontend
npm ci
npm run dev
```

## V4 API

```text
POST /api/investigations                  start and checkpoint a repository investigation
POST /api/investigations/batch            start 1-5 independently checkpointed investigations
GET  /api/investigations/{id}             reload its durable projection
GET  /api/investigations/{id}/events      replay ordered SSE trajectory events
GET  /api/investigations/{id}/audit.zip   export deterministic evidence and SHA-256 manifest
POST /api/investigations/{id}/approval    resume with approve or reject
```

The V1 diagnosis endpoints remain available for compatibility and comparison.

Audit bundles include the user-supplied title and body. Their manifest sets `contains_user_input: true`; inspect a bundle before sharing it outside the intended review context.

## Quality gates

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check src tests
.\.venv\Scripts\python -m ruff format --check src tests
.\.venv\Scripts\issuepilot-license-audit
.\.venv\Scripts\issuepilot-eval --output artifacts/evaluation.json
.\.venv\Scripts\issuepilot-investigation-eval --output artifacts/investigation-evaluation.json
Set-Location frontend
npm ci
npm test
npm run build
npm audit --audit-level=high
```

## Architecture

```text
GitHub REST (fixed read endpoints)
          |
          v
 allowlisted evidence tools ---> bounded EvidenceArtifact records
          |                                  |
          v                                  v
 LangGraph state machine ------------> cited hypotheses/draft
          |                                  |
          v                                  v
 SQLite checkpoints + event projection -> React trajectory console
                                             |
                                             v
                                  approve/reject interrupt resume
                                  (published always remains false)
```

## Interview demo

Follow [`docs/demo/90-second-demo.md`](docs/demo/90-second-demo.md). The strongest discussion points are durable graph recovery, fixed-endpoint tool security, event replay, grounding gates, and the difference between synthetic regression evidence and real-world effectiveness.

## Honest boundaries

- It is a read-only investigation assistant, not an autonomous maintainer or patch generator.
- It does not download full Actions log archives yet; V2 inspects failed run metadata and links to the run.
- It uses SQLite for a portfolio/local deployment, not a horizontally scaled production topology.
- The committed benchmark is synthetic and small; no real-user diagnostic accuracy is claimed.
- Optional model generation remains secondary to deterministic, citation-verifiable behavior.
