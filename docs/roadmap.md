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

## Phase 3 — Implemented

- Authenticated, ownership-scoped original-PDF delivery with `application/pdf`, inline disposition, and single byte-range support.
- PDF.js rendering at `/paper/[id]` without exposing local storage paths.
- Side-by-side Original PDF and reading-order Structured document panels.
- Actual per-page bbox-to-rendered-viewport overlay mapping, including resize rerendering.
- Stable Phase 2 Block UUIDs used directly by PDF overlays, DOM anchors, URL state, and active selection.
- Right-to-left and left-to-right click navigation.
- Debounced center-block scroll synchronization with a source lock that prevents feedback loops.
- Persisted outline navigation to each Section's first available Block.
- Explicit not-started, processing, failed, completed, and retry Reader states.
- Original, Structured, and side-by-side modes; Bilingual is disabled and labelled as future work.
- Desktop-first responsive layout that stacks panels on narrower viewports.

## Phase 4 — Not implemented

Translation and bilingual content are not implemented. No provider or LLM call is made by the Phase 3 Reader.

The following also remain future work:

- Translation and glossary workflows
- LLM provider integrations
- Embeddings, retrieval, RAG, and AI chat
- Celery, asynchronous parsing, progress events, and SSE
- OCR
- S3-compatible storage implementation
- Notes and Word export
- Memberships, plans, and payments
