import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.paper import Paper
from app.models.user import User
from app.services.storage import EmptyFileError, FileTooLargeError, LocalStorage


class PaperUploadError(ValueError):
    def __init__(self, detail: str, status_code: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _display_filename(upload: UploadFile) -> str:
    filename = Path(upload.filename or "").name.strip()
    return filename[:512] or "document.pdf"


async def create_paper(
    db: Session,
    current_user: User,
    upload: UploadFile,
    storage: LocalStorage,
) -> Paper:
    original_filename = _display_filename(upload)
    if Path(original_filename).suffix.lower() != ".pdf":
        raise PaperUploadError("Only .pdf files are accepted", 415)
    if (upload.content_type or "").lower() != "application/pdf":
        raise PaperUploadError("Content-Type must be application/pdf", 415)

    signature = await upload.read(5)
    await upload.seek(0)
    if not signature:
        raise PaperUploadError("The PDF file must not be empty", 400)
    if signature != b"%PDF-":
        raise PaperUploadError("File content does not have a valid PDF signature", 415)

    paper_id = uuid.uuid4()
    try:
        stored = await storage.save_pdf(
            upload,
            user_id=current_user.id,
            paper_id=paper_id,
            max_bytes=settings.max_pdf_upload_mb * 1024 * 1024,
        )
    except EmptyFileError as exc:
        raise PaperUploadError("The PDF file must not be empty", 400) from exc
    except FileTooLargeError as exc:
        raise PaperUploadError(
            f"The PDF file exceeds the {settings.max_pdf_upload_mb} MB limit", 413
        ) from exc

    paper = Paper(
        id=paper_id,
        user_id=current_user.id,
        filename="original.pdf",
        original_filename=original_filename,
        file_size=stored.file_size,
        file_key=stored.file_key,
        file_hash=stored.file_hash,
        document_type="pdf",
        source_language=None,
        target_language="zh",
        parse_status="NOT_STARTED",
        translation_status="NOT_STARTED",
        qa_status="PENDING",
    )
    db.add(paper)
    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.delete_file(stored.file_key)
        raise
    db.refresh(paper)
    return paper


def list_papers(db: Session, current_user: User) -> list[Paper]:
    ordering = func.coalesce(Paper.last_opened_at, Paper.created_at).desc()
    return list(
        db.scalars(
            select(Paper).where(Paper.user_id == current_user.id).order_by(ordering)
        )
    )


def get_owned_paper(db: Session, current_user: User, paper_id: uuid.UUID) -> Paper | None:
    return db.scalar(
        select(Paper).where(
            Paper.id == paper_id,
            Paper.user_id == current_user.id,
        )
    )


def open_paper(db: Session, current_user: User, paper_id: uuid.UUID) -> Paper | None:
    paper = get_owned_paper(db, current_user, paper_id)
    if paper is None:
        return None
    paper.last_opened_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(paper)
    return paper


def delete_paper(
    db: Session,
    current_user: User,
    paper_id: uuid.UUID,
    storage: LocalStorage,
) -> bool:
    paper = get_owned_paper(db, current_user, paper_id)
    if paper is None:
        return False

    staged_paper = storage.stage_delete_paper(paper.file_key)
    try:
        db.delete(paper)
        db.commit()
    except Exception:
        db.rollback()
        if staged_paper is not None:
            storage.restore_staged_paper(*staged_paper)
        raise

    if staged_paper is not None:
        storage.delete_tree(staged_paper[0])
    return True
