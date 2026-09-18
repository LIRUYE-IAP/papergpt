# PaperGPT Architecture

## Current system — Phase 1

PaperGPT is a modular monolith with an independently runnable Next.js frontend and FastAPI backend.

| Layer | Technology | Current responsibility |
| --- | --- | --- |
| Frontend | Next.js App Router | Registration, login, library, upload, detail, and delete UI |
| Backend | FastAPI | Versioned Auth, Paper, and health APIs |
| Persistence | SQLAlchemy 2 + Alembic | User/Paper models and versioned schema changes |
| Database | PostgreSQL + pgvector | Account and paper metadata; vector extension reserved for later phases |
| Cache foundation | Redis | Connectivity only; no background tasks in Phase 1 |
| File storage | Local filesystem abstraction | Original PDF storage under system-generated object keys |

## Authentication and isolation

- Passwords are hashed with pwdlib's recommended Argon2 implementation and are never returned by the API.
- FastAPI issues HS256 JWT bearer tokens containing `sub` and `exp`; the signing secret comes only from the root `.env`.
- Paper queries always include the authenticated user ID. Detail and delete return the same not-found response for missing and unowned records.
- The frontend uses a deliberately small client-side token strategy based on `localStorage`; no global state library is introduced in Phase 1.
- CORS accepts only the configured `FRONTEND_ORIGIN`, never `*`.

## Upload and storage flow

1. The API validates authentication, `.pdf` extension, `application/pdf` content type, non-empty content, and the configured size limit.
2. The file is streamed in bounded chunks while calculating SHA-256.
3. Local storage writes to a temporary file and atomically moves it to `papers/{user_id}/{paper_id}/original/original.pdf`.
4. PostgreSQL stores the generated object key, hash, size, display filename, and Phase 1 statuses.
5. A database failure removes the newly written file. Deletion stages the file before committing the database delete and restores it if the transaction fails.

## Backend boundaries

- `api/` owns HTTP transport, versioning, and authentication dependencies.
- `core/` owns environment-based configuration.
- `db/` owns SQLAlchemy base, engine, and sessions.
- `models/` owns persisted entities and relationships.
- `schemas/` owns API contracts.
- `services/` owns authentication, paper workflows, and storage abstractions.
- Alembic is the only supported schema-change mechanism.

## Future only — not implemented

- **Document engine:** PDF parsing, OCR, blocks, and sections.
- **Async processing:** Redis + Celery tasks and progress delivery.
- **Storage:** an S3-compatible implementation behind the storage abstraction.
- **AI:** provider abstraction, translation, embeddings, RAG, and chat.
- **Product:** notes, glossary, Word export, membership, plans, and payments.
