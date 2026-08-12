# IssuePilot 90-second demo

## Preparation

```powershell
docker compose up --build
```

Open `http://localhost:8080`. No model key is required; without one, the UI must display **Deterministic fallback**.

## Talk track

1. Submit the default Windows package-cache issue.
2. Show the ranked evidence and explain that BM25 supplies the relevance boundary before deterministic vector reranking.
3. Show the two allowlisted read-only tool results. The workflow cannot run shell commands or write to GitHub.
4. Click **Approve draft** and show that approval produces a payload without publishing it.
5. Inspect the rendered trace spans for retrieval, tool selection, tool execution, and generation.
6. Run `issuepilot-eval --output artifacts/evaluation.json`; explain that the four cases are synthetic regression fixtures, not production accuracy.

## Fallback order

1. Live Docker UI with optional model key.
2. Local API with deterministic generation.
3. Committed evaluation JSON and CI artifact.

## Truthfulness boundaries

- The committed benchmark is synthetic and intentionally small.
- Hash vectors provide deterministic offline vector similarity; a live embedding service is not claimed.
- The model adapter is covered with a protocol-level test, but model quality is not claimed without a recorded live run.
- Approval produces a publishable payload only. IssuePilot never posts it automatically.
- A query with no lexical evidence returns no citations or tools and cannot be approved.
