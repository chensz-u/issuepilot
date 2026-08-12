# IssuePilot

Evidence-first GitHub issue diagnosis copilot for an AI application/backend portfolio.

IssuePilot combines bounded public-issue ingestion, a BM25 relevance gate with deterministic vector reranking, executed read-only tools, optional model generation, human approval, persisted traces, and an offline quality gate. It is designed to answer the engineering question that generic RAG demos avoid: **what evidence proves this recommendation, and how do we detect a regression?**

## Evidence at a glance

| Capability | Verifiable evidence |
| --- | --- |
| Hybrid retrieval | BM25 blocks irrelevant evidence; vector scores rerank relevant matches with deterministic ties |
| GitHub ingestion | Official REST API, public closed issues, 1–100 item bound, pull requests excluded |
| Tool safety | Two allowlisted read-only adapters execute and return summaries; no shell, filesystem, arbitrary URL, or GitHub write tool |
| Human control | Grounded drafts stay pending until approved; no-evidence drafts are blocked; approval never publishes |
| Traceability | Retrieval, tool selection, tool execution, generation mode, duration, and redacted input persisted in SQLite |
| Evaluation | Synthetic-v1 Hit@2, draft-to-document citation grounding, and tool-selection quality floors run in CI |
| Model integration | Optional OpenAI Responses adapter; deterministic fallback is explicit when absent or unavailable |

The latest committed offline result is [`docs/evidence/evaluation.json`](docs/evidence/evaluation.json). It is a four-case synthetic regression fixture, not a real-world accuracy claim.

## Run locally

### Docker-first

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open `http://localhost:8080`. The API is available at `http://localhost:8000/docs`.

### Development

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
$env:PYTHONPATH = "src"
python -m uvicorn issuepilot.api:app --reload
```

In a second terminal:

```powershell
Set-Location frontend
npm ci
npm run dev
```

## Import public issue evidence

```powershell
issuepilot-import pypa/pip --limit 30 --database issuepilot.db
```

Unauthenticated public requests work within GitHub's rate limit. Set `GITHUB_TOKEN` locally for a higher limit; tokens are never written to traces or snapshots. Imports update SQLite and are not committed automatically.

## Run the quality gate

```powershell
pytest
ruff check src tests
ruff format --check src tests
issuepilot-eval --output artifacts/evaluation.json
Set-Location frontend
npm test
npm run build
```

Current synthetic-v1 floors:

- retrieval Hit@2 ≥ 0.75
- citation grounding rate = 1.00
- tool-selection accuracy = 1.00

## API flow

```text
POST /api/diagnoses -> grounded draft + citations + executed tool summaries + approval state + trace id
GET  /api/traces/{id} -> redacted workflow spans
POST /api/approvals/{id} -> publishable payload, published=false
```

## Optional model mode

Set `OPENAI_API_KEY` and optionally `OPENAI_MODEL`. The backend uses the Responses API with a prompt-injection boundary: issue content is untrusted data, and the answer must use supplied evidence. HTTP, malformed, or citation-ungrounded output falls back to the deterministic draft. `/health` reports the configured generation mode.

No live model-quality result is committed in this MVP. The adapter is verified with an HTTP protocol test, while CI remains keyless and reproducible.

## Interview demo

Use the [90-second demo guide](docs/demo/90-second-demo.md). The strongest discussion topics are hybrid-ranking trade-offs, deterministic fallback, approval-before-write, trace redaction, and why a synthetic quality gate is useful but insufficient evidence of production accuracy.

## Architecture

```text
GitHub REST -> bounded issue snapshot -> SQLite -> hybrid retriever
                                                -> diagnosis workflow
                                                   |- read-only tool execution
                                                   |- deterministic/model generator
                                                   |- pending approval
                                                   `- redacted trace
React evidence console <- FastAPI typed responses <-'
```

## Non-claims

- Not an autonomous maintainer or auto-comment bot.
- No production retrieval-scale, security certification, or real-user accuracy claim.
- Deterministic hash vectors are an offline fallback, not a semantic embedding quality claim.
- The fixed benchmark measures regression behavior only.
