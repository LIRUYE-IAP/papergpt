# PaperGPT Architecture

## Current system — Phase 2

PaperGPT is a modular monolith with an independently runnable Next.js frontend and FastAPI backend.

| Layer | Technology | Current responsibility |
| --- | --- | --- |
| Frontend | Next.js App Router | Registration, login, library, upload, and basic paper detail UI |
| Backend | FastAPI | Versioned Auth, Paper, document-engine, and health APIs |
| Document engine | PyMuPDF + deterministic heuristics | Born-digital page/block extraction, bbox, columns, reading order, classification, sections, and debug JSON |
| Persistence | SQLAlchemy 2 + Alembic | User, Paper, Section, and Block models with versioned schema changes |
| Database | PostgreSQL + pgvector | Accounts, paper metadata, sections, and blocks; vector extension reserved for later phases |
| Cache foundation | Redis | Connectivity only; no Celery tasks or Phase 2 job execution |
| File storage | Local filesystem abstraction | Original PDFs and generated processing JSON under system-generated keys |

## Authentication and isolation

- Passwords use pwdlib's recommended Argon2 implementation and are never returned by the API.
- FastAPI issues HS256 JWT bearer tokens containing `sub` and `exp`; the signing secret comes only from the root `.env`.
- Paper, parse, outline, and block queries always constrain by the authenticated user ID.
- Missing and unowned papers have the same not-found response.
- CORS accepts only the configured `FRONTEND_ORIGIN`, never `*`.

## Document-engine pipeline

1. The API resolves an owned Paper and changes `parse_status` from `NOT_STARTED` or its prior state to `PROCESSING`.
2. PyMuPDF opens the stored born-digital PDF and extracts each page's spans, text blocks, image blocks, page size, fonts, and bbox.
3. Coordinates are clamped to the page and stored both in PDF points and normalized page coordinates.
4. Repeated marginal text and page-number patterns identify `HEADER`, `FOOTER`, and `PAGE_NUMBER` blocks without discarding them.
5. Deterministic font, numbering, text-pattern, and position heuristics classify titles, headings, captions, references, and other block types.
6. Narrow body blocks establish the left/right column geometry. A heading is a full-width separator only when its bbox spans at least 72% of the detected content width and reaches both main content edges; otherwise it remains in column 0 or column 1 and participates in that column's normal flow.
7. Adjacent compatible text blocks are reconstructed using column, font, font-size, indentation, and vertical-gap checks. Conservative line-end hyphen repair removes splits such as `fore-` + `casting`.
8. Heading levels build a parent/child section tree. Blocks retain their page, bbox, section, column, and globally unique reading order.
9. Block and Section primary keys are deterministic UUIDv5 anchors derived from the Paper UUID, parser version, and canonical layout identity. An unchanged parse preserves IDs for future reader, translation, note, and citation references.
10. Only after in-memory parsing succeeds, one database transaction deletes the paper's old parse result and inserts the complete new Section/Block set.
11. Debug artifacts are first written as a complete hidden staging directory. Directory promotion replaces the prior `processing/` set; a failed promotion restores the prior complete set. PostgreSQL remains authoritative.

Parse failure sets the Paper status to `FAILED`. A parser failure before replacement leaves an existing complete parse result intact; database persistence is transactional. Phase 2 executes synchronously and does not introduce Celery.

PostgreSQL transactions and filesystem renames cannot form one cross-resource ACID transaction. The implementation therefore guarantees complete database replacement and complete debug-artifact sets independently. If filesystem promotion fails after database commit, the old complete artifact set is retained and `parse_status` becomes `FAILED`, explicitly signalling that artifacts do not represent the latest database parse.

## Data model

`Section` belongs to one Paper and optionally to a parent Section. It stores original/translated-title slots, level, stable document order, start/end pages, and a future summary slot.

`Block` belongs to one Paper and optionally one Section or parent Block. It stores:

- page number and globally unique per-paper reading order
- supported block enum
- original text
- absolute and normalized bbox JSON
- column index
- extraction metadata
- translatability flag
- timestamps

Foreign keys cascade from Paper. Reparse safely replaces child records, and Paper deletion stages and removes the complete storage subtree, including processing artifacts.

## Storage layout

```text
storage/papers/{user_id}/{paper_id}/
├── original/
│   └── original.pdf
└── processing/
    ├── raw_pdf_blocks.json
    ├── layout.json
    └── document.json
```

The local implementation remains behind `LocalStorage`. S3-compatible storage is future work.

## Coordinate invariants

- Page width/height and block bbox originate from the same PyMuPDF `page.get_text("dict")` coordinate system.
- Every persisted bbox satisfies `0 <= x0 < x1 <= page_width` and `0 <= y0 < y1 <= page_height`.
- Normalized coordinates satisfy `0 <= x0 < x1 <= 1` and `0 <= y0 < y1 <= 1`.
- Block extraction metadata repeats the applicable page width and height for inspectable validation.
- Debug page records retain PyMuPDF page number, rotation, and crop box.

The Phase 2 baseline targets ordinary unrotated born-digital PDFs. Rotation and crop-box metadata are preserved, but unusual rotated/cropped combinations are not explicitly transformed with rotation/derotation matrices and remain a documented acceptance limitation.

## Real-world PDF acceptance checklist

Use only a locally supplied PDF that is authorized for testing; never add an unknown-copyright academic PDF to Git. Before accepting a new publisher layout, manually verify:

- title and abstract classification
- numbered/unnumbered heading hierarchy
- left-column then right-column reading order
- column-local heading placement
- figure and table captions
- References boundary and non-translatable entries
- repeated header/footer/page-number handling
- source-page bbox alignment
- absolute/normalized bbox bounds against page dimensions

## Explicit future boundaries

- **Phase 3 Reader:** no PDF rendering, block overlay, or reader synchronization UI is implemented.
- **Translation:** no translated blocks, glossary, provider calls, or translation workflow is implemented.
- **AI:** no LLM, embedding, RAG, or chat integration is implemented.
- **Async processing:** Redis is available, but Celery, job queues, progress events, and SSE are not implemented.
- **OCR:** scanned PDFs are detected only; no OCR pipeline is installed.
- **Export and commercial features:** Word export, memberships, plans, and payments remain future work.
