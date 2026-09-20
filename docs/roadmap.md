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
- Transactional reparse reconciliation that avoids duplicate active blocks.
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

## Phase 4A — Implemented

- Translation and TranslationVersion tables keyed directly to stable Block UUIDs.
- Unique `(block_id, target_language)` current translations with per-success version history.
- Provider-neutral translation interface, deterministic mock provider, and optional real OpenAI Responses API adapter.
- Paper, section, and previous/current/next Block context construction.
- Independent academic prompt that preserves meaning, causality, negation, and uncertainty.
- Placeholder protection and strict restoration for citations, Figure/Table references, scientific units, selected chemical species, and statistical notation.
- Synchronous whole-paper and single-Block translation APIs with ownership checks.
- Language, page, and section filters for Block-linked translation retrieval.
- Per-Block failure persistence and translated/skipped/failed counts without rolling back earlier successes.
- Automatic protection of `user_modified=true` translations.
- Stable-UUID reparse reconciliation that preserves unchanged Translation IDs, version history, source snapshots, translated text, and `user_modified` state.
- Conservative stale-history retention when a translated Block disappears or changes identity.
- Explicit untrusted-document prompt boundary and collision-safe, per-occurrence protected-token placeholders.
- Mock-provider persistence, mapping, context, protected-token, prompt-boundary, failure, retranslation, reparse, version, and ownership tests.

## Phase 4B — Not implemented

The polished Chinese/Bilingual Reader, translation editing UI, advanced glossary workflow, and translation QA workflow remain future work.

The following also remain future work:

- Advanced glossary and translation-QA workflows
- Additional provider adapters beyond the Phase 4A OpenAI boundary
- Embeddings, retrieval, RAG, and AI chat
- Celery, asynchronous parsing, progress events, and SSE
- OCR
- S3-compatible storage implementation
- Notes and Word export
- Memberships, plans, and payments
