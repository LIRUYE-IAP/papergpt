# PaperGPT Architecture

## Current system — Phase 4B

PaperGPT is a modular monolith with an independently runnable Next.js frontend and FastAPI backend.

| Layer | Technology | Current responsibility |
| --- | --- | --- |
| Frontend | Next.js App Router + PDF.js | Registration, login, library, upload, and synchronized Original/Structured/Chinese/Bilingual Reader |
| Backend | FastAPI | Auth, Paper, PDF delivery, document-engine, glossary, translation editing/versioning/QA, and health APIs |
| Translation core | Provider-neutral services + deterministic mock/OpenAI adapters | Block context, matched glossary constraints, token protection, prompting, persistence, versioning, and deterministic QA |
| Document engine | PyMuPDF + deterministic heuristics | Born-digital page/block extraction, bbox, columns, reading order, classification, sections, and debug JSON |
| Persistence | SQLAlchemy 2 + Alembic | User, Paper, Section, Block, Translation, TranslationVersion, GlossaryTerm, and TranslationQAResult models |
| Database | PostgreSQL + pgvector | Accounts, document structure, glossary constraints, translations, QA findings, and history; vectors remain future |
| Cache foundation | Redis | Connectivity only; no Celery tasks or Phase 4B job execution |
| File storage | Local filesystem abstraction | Original PDFs and generated processing JSON under system-generated keys |

## Authentication and isolation

- Passwords use pwdlib's recommended Argon2 implementation and are never returned by the API.
- FastAPI issues HS256 JWT bearer tokens containing `sub` and `exp`; the signing secret comes only from the root `.env`.
- Paper, PDF file, parse, outline, Block, translation, version, QA, and glossary queries always constrain by the authenticated user ID.
- Missing and unowned papers have the same not-found response.
- CORS accepts only the configured `FRONTEND_ORIGIN`, never `*`.

## Reader architecture and Block Anchor Sync

The `/paper/[id]` client loads three owned resources with the same bearer token: Paper state, the nested outline, and globally ordered Blocks. PDF.js receives the original PDF only through `GET /api/v1/papers/{paper_id}/file`; the browser never receives a local filesystem path. The endpoint returns `application/pdf`, advertises byte ranges, and implements one bounded RFC 7233 range per request for PDF.js incremental reads.

The persisted deterministic Block UUID is the only synchronization identity:

```text
PDF bbox overlay <-> stable Block UUID <-> Translation.block_id <-> Reader DOM block
```

Structured, Chinese, and Bilingual nodes use `block-{uuid}` and overlays use `pdf-block-{uuid}`, with `data-block-id={uuid}` on both. No frontend-only content IDs are generated. Reader mode changes retain the same parent-owned active UUID and URL anchor.

PyMuPDF extraction coordinates use a top-left origin and include the matching page width/height. The Reader converts the absolute bbox to normalized coordinates and scales it to each actual rendered PDF.js viewport. Canvas device-pixel scaling is independent of CSS viewport dimensions, so overlays stay aligned when the panel is resized. The Phase 2 limitation for unusual rotated/cropped combinations remains; these layouts require manual verification.

One parent-owned `activeBlockId` drives both active styles. PDF and structured scroll observers choose the visible block nearest the panel center. A debounced, short-lived source lock (`pdf` or `document`) suppresses the reverse observer during programmatic scrolling and prevents feedback loops. Outline navigation resolves the first existing Block belonging to the persisted Section. The URL query `?block={uuid}` stores a refreshable Reader anchor.

## Academic translation pipeline

```text
stable Document Block
-> document/section/local context
-> protected scientific placeholders
-> provider-neutral TranslationRequest
-> mock or OpenAI provider
-> strict placeholder restoration
-> Translation + immutable TranslationVersion
-> deterministic TranslationQAResult set
-> Block-linked Reader API
```

The context builder selects the previous and next eligible Blocks in global reading order and injects only enabled glossary terms matching this bounded context. Those Blocks help resolve terminology but the prompt requests output for the current Block only. Serialized input is delimited JSON labelled as untrusted source-document data. Header/footer/page-number/reference Blocks, stale or non-translatable Blocks, figure/table bodies, and equations are conservatively skipped.

Provider code lives under `app.ai.providers`; translation business logic depends only on the abstract interface. `AI_PROVIDER=mock` is the zero-cost default. `AI_PROVIDER=openai` constructs the official Python SDK only after ownership and parsed-state checks, and requires an environment-provided key and model. The OpenAI adapter uses a stateless Responses API request with `store=False`. Tests never invoke it.

