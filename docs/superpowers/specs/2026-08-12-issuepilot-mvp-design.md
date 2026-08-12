# IssuePilot MVP Design

## Outcome

Build a portfolio-ready GitHub issue diagnosis copilot that demonstrates grounded retrieval, read-only tool use, human approval, traceability, and reproducible evaluation. It must remain useful without a model API key and clearly label deterministic fallback output.

## Scope

- Import a bounded set of public GitHub issues through the official REST API.
- Index issue and documentation snapshots with BM25 plus vector similarity.
- Diagnose a new issue with citations and a small allowlist of read-only tools.
- Require explicit approval before producing a publishable comment payload; never post to GitHub.
- Record an end-to-end trace containing retrieval, tool, generation, latency, and mode evidence.
- Run a committed offline benchmark for retrieval, citation coverage, tool choice, and latency.
- Provide a FastAPI API, a small React evidence console, Docker Compose, and CI.

## Architecture

The backend uses focused Python modules for domain types, ingestion, retrieval, diagnosis, trace storage, and evaluation. SQLite stores snapshots and traces; the retrieval index is rebuilt deterministically from stored documents. An optional OpenAI-compatible provider may generate the final draft, while the default deterministic provider keeps tests, demos, and CI reproducible.

The frontend is a Vite React console with one issue form and one evidence view. It renders the answer, citations, selected tools, approval state, and trace spans. It does not hide fallback mode or claim that a draft was published.

## Safety and truthfulness

- GitHub access is read-only and restricted to public repository data for the MVP.
- No shell, filesystem, repository write, or arbitrary URL tools are exposed to the diagnosis workflow.
- User-provided content is treated as data, not instructions.
- Secrets, authorization headers, and raw model reasoning are never stored in traces.
- Synthetic benchmark data is labeled synthetic; live GitHub results are not committed automatically.

## Success criteria

- A fresh checkout can run backend tests, frontend rendered tests, builds, and the offline evaluation.
- The demo diagnoses a fixed issue, shows at least two citations, a tool decision, approval state, and trace timing.
- The evaluation command emits machine-readable JSON and fails when configured quality floors regress.
- Docker Compose validates and starts the API plus frontend without requiring a model key.

