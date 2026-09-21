# PaperGPT

PaperGPT Phase 4C-1 hardens the Phase 4B reading workflow for real OpenAI failures. Provider errors are normalized into a stable HTTP contract, failed translations cannot remain stuck in `PROCESSING`, and the Reader always releases block/paper loading state with a readable error and manual Retry action. Translation quality/prompt work, RAG, chat, and background jobs are not implemented.

## Prerequisites

- `uv` for the project-local Python 3.12 runtime and `.venv`
- Node.js and npm
- Docker with Docker Compose

## Environment

From the project root:

```powershell
Copy-Item .env.example .env
```

Replace the local database password in both `POSTGRES_PASSWORD` and `DATABASE_URL`, and replace `SECRET_KEY` with a random local secret. Do not commit `.env`.

Important local settings include:

- `JWT_EXPIRATION_MINUTES`: access-token lifetime
- `MAX_PDF_UPLOAD_MB`: PDF upload limit
- `FRONTEND_ORIGIN`: the allowed browser origin for CORS
- `STORAGE_ROOT`: local original-PDF and processing-artifact root
- `AI_PROVIDER`: `mock` by default, or `openai` for the real provider adapter
- `OPENAI_API_KEY`: required only when `AI_PROVIDER=openai`; keep it exclusively in the ignored root `.env`

Automated tests force the deterministic mock provider and remove the key from the test settings object, regardless of local `.env`, so pytest performs zero OpenAI network requests. The real OpenAI adapter has an explicit 60-second request timeout and disables SDK automatic retries; users retry manually after a surfaced error.

## Backend environment

The root `.venv` is the only supported backend development environment. The optional `.python/` directory is a uv-managed local Python runtime, not project source code and not a second backend environment.

Run from the project root in PowerShell:

```powershell
$env:UV_PYTHON_INSTALL_DIR = Join-Path (Get-Location) ".python"
$env:UV_CACHE_DIR = Join-Path (Get-Location) ".uv-cache"
uv python install 3.12 --no-bin --no-registry
if (-not (Test-Path .\.venv\Scripts\python.exe)) { uv venv --python 3.12 .venv }
uv pip install --python .\.venv\Scripts\python.exe -e ".\backend[dev]"
.\.venv\Scripts\python.exe --version
```

The backend dependency set includes PyMuPDF for born-digital PDF layout extraction. No OCR package is installed.

## Infrastructure and migration

From the project root:

```powershell
docker compose up -d --wait
docker compose ps
Set-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m alembic current
..\.venv\Scripts\python.exe -m alembic check
```

PostgreSQL/pgvector listens on `localhost:5432`; Redis listens on `localhost:6379`. Both use named Docker volumes. Parsing, translation, and deterministic QA remain synchronous and do not use Redis for task execution.

## FastAPI and tests

From `backend/`:

```powershell
..\.venv\Scripts\python.exe -m pytest
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

## API

All paper and document endpoints require `Authorization: Bearer <access_token>`.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/auth/register` | Create an account |
| `POST` | `/api/v1/auth/login` | Return a JWT access token |
| `GET` | `/api/v1/auth/me` | Return the authenticated user |
| `POST` | `/api/v1/papers` | Upload one PDF as multipart field `file` |
| `GET` | `/api/v1/papers` | List the current user's papers |
| `GET` | `/api/v1/papers/{paper_id}` | Read an owned paper's metadata |
| `GET` | `/api/v1/papers/{paper_id}/file` | Stream an owned PDF to PDF.js, including single byte ranges |
| `DELETE` | `/api/v1/papers/{paper_id}` | Delete an owned paper and all stored artifacts |
| `POST` | `/api/v1/papers/{paper_id}/parse` | Synchronously parse an owned PDF |
| `GET` | `/api/v1/papers/{paper_id}/outline` | Return the nested section outline |
| `GET` | `/api/v1/papers/{paper_id}/blocks` | Return ordered blocks and layout debug data |
| `POST` | `/api/v1/papers/{paper_id}/translate` | Translate eligible Blocks into `target_language` |
| `GET` | `/api/v1/papers/{paper_id}/translations` | Return Block-linked translations with optional language/page/section filters |
| `POST` | `/api/v1/papers/{paper_id}/blocks/{block_id}/translate` | Translate or retranslate one owned Block |
| `PATCH` | `/api/v1/papers/{paper_id}/translations/{translation_id}` | Save a manual edit and append a version |
| `GET` | `/api/v1/papers/{paper_id}/translations/{translation_id}/versions` | List immutable translation history |
| `GET/POST` | `/api/v1/papers/{paper_id}/translations/{translation_id}/qa` | Read or deterministically rerun QA |
| `GET/POST` | `/api/v1/glossary` | List or create owned global/paper terms |
| `PATCH/DELETE` | `/api/v1/glossary/{term_id}` | Update or delete one owned term |
| `GET` | `/api/v1/papers/{paper_id}/glossary` | List global and Paper terms applicable to an owned Paper |
| `GET` | `/api/v1/health` | Check API, PostgreSQL, and Redis |

