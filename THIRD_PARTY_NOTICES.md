# Third-party notices

IssuePilot V2 directly uses the following open-source packages:

| Project | Use | License |
| --- | --- | --- |
| [LangGraph](https://github.com/langchain-ai/langgraph) | State graph runtime and human interrupt/resume | MIT |
| [langgraph-checkpoint-sqlite](https://pypi.org/project/langgraph-checkpoint-sqlite/) | Durable local graph checkpoints | MIT |
| [rank-bm25](https://github.com/dorianbrown/rank_bm25) | `BM25Plus` lexical scoring | Apache-2.0 |

The dependency distributions retain their own license metadata. No source file from these projects is copied into this repository.

The append-only trajectory design is informed by [mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent) (MIT). The UI event projection is informed by the open-source portion of [OpenHands](https://github.com/OpenHands/OpenHands) (MIT). No OpenHands `enterprise/` code and no source files from either project are copied.

The evaluation structure is informed by [SWE-bench](https://github.com/SWE-bench/SWE-bench) (MIT). IssuePilot does not redistribute the SWE-bench dataset in this repository.
