# Architecture: runnable demo vs target platform

## Current run path (implemented G2 local slice)
```
web/index.html (plain HTML + JS, local-only)
 -> FastAPI /analysis -> deterministic EIE -> fixture JSON (SHA256 content checked)
 -> FastAPI /proposals -> SQLite proposal snapshot + fingerprint
 -> /decision -> approver demo persona + current evidence recheck
 -> /execute -> SQLite mock work order (unique idempotency key)
 -> /reconcile -> lookup mock work order receipt
```

No LLM, embedding, graph store, retrieval index, third-party services, distributed API or real authentication exists in this starter. A demo persona is not a security boundary.

## Target path (specification, NOT implemented)
```
React/TypeScript
 -> Authenticated FastAPI + JWT/OIDC RBAC + audit
 -> LangGraph planner (read-only tools and bounded reasoning)
 -> PostgreSQL row policies + structured event SQL views
 -> pgvector + lexical hybrid retriever (ACL pre-filter, version tags)
 -> claim extraction / NLI baseline + Bitemporal EIE conflict resolver
 -> risk calibrated action gate (draft only)
 -> approval state machine + transactional outbox
 -> separate mock work-order server + idempotency/receipt reconciliation
 -> tracing + evaluation reports + provenance ledger
```

Work in dependency order, gated by `docs/TASK_BOARD.md`. Switching SQLite to PostgreSQL without an identity and permission boundary is not enough to remove the demo-only restriction.
