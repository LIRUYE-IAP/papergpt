# PaperGPT

PaperGPT currently contains a Next.js frontend and a FastAPI backend foundation. Phase 0 provides local PostgreSQL/pgvector and Redis infrastructure, initial database models and migration, and health checks. It does not implement product workflows or AI calls.

## Prerequisites

- `uv` (manages the project's Python 3.12 runtime and virtual environment)
- Node.js and npm
- Docker with Docker Compose

## Environment configuration

From the project root, create a local environment file without committing it:

```powershell
Copy-Item .env.example .env
```

The values in `.env.example` are local-development placeholders. Before first startup, set `POSTGRES_PASSWORD`, update the matching password inside `DATABASE_URL`, and replace `SECRET_KEY` in `.env`. Keep real secrets only in `.env` or an external secret manager. The `.env` file is ignored by Git.

## Backend Python environment

The root `.venv` is the only supported backend development environment. Do not install PaperGPT dependencies into a Conda environment or a global Python installation.

Run the following from the project root in PowerShell. The conditional command creates `.venv` when it is missing; the final command installs or restores all backend and test dependencies in that same environment:

```powershell
$env:UV_PYTHON_INSTALL_DIR = Join-Path (Get-Location) ".python"
$env:UV_CACHE_DIR = Join-Path (Get-Location) ".uv-cache"
uv python install 3.12 --no-bin --no-registry
if (-not (Test-Path .\.venv\Scripts\python.exe)) { uv venv --python 3.12 .venv }
uv pip install --python .\.venv\Scripts\python.exe -e ".\backend[dev]"
.\.venv\Scripts\python.exe --version
```

The expected version is Python 3.12. The `.python/` directory is an optional uv-managed local Python runtime used to create `.venv`; it is ignored local tooling, not project source code and not the backend environment itself. Backend commands must use `.venv\Scripts\python.exe`.

## Infrastructure

From the project root:

```powershell
docker compose up -d
docker compose ps
```

PostgreSQL is exposed on `localhost:5432`, Redis on `localhost:6379`, and their data is retained in named Docker volumes.

## Database migration

From the project root:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m alembic current
```

## Backend tests

From `backend/`:

```powershell
..\.venv\Scripts\python.exe -m pytest
```

## FastAPI

From `backend/`:

```powershell
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The API documentation is available at `http://127.0.0.1:8000/docs`. In another terminal, verify the health endpoint:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

## Frontend

From the project root in another terminal:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

Create a production build with:

```powershell
npm.cmd run build
```

The frontend remains the existing Next.js application and was not regenerated in Phase 0. Use `npm.cmd` in Windows PowerShell so the commands do not depend on PowerShell script-execution policy.
