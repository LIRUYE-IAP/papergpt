# PaperGPT Roadmap

## Phase 0 — Implemented

- Next.js and FastAPI foundations.
- PostgreSQL with pgvector and Redis local infrastructure.
- SQLAlchemy models, Alembic, health checks, and baseline tests.

## Phase 1 — Implemented

- Account registration, Argon2 password hashing, login, JWT bearer authentication, and `/auth/me`.
- Authenticated PDF upload with validation, configurable size limit, SHA-256, and local storage abstraction.
- Per-user paper list, detail, and deletion with backend ownership enforcement.
- Minimal registration, login, library, upload, detail, and delete UI.
- Integration tests for authentication, upload, CRUD, storage deletion, and ownership isolation.

Phase 1 intentionally does not parse PDF contents or invoke any AI provider.

## Phase 2 — Not implemented

Phase 2 has not started. Document parsing, OCR, background processing, translation, retrieval, AI chat, exports, and commercial features remain future work and require separate approval before implementation.
