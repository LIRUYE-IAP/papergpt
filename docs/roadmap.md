# PaperGPT Roadmap

## Phase 0 — Implemented

- Next.js and FastAPI foundations.
- PostgreSQL with pgvector and Redis local infrastructure.
- SQLAlchemy models, Alembic, health checks, and baseline tests.

## Phase 1 — Implemented

- Account registration, Argon2 password hashing, login, JWT bearer authentication, and `/auth/me`.
- Authenticated PDF upload with extension, MIME, non-empty, size, and `%PDF-` signature validation.
- Configurable upload limit, SHA-256, and local storage abstraction.
- Per-user paper list, detail, and deletion with backend ownership enforcement.
- Minimal registration, login, library, upload, detail, and delete UI.

## Phase 2 — Implemented

- PyMuPDF-based born-digital PDF extraction that retains page and bbox information.
- Page dimensions plus absolute and normalized block coordinates.
- Block enum and persisted PostgreSQL `sections` and `blocks` tables.
- Heuristic title, heading, caption, repeated header/footer/page-number, and references classification.
- Double-column detection and column-major reading order.
- Geometry-aware column-local headings that remain in their owning column flow.
- Paragraph reconstruction with layout/style checks and conservative English line-end dehyphenation.
- Hierarchical section detection without LLM calls.
- Transactional reparse that replaces old results and avoids duplicate blocks.
- Stable deterministic Block/Section UUID anchors across unchanged reparses.
- Paper parse states: `NOT_STARTED`, `PROCESSING`, `COMPLETED`, and `FAILED`.
- Authenticated parse, outline, and filterable block APIs.
- `raw_pdf_blocks.json`, `layout.json`, and `document.json` debug artifacts.
- Complete-set debug artifact staging and atomic directory promotion with rollback to the prior set.
- Programmatically generated three-page academic-style tests for double columns, headings, captions, repeated marginalia, references, ownership, reparse, failure, and deletion cleanup.
- Scanned-PDF detection metadata without OCR.

## Phase 3 — Not implemented

The PDF Reader, rendered page synchronization, block overlays, and reader interactions have not been implemented and require separate approval.

The following also remain future work:

- Translation and glossary workflows
- LLM provider integrations
- Embeddings, retrieval, RAG, and AI chat
- Celery, asynchronous parsing, progress events, and SSE
- OCR
- S3-compatible storage implementation
- Notes and Word export
- Memberships, plans, and payments
