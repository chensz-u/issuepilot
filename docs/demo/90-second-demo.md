# IssuePilot V4 90-second demo

## Start

```powershell
docker compose up --build
```

Open `http://localhost:8080`. Set `GITHUB_TOKEN` in `.env` if anonymous GitHub rate limits are exhausted.

## Talk track

1. Enter `chenyi-c/issuepilot` and a CI/cache failure report, then start the investigation.
2. Show the five fixed read-only tools and evidence links, including immutable bounded source blobs.
3. Explain supported/rejected hypotheses, the evidence-linked verification plan, and the explicit quality policy.
4. Walk through the ordered trajectory and durable `awaiting_approval` checkpoint.
5. Download the audit ZIP and verify that its manifest hashes the projection and ordered events.
6. Approve or reject; approval only creates a publishable payload and `published` remains false.
7. Run the eight-metric synthetic regression gate and distinguish it from production accuracy.

## Fallback order

1. Live public GitHub investigation with a token.
2. Live deterministic investigation using injected/demo evidence.
3. Committed V4 evaluation JSON plus GitHub Actions evidence.

## Safety boundaries

- Repository input is parsed as `owner/name`; arbitrary URLs are rejected.
- GitHub access uses fixed GET endpoints only.
- No shell, clone, comment, workflow rerun, or repository mutation tool exists.
- Tokens and authorization values are not persisted.
- Missing or failed evidence blocks approval instead of producing a confident diagnosis.
