import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.api.deps import get_current_user
from app.ai.factory import ProviderConfigurationError
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
from app.schemas.translation import (
    BlockTranslationRunResponse,
    TranslationRequestPayload,
    TranslationResponse,
    TranslationRunResponse,
)
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
    get_owned_paper,
    list_papers,
    open_paper,
)
from app.services.paper_files import RangeNotSatisfiable, iter_file_bytes, parse_byte_range
from app.services.storage import LocalStorage
from app.services.translations import (
    TranslationServiceError,
    list_owned_translations,
    translate_owned_block,
    translate_owned_paper,
)

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


@router.post("/{paper_id}/translate", response_model=TranslationRunResponse)
def translate_paper(
    paper_id: uuid.UUID,
    payload: TranslationRequestPayload,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> TranslationRunResponse:
    try:
        result = translate_owned_paper(
            db,
            current_user,
            paper_id,
            payload.target_language,
        )
    except TranslationServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except ProviderConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    return TranslationRunResponse.model_validate(result)


@router.get("/{paper_id}/translations", response_model=list[TranslationResponse])
def paper_translations(
    paper_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    target_language: Annotated[str | None, Query(min_length=2, max_length=32)] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    section_id: uuid.UUID | None = None,
) -> list[TranslationResponse]:
    try:
        translations = list_owned_translations(
            db,
            current_user,
            paper_id,
            target_language=target_language,
            page=page,
            section_id=section_id,
        )
    except TranslationServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    if translations is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    return [TranslationResponse.model_validate(item) for item in translations]


@router.post(
    "/{paper_id}/blocks/{block_id}/translate",
    response_model=BlockTranslationRunResponse,
)
def translate_block(
    paper_id: uuid.UUID,
    block_id: uuid.UUID,
    payload: TranslationRequestPayload,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> BlockTranslationRunResponse:
    try:
        result = translate_owned_block(
            db,
            current_user,
            paper_id,
            block_id,
            payload.target_language,
        )
    except TranslationServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except ProviderConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paper or block not found",
        )
    return BlockTranslationRunResponse.model_validate(result)


@router.get("/{paper_id}/file")
def paper_file(
    paper_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    range_header: Annotated[str | None, Header(alias="Range")] = None,
) -> StreamingResponse:
    paper = get_owned_paper(db, current_user, paper_id)
    if paper is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")

    file_path = LocalStorage(settings.storage_root).path_for_key(paper.file_key)
    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper file not found")

    file_size = file_path.stat().st_size
    encoded_filename = quote(paper.original_filename, safe="")
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f"inline; filename*=UTF-8''{encoded_filename}",
    }

    if range_header is None:
        headers["Content-Length"] = str(file_size)
        return StreamingResponse(
            iter_file_bytes(file_path),
            media_type="application/pdf",
            headers=headers,
        )

    try:
        byte_range = parse_byte_range(range_header, file_size)
    except RangeNotSatisfiable as exc:
        raise HTTPException(
            status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
            detail="Requested range is not satisfiable",
            headers={
                "Accept-Ranges": "bytes",
                "Content-Range": f"bytes */{file_size}",
            },
        ) from exc

    headers.update(
        {
            "Content-Length": str(byte_range.length),
            "Content-Range": byte_range.content_range,
        }
    )
    return StreamingResponse(
        iter_file_bytes(
            file_path,
            start=byte_range.start,
            length=byte_range.length,
        ),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type="application/pdf",
        headers=headers,
    )


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
