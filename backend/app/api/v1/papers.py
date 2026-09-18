import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.paper import PaperResponse
from app.services.papers import (
    PaperUploadError,
    create_paper,
    delete_paper,
    list_papers,
    open_paper,
)
from app.services.storage import LocalStorage

router = APIRouter(prefix="/papers", tags=["papers"])


@router.post("", response_model=PaperResponse, status_code=status.HTTP_201_CREATED)
async def upload_paper(
    file: Annotated[UploadFile, File()],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PaperResponse:
    try:
        paper = await create_paper(
            db,
            current_user,
            file,
            LocalStorage(settings.storage_root),
        )
    except PaperUploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    finally:
        await file.close()
    return PaperResponse.model_validate(paper)


@router.get("", response_model=list[PaperResponse])
def papers(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[PaperResponse]:
    return [PaperResponse.model_validate(paper) for paper in list_papers(db, current_user)]


@router.get("/{paper_id}", response_model=PaperResponse)
def paper_detail(
    paper_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PaperResponse:
    paper = open_paper(db, current_user, paper_id)
    if paper is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    return PaperResponse.model_validate(paper)


@router.delete("/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_paper(
    paper_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    deleted = delete_paper(
        db,
        current_user,
        paper_id,
        LocalStorage(settings.storage_root),
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