The blocks endpoint supports optional `page`, `section_id`, and `block_type` query filters. Block responses include the block ID, page, type, absolute and normalized bbox, reading order, column, text, section, metadata, and translatability flag.

Ownership is enforced by backend queries. Missing and unowned papers both return `404` from file, parse, outline, blocks, and translation endpoints. The file endpoint returns `application/pdf`, supports the single-range requests used by PDF.js, and never returns a server filesystem path.

## Academic translation core

Phase 4B still translates one persisted Document Block at a time. A request contains the paper title, section title, Block type, previous/current/next translatable text, source/target language, and only the enabled glossary terms that actually match that local context. Only `current_text` is translated; adjacent Blocks are context only.

The default `mock` provider is deterministic and makes no network request. The optional `openai` adapter uses the official Python SDK and Responses API behind the same provider interface. Business services do not import provider SDKs directly.

Automatic translation skips `HEADER`, `FOOTER`, `PAGE_NUMBER`, `REFERENCE`, figure/table body Blocks, equations, and every Block with `is_translatable=false`. Completed and failed records are committed per Block, so one provider failure does not roll back earlier successes. Paper-level responses report `translated_count`, `skipped_count`, and `failed_count`.

Before translation, citations, Figure/Table references, scientific number/unit expressions, selected chemical species, and common statistical symbols are replaced with deterministic placeholders. A translation is accepted only if every placeholder is returned exactly once; otherwise that Block is marked `FAILED`. The original tokens are restored before persistence.

`translations` has one row per `(block_id, target_language)`. Every successful generation appends a `translation_versions` snapshot with an increasing version number. `original_text` is the source snapshot captured when translation begins. A row marked `user_modified=true` is skipped by whole-paper and single-Block automatic translation and is never overwritten without a future explicit force workflow.

### Real-provider failure contract

The OpenAI adapter converts SDK exceptions before they leave the provider boundary. API responses use a stable envelope:

```json
{
  "error": {
    "code": "AI_RATE_LIMITED",
    "message": "Translation service rate limit reached.",
    "retry_after_seconds": 120,
    "partial_result": null
  }
}
```

Supported codes are `AI_RATE_LIMITED`, `AI_AUTHENTICATION_FAILED`, `AI_PERMISSION_DENIED`, `AI_INVALID_REQUEST`, `AI_MODEL_UNAVAILABLE`, `AI_TIMEOUT`, `AI_CONNECTION_FAILED`, `AI_SERVICE_UNAVAILABLE`, and `TRANSLATION_FAILED`. Provider authentication failures are server-side `502` responses, not PaperGPT-user `401` responses, so they never log out the current user.

A failed provider call is transactionally persisted as `Translation.status=FAILED` with a short safe message; SDK response bodies, request headers, credentials, organization identifiers, and source PDF text are not stored or logged. A successful manual Retry changes the row to `COMPLETED` and clears `error_message`.

Whole-paper translation stops immediately on provider-wide rate-limit, authentication, permission, model, timeout, connection, or availability failures. Its error envelope includes completed/skipped/failed/remaining partial counts. Already completed Blocks remain committed, the current failed Block is `FAILED`, and unattempted Blocks are not falsely marked failed. There is no automatic retry loop.

### Glossary, editing, and deterministic QA

Glossary scope precedence is:

```text
PAPER > USER_GLOBAL > future DOMAIN/AUTO > MODEL
```

Paper terms belong to an owned Paper; global terms belong only to their user. Matching respects `case_sensitive`, English word boundaries, and longest non-overlapping phrases. A Paper-level conflict overrides its global equivalent. Terms constrain the prompt and are never used to rewrite source text before translation.

Manual edits require non-empty text, set `user_modified=true`, append a monotonic `USER_EDIT` TranslationVersion, and immediately replace the translation's deterministic QA results. QA stores individual findings—not a fabricated numeric score—for completeness, numbers, units, citations, Figure/Table references, selected chemical species, statistical expressions, glossary compliance, uncertainty markers, placeholder residue, and suspicious output. Aggregation is deterministic: any failure gives `FAILED`; otherwise any warning gives `WARNING`; otherwise `PASSED`; not-yet-run is `PENDING`. A rerun replaces the prior result set rather than accumulating duplicates.

Reparse reconciles stable UUIDs instead of deleting every Block. Unchanged Blocks are updated in place, so Translation IDs, version IDs, source snapshots, translated text, and `user_modified` state survive. A newly parsed Block is inserted. A removed Block without translations is deleted; one with translation history is retained as `is_stale=true`, excluded from active Reader/translation queries, and kept with its Translation and TranslationVersion rows for future manual reconciliation.

## PDF validation and storage

Uploads are checked for:

- `.pdf` extension
- `application/pdf` content type
- non-empty content
- configured size limit
- leading `%PDF-` signature

Original files are streamed to a system-generated key while calculating SHA-256:

```text
storage/papers/{user_id}/{paper_id}/original/original.pdf
```

Successful parsing also writes inspectable artifacts:

