# PaperGPT

PaperGPT Phase 3 provides account authentication, per-user PDF management, a synchronous born-digital document engine, and a PDF.js Reader synchronized with structured document blocks. The backend uses PyMuPDF to retain pages, text blocks, bounding boxes, reading order, columns, and heuristic section structure. Translation, LLMs, RAG, and background jobs are not implemented.

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

Provider API keys remain empty because Phase 3 makes no AI calls.

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

PostgreSQL/pgvector listens on `localhost:5432`; Redis listens on `localhost:6379`. Both use named Docker volumes. Phase 3 parsing remains synchronous and does not use Redis for task execution.

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
| `GET` | `/api/v1/health` | Check API, PostgreSQL, and Redis |

The blocks endpoint supports optional `page`, `section_id`, and `block_type` query filters. Block responses include the block ID, page, type, absolute and normalized bbox, reading order, column, text, section, metadata, and translatability flag.

Ownership is enforced by backend queries. Missing and unowned papers both return `404` from file, parse, outline, and blocks endpoints. The file endpoint returns `application/pdf`, supports the single-range requests used by PDF.js, and never returns a server filesystem path.

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

PostgreSQL `sections` and `blocks` are the formal data source; debug JSON is not used as the database. Reparse replaces prior sections and blocks rather than appending duplicates. Deleting a parsed paper removes both `original/` and `processing/`.

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

`/paper/[id]` is the Phase 3 Reader. It renders the authenticated original PDF through PDF.js beside the ordered structured blocks. The toolbar supports side-by-side, Original, and Structured modes; Bilingual is visibly disabled because Translation is a future phase.

### Reader anchors and synchronization

- Every PDF overlay and structured DOM block uses the persisted Phase 2 Block UUID. Structured nodes use `id="block-{uuid}"` plus `data-block-id`; overlays use `id="pdf-block-{uuid}"` plus the same data attribute.
- Stored PyMuPDF top-left bboxes are normalized against their matching stored page width/height, then scaled to the actual PDF.js viewport width/height. No scroll-percentage position guessing is used.
- Clicking a structured block centers its bbox overlay in the PDF panel. Clicking an overlay centers the matching structured block.
- Normal scrolling selects the visible block closest to the relevant panel's center. A short-lived `pdf`/`document` source lock prevents programmatic scrolling from feeding back into the opposite observer.
- Outline entries come from the existing outline API and jump to the first persisted block in the selected section.
- The active anchor is reflected in `?block={uuid}` and restored after refresh when that block still exists.
- `NOT_STARTED`, `PROCESSING`, `FAILED`, and `COMPLETED` parse states are handled explicitly. Parse/reparse remains synchronous in Phase 3.

The Reader is desktop-first. Narrow viewports stack the outline and reader panels; Original or Structured mode can be used to focus one panel.
