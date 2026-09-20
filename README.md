# PaperGPT

PaperGPT Phase 4A adds a synchronous academic-translation core to the authenticated PDF library, born-digital document engine, and PDF.js Reader. Translations map directly to stable Block UUIDs, preserve version history and protected scientific tokens, and run through a provider abstraction. Phase 4B's polished Chinese/Bilingual Reader, advanced glossary/QA workflows, RAG, chat, and background jobs are not implemented.

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
- `AI_PROVIDER`: `mock` by default, or `openai` for the real provider
- `OPENAI_TRANSLATION_MODEL`: model used only when `AI_PROVIDER=openai`

Local development and all automated tests use the deterministic mock provider and need no API key. To opt into the real provider manually, set `AI_PROVIDER=openai`, `OPENAI_API_KEY`, and `OPENAI_TRANSLATION_MODEL` only in the ignored `.env`; never commit the key.

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

PostgreSQL/pgvector listens on `localhost:5432`; Redis listens on `localhost:6379`. Both use named Docker volumes. Parsing and Phase 4A translation remain synchronous and do not use Redis for task execution.

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
| `GET` | `/api/v1/health` | Check API, PostgreSQL, and Redis |

The blocks endpoint supports optional `page`, `section_id`, and `block_type` query filters. Block responses include the block ID, page, type, absolute and normalized bbox, reading order, column, text, section, metadata, and translatability flag.

Ownership is enforced by backend queries. Missing and unowned papers both return `404` from file, parse, outline, blocks, and translation endpoints. The file endpoint returns `application/pdf`, supports the single-range requests used by PDF.js, and never returns a server filesystem path.

## Academic translation core

Phase 4A translates one persisted Document Block at a time. A request contains the paper title, section title, Block type, previous/current/next translatable text, source/target language, and an empty glossary structure reserved for later work. Only `current_text` is translated; adjacent Blocks are context only.

The default `mock` provider is deterministic and makes no network request. The optional `openai` adapter uses the official Python SDK and Responses API behind the same provider interface. Business services do not import provider SDKs directly.

Automatic translation skips `HEADER`, `FOOTER`, `PAGE_NUMBER`, `REFERENCE`, figure/table body Blocks, equations, and every Block with `is_translatable=false`. Completed and failed records are committed per Block, so one provider failure does not roll back earlier successes. Paper-level responses report `translated_count`, `skipped_count`, and `failed_count`.

Before translation, citations, Figure/Table references, scientific number/unit expressions, selected chemical species, and common statistical symbols are replaced with deterministic placeholders. A translation is accepted only if every placeholder is returned exactly once; otherwise that Block is marked `FAILED`. The original tokens are restored before persistence.

`translations` has one row per `(block_id, target_language)`. Every successful generation appends a `translation_versions` snapshot with an increasing version number. `original_text` is the source snapshot captured when translation begins. A row marked `user_modified=true` is skipped by whole-paper and single-Block automatic translation and is never overwritten without a future explicit force workflow.

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

`/paper/[id]` is the Phase 3 Reader. It renders the authenticated original PDF through PDF.js beside the ordered structured blocks. Phase 4A exposes translations through the API, but the Bilingual control remains disabled because the polished Chinese/Bilingual Reader belongs to Phase 4B.

### Reader anchors and synchronization

- Every PDF overlay and structured DOM block uses the persisted Phase 2 Block UUID. Structured nodes use `id="block-{uuid}"` plus `data-block-id`; overlays use `id="pdf-block-{uuid}"` plus the same data attribute.
- Stored PyMuPDF top-left bboxes are normalized against their matching stored page width/height, then scaled to the actual PDF.js viewport width/height. No scroll-percentage position guessing is used.
- Clicking a structured block centers its bbox overlay in the PDF panel. Clicking an overlay centers the matching structured block.
- Normal scrolling selects the visible block closest to the relevant panel's center. A short-lived `pdf`/`document` source lock prevents programmatic scrolling from feeding back into the opposite observer.
- Outline entries come from the existing outline API and jump to the first persisted block in the selected section.
- The active anchor is reflected in `?block={uuid}` and restored after refresh when that block still exists.
- `NOT_STARTED`, `PROCESSING`, `FAILED`, and `COMPLETED` parse states are handled explicitly. Parse/reparse remains synchronous in Phase 3.

The Reader is desktop-first. Narrow viewports stack the outline and reader panels; Original or Structured mode can be used to focus one panel.
