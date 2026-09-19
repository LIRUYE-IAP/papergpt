import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.models.document import BlockType
from app.schemas.document import (
    BlockResponse,
    ParseResponse,
    SectionOutlineResponse,
    SectionResponse,
)
from app.schemas.paper import PaperResponse
from app.services.documents import (
    PaperParseError,
    list_owned_blocks,
    list_owned_sections,
    parse_owned_paper,
)
from app.services.papers import (
    PaperUploadError,
    create_paper,
    delete_paper,
    list_papers,
    open_paper,
)
from app.services.storage import LocalStorage

router = APIRouter(prefix="/papers", tags=["papers"])


def _outline_response(sections: list) -> list[SectionOutlineResponse]:
    nodes = {
        section.id: SectionOutlineResponse(
            **SectionResponse.model_validate(section).model_dump(),
            children=[],
        )
        for section in sections
    }
    roots: list[SectionOutlineResponse] = []
    for section in sections:
        node = nodes[section.id]
        if section.parent_id is not None and section.parent_id in nodes:
            nodes[section.parent_id].children.append(node)
        else:
            roots.append(node)
    return roots


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


@router.post("/{paper_id}/parse", response_model=ParseResponse)
def parse_document(
    paper_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ParseResponse:
    try:
        result = parse_owned_paper(
            db,
            current_user,
            paper_id,
            LocalStorage(settings.storage_root),
        )
    except PaperParseError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    return ParseResponse(
        paper_id=result.paper_id,
        parse_status="COMPLETED",
        page_count=result.page_count,
        section_count=result.section_count,
        block_count=result.block_count,
        is_scanned=result.is_scanned,
    )


@router.get("/{paper_id}/outline", response_model=list[SectionOutlineResponse])
def paper_outline(
    paper_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[SectionOutlineResponse]:
    sections = list_owned_sections(db, current_user, paper_id)
    if sections is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    return _outline_response(sections)


@router.get("/{paper_id}/blocks", response_model=list[BlockResponse])
def paper_blocks(
    paper_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[int | None, Query(ge=1)] = None,
    section_id: uuid.UUID | None = None,
    block_type: BlockType | None = None,
) -> list[BlockResponse]:
    blocks = list_owned_blocks(
        db,
        current_user,
        paper_id,
        page=page,
        section_id=section_id,
        block_type=block_type,
    )
    if blocks is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    return [BlockResponse.model_validate(block) for block in blocks]


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