Token preprocessing protects citations, Figure/Table references, number-unit expressions, selected atmospheric chemical species, and statistical notation. Placeholders use a deterministic source-derived namespace and a per-occurrence index, so repeated equal tokens remain independently restorable without colliding with ordinary document text. Restoration requires each placeholder exactly once, so a provider cannot silently drop, duplicate, or alter a protected scientific value.

Each `(block_id, target_language)` has one current Translation. Every successful initial translation, retranslation, or manual edit appends a monotonically numbered TranslationVersion. Manual edits use reason `USER_EDIT`, set `user_modified=true`, and immediately refresh deterministic QA. Failed Blocks retain `FAILED` and `error_message`; successful Blocks are committed independently. `user_modified=true` is an unconditional automatic-translation skip.

## Glossary architecture

`GlossaryTerm` is owned by a User and has either `USER_GLOBAL` scope with no Paper, or `PAPER` scope tied to a Paper owned by that user. Database checks encode this scope/nullability invariant; service ownership checks use uniform `404` responses for missing and unowned resources. Paper terms survive reparse because they are attached to Paper rather than Block.

Resolution precedence is:

```text
PAPER > USER_GLOBAL > future DOMAIN/AUTO > MODEL
```

Phase 4B implements the first two levels. Matching respects case sensitivity, token/word boundaries, language pair, enabled state, and longest non-overlapping phrase. Paper conflicts remove the global equivalent before phrase selection. Matching never pre-replaces source content; selected source/target pairs are constraints in the provider request.

## Deterministic translation QA

QA uses no model and produces no pseudo-precise score. Each run replaces the prior `TranslationQAResult` set with named checks for completeness, protected numeric/unit/citation/Figure/Table/chemical/statistical content, glossary terminology, uncertainty markers, placeholder residue, and suspicious output. Each finding carries a status, message, and structured JSON detail. Overall status is `FAILED` when any check fails, otherwise `WARNING` when any warns, otherwise `PASSED`; an unexecuted translation is `PENDING`.

QA, edit, and version endpoints join Translation through the owned Paper and an active (`is_stale=false`) Block. Retained stale history therefore cannot appear in the current Reader or be modified through current-content endpoints.

## Chinese and Bilingual Reader

Chinese and Bilingual panels consume active Blocks and map translations by `Translation.block_id`; array position is never an identity. Missing translations render an explicit state and per-Block action. Bilingual rows put original and Chinese text in one DOM anchor, so both modes reuse Phase 3 scroll observation and PDF bbox synchronization. The parent owns the only `activeBlockId`, and `?block={uuid}` restores it after refresh. QA details, manual-edit state, and glossary controls are auxiliary views over the same owned records.

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
10. Only after in-memory parsing succeeds, one database transaction reconciles stable Section/Block UUIDs. Unchanged rows are updated in place, new rows are inserted, untranslated removed rows are deleted, and translated removed rows are retained as stale history.
11. Debug artifacts are first written as a complete hidden staging directory. Directory promotion replaces the prior `processing/` set; a failed promotion restores the prior complete set. PostgreSQL remains authoritative.

Parse failure sets the Paper status to `FAILED`. A parser failure before replacement leaves an existing complete parse result intact; database persistence is transactional. Parsing, translation, and QA remain synchronous in Phase 4B and do not introduce Celery.

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
- translatability and stale-history flags
- timestamps

Foreign keys cascade from Paper. Reparse never deletes an unchanged stable Block. Removed Blocks with no Translation can be deleted; removed or changed Blocks with Translation history remain in the database as `is_stale=true` and are excluded from active Reader queries. Paper deletion is the explicit destructive boundary and removes all related database rows plus the complete storage subtree.

`Translation` belongs to one Paper and one stable Block, is unique by `(block_id, target_language)`, and stores the source snapshot, current translated text, provider/model, status, aggregate QA status, timestamps, user-modified protection, and failure message. `TranslationVersion` preserves generated and manual-edit snapshots. `TranslationQAResult` stores one named finding per current check. `GlossaryTerm` belongs to a User and optionally an owned Paper. Explicit Paper deletion cascades through Paper-scoped terms and translation tables; parse reconciliation protects translated Blocks from accidental history deletion.

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

- **Reparse reconciliation UI:** removed/changed translated Blocks are safely retained as stale history, but Phase 4B has no UI or automatic semantic mapping for reconciling that history with a new Block UUID.
- **AI beyond translation:** no embedding, retrieval, RAG, or AI chat integration is implemented.
- **Async processing:** Redis is available, but Celery, job queues, progress events, and SSE are not implemented.
- **OCR:** scanned PDFs are detected only; no OCR pipeline is installed.
- **Export and commercial features:** Word export, memberships, plans, and payments remain future work.
