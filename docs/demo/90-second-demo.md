# IssuePilot V2 90-second demo

## Start

```powershell
docker compose up --build
```

Open `http://localhost:8080`. Set `GITHUB_TOKEN` in `.env` if anonymous GitHub rate limits are exhausted.

## Talk track

1. Enter `chenyi-c/issuepilot` and a CI/cache failure report, then start the investigation.
2. Show the four fixed read-only tools and evidence links: repository README, matching issues, failed workflow runs, and commits.
3. Explain that each supported hypothesis names its evidence ids; the draft repeats those ids instead of relying on an opaque answer.
4. Walk through the ordered trajectory and point out the durable `awaiting_approval` checkpoint.
5. Restart the backend if time permits, reload the investigation id, then approve or reject it. Approval only creates a publishable payload; `published` remains false.
6. Run `issuepilot-investigation-eval --output artifacts/investigation-evaluation.json` and distinguish the five-case synthetic regression gate from production accuracy.

## Fallback order

1. Live public GitHub investigation with a token.
2. Live deterministic investigation using injected/demo evidence.
3. Committed V2 evaluation JSON plus GitHub Actions evidence.

## Safety boundaries

- Repository input is parsed as `owner/name`; arbitrary URLs are rejected.
- GitHub access uses fixed GET endpoints only.
- No shell, clone, comment, workflow rerun, or repository mutation tool exists.
- Tokens and authorization values are not persisted.
- Missing or failed evidence blocks approval instead of producing a confident diagnosis.
