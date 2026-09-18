# PaperGPT

PaperGPT Phase 1 provides account registration and login, authenticated PDF upload, a per-user paper library, basic paper details, and deletion from both PostgreSQL and local storage. PDF parsing, translation, AI, RAG, background jobs, exports, and commercial features are not implemented.

## Prerequisites

- `uv` for the project-local Python 3.12 runtime and `.venv`
- Node.js and npm
- Docker with Docker Compose

## Environment

From the project root:

```powershell
Copy-Item .env.example .env
```

Replace the local database password in both `POSTGRES_PASSWORD` and `DATABASE_URL`, and replace `SECRET_KEY` with a random local secret. Do not commit `.env`. Phase 1 also uses:

- `JWT_EXPIRATION_MINUTES`: access-token lifetime
- `MAX_PDF_UPLOAD_MB`: PDF upload limit
- `FRONTEND_ORIGIN`: the single allowed browser origin for CORS
- `STORAGE_ROOT`: local file-storage root

Provider API keys remain empty because Phase 1 makes no AI calls.

## Backend environment

The root `.venv` is the only supported backend development environment. The optional `.python/` directory is uv-managed local tooling, not source code and not the backend environment.

Run from the project root in PowerShell:

```powershell
$env:UV_PYTHON_INSTALL_DIR = Join-Path (Get-Location) ".python"
$env:UV_CACHE_DIR = Join-Path (Get-Location) ".uv-cache"
uv python install 3.12 --no-bin --no-registry
if (-not (Test-Path .\.venv\Scripts\python.exe)) { uv venv --python 3.12 .venv }
uv pip install --python .\.venv\Scripts\python.exe -e ".\backend[dev]"
.\.venv\Scripts\python.exe --version
```

## Infrastructure and migration

From the project root:

```powershell
docker compose up -d --wait
docker compose ps
Set-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m alembic current
```

PostgreSQL/pgvector listens on `localhost:5432`; Redis listens on `localhost:6379`. Both use named Docker volumes.

## FastAPI and tests

From `backend/`:

```powershell
..\.venv\Scripts\python.exe -m pytest
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

## Phase 1 API

All paper endpoints require `Authorization: Bearer <access_token>`.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/auth/register` | Create an account |
| `POST` | `/api/v1/auth/login` | Return a JWT access token |
| `GET` | `/api/v1/auth/me` | Return the authenticated user |
| `POST` | `/api/v1/papers` | Upload one PDF as multipart field `file` |
| `GET` | `/api/v1/papers` | List the current user's papers |
| `GET` | `/api/v1/papers/{paper_id}` | Read an owned paper's metadata |
| `DELETE` | `/api/v1/papers/{paper_id}` | Delete an owned paper and stored file |
| `GET` | `/api/v1/health` | Check API, PostgreSQL, and Redis |

Passwords are Argon2 hashes. JWTs contain the user ID in `sub` and an `exp` claim. Ownership is enforced by backend queries; an unowned paper is returned as not found.

Uploaded files are streamed to a system-generated key:

```text
storage/papers/{user_id}/{paper_id}/original/original.pdf
```

Only the object key and metadata are stored in PostgreSQL. The browser-provided filename is retained only as `original_filename` for display.

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
npm.cmd run build
```

Implemented pages:

- `/register`
- `/login`
- `/library`
- `/paper/[id]`

The Phase 1 browser client stores its bearer token in `localStorage`. No PDF reader, parser, translation progress, or AI experience is present yet.