```text
storage/papers/{user_id}/{paper_id}/processing/raw_pdf_blocks.json
storage/papers/{user_id}/{paper_id}/processing/layout.json
storage/papers/{user_id}/{paper_id}/processing/document.json
```

PostgreSQL `sections` and `blocks` are the formal data source; debug JSON is not used as the database. Reparse reconciles prior sections and blocks rather than appending duplicates or deleting stable translated Blocks. Deleting a parsed paper removes both `original/` and `processing/`.

Block and Section IDs are deterministic UUIDv5 values derived from the Paper ID, parser version, and canonical parsed identity. Repeating a parse with the same PDF and parser version preserves Block IDs across PostgreSQL, the blocks API, and `document.json`.

## Document engine scope

The current heuristic pipeline is:

```text
PDF pages
→ PyMuPDF spans and text/image blocks
→ coordinate normalization
→ repeated header/footer/page-number detection
→ block classification
→ column detection
→ paragraph reconstruction
→ column-aware reading order
→ section-tree construction
→ transactional persistence
→ debug JSON
```

Supported block types include titles, authors, affiliations, abstracts, keywords, three heading levels, paragraphs, figures and captions, tables and captions, equations, footnotes, references, headers, footers, and page numbers. Classification is heuristic and does not claim perfect handling of every publisher layout.

Scanned/image-only documents are detected in debug metadata as `is_scanned`; Phase 2 does not run OCR.

### Coordinates

Page width, page height, and extracted bbox values all come from the same PyMuPDF `text-dict` coordinate space. Persisted block metadata includes the matching page dimensions, while each debug page records its page number, rotation, crop box, and coordinate-system label. Absolute bboxes are clamped to the page and zero-area blocks are not persisted.

The current baseline is validated for ordinary unrotated born-digital academic PDFs. Rotation and crop-box metadata are retained, but unusual rotated/cropped-page combinations are not yet normalized with explicit rotation matrices and require manual acceptance review.

## Real-world PDF acceptance checklist

Do not add a third-party or unknown-copyright paper to Git. Use a locally supplied, authorized PDF and manually inspect the outline/blocks APIs and debug JSON for:

- title classification and bbox alignment
- abstract classification and reading position
- numbered and unnumbered headings
- full-page double-column order: left column before right column
- column-local headings remaining inside their own column flow
- figure-caption classification
- table-caption classification
- References heading and non-translatable reference entries
- repeated header, footer, and page-number classification
- absolute bbox alignment against the source page
- normalized bbox bounds and matching page width/height

The programmatically generated three-page academic fixture remains the automated regression baseline and contains no third-party paper content.

## Frontend

The frontend defaults to `http://localhost:8000/api/v1`. To override it, copy `frontend/.env.example` to `frontend/.env.local` and change `NEXT_PUBLIC_API_BASE_URL`.

From the project root in another terminal:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

Production verification:

```powershell
npm.cmd run lint
npm.cmd run build
```

Implemented pages remain:

- `/register`
- `/login`
- `/library`
- `/paper/[id]`

`/paper/[id]` is the Phase 4B Reader. It renders the authenticated original PDF through PDF.js and provides Original, Structured, Chinese, and Bilingual reading modes. It also exposes Translate Paper, Translate Block, plain-text manual editing, deterministic QA details, and a minimal Paper/global Glossary manager.

Phase 4C-1 adds per-Block translating state, readable Chinese provider errors, failed-state Retry controls, bounded frontend requests, and whole-paper partial-failure notices. Every success, HTTP error, network failure, malformed error body, or timeout exits loading state through `finally`; one Block's request no longer locks unrelated Block controls.

### Reader anchors and synchronization

- Every PDF overlay and Original/Chinese/Bilingual DOM block uses the persisted Phase 2 Block UUID. Reader nodes use `id="block-{uuid}"` plus `data-block-id`; overlays use `id="pdf-block-{uuid}"` plus the same data attribute. `Translation.block_id` is the same UUID.
- Stored PyMuPDF top-left bboxes are normalized against their matching stored page width/height, then scaled to the actual PDF.js viewport width/height. No scroll-percentage position guessing is used.
- Clicking a structured block centers its bbox overlay in the PDF panel. Clicking an overlay centers the matching structured block.
- Normal scrolling selects the visible block closest to the relevant panel's center. A short-lived `pdf`/`document` source lock prevents programmatic scrolling from feeding back into the opposite observer.
- Outline entries come from the existing outline API and jump to the first persisted block in the selected section.
- The active anchor is reflected in `?block={uuid}` and restored after refresh when that block still exists. Mode switches preserve the single parent-owned `activeBlockId` and recenter both panels.
- `NOT_STARTED`, `PROCESSING`, `FAILED`, and `COMPLETED` parse states are handled explicitly. Parse/reparse remains synchronous in Phase 3.

Only active Blocks and their translations appear in the current Reader. Stale translated history remains preserved in PostgreSQL after changed reparses but is deliberately excluded from Reader, translation, QA, editing, and version endpoints. Paper glossary terms survive reparse because they belong to the Paper, not a Block.

The Reader is desktop-first. Narrow viewports stack the outline and reader panels; Original or Structured mode can be used to focus one panel.
