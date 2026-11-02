# Third-party notices and due diligence queue

The starter kit has original reference implementation and test fixtures. It does **not** vend third-party model weights, data dumps, or GitHub repository source.

- Python app runtime: FastAPI, Starlette, Pydantic, Uvicorn; review current dependency licenses before any public distribution.
- Tests/development: Pytest, HTTPX, Ruff; review their current license terms.
- Research candidates not included as dependencies: LangGraph, pgvector, GraphRAG, SURE-RAG, EnterpriseRAG-Bench, FEVER, Langflow, etc. See `docs/research/PRIOR_ART_CHECKLIST.md`.
- The v2.0 plan includes URLs for reference; external dataset download, copyright terms, model weights and verification are pending.
- Choose a license for the user's own repository **before** releasing on GitHub. No license decision is imposed by this kit.
