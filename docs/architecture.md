# PaperGPT Architecture

## Phase 0 system shape

PaperGPT starts as a modular monolith with independently runnable frontend and backend applications. Phase 0 establishes infrastructure and data foundations only; it contains no authentication, document-processing, translation, retrieval, chat, billing, or payment workflows.

| Layer | Technology | Current responsibility |
| --- | --- | --- |
| Frontend | Next.js | Existing web application shell |
| Backend | FastAPI | Versioned HTTP API and health checks |
| Database | PostgreSQL + pgvector | Relational persistence and future vector support |
| Cache / broker | Redis | Connectivity foundation; no background jobs yet |

## Backend boundaries

- `api/` owns HTTP routing and versioning.
- `core/` owns environment-based configuration.
- `db/` owns SQLAlchemy base, engine, and sessions.
- `models/` owns persisted entities and relationships.
- `schemas/` owns API request and response contracts.
- `services/` owns application and infrastructure checks outside the transport layer.
- Alembic is the only supported mechanism for database schema changes.

## Future abstractions

- **Async future:** Redis + Celery. Celery is intentionally not installed or configured in Phase 0.
- **Storage future:** an S3-compatible storage abstraction. Local `storage/` is only a development placeholder.
- **AI future:** a provider abstraction capable of supporting multiple model vendors. Provider keys are reserved in configuration, but no provider SDK or AI call exists in Phase 0.

## Data foundation

`User` owns zero or more `Paper` records. Deleting a user cascades to that user's papers. PostgreSQL stores paper metadata in conventional columns and author metadata in JSONB. The `vector` extension is enabled for later phases, but no embedding column or retrieval behavior is introduced yet.
