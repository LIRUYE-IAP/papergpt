import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.glossary import GlossaryScope
from app.models.user import User
from app.schemas.glossary import (
    GlossaryTermCreate,
    GlossaryTermResponse,
    GlossaryTermUpdate,
)
from app.services.glossary import (
    GlossaryServiceError,
    create_glossary_term,
    delete_glossary_term,
    list_paper_glossary,
    list_user_glossary,
    update_glossary_term,
)

router = APIRouter(tags=["glossary"])


def _raise_service_error(exc: GlossaryServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/glossary", response_model=list[GlossaryTermResponse])
def glossary_terms(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    scope: Annotated[GlossaryScope | None, Query()] = None,
) -> list[GlossaryTermResponse]:
    return [
        GlossaryTermResponse.model_validate(term)
        for term in list_user_glossary(db, current_user, scope=scope)
    ]


@router.post(
    "/glossary",
    response_model=GlossaryTermResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_glossary_term(
    payload: GlossaryTermCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> GlossaryTermResponse:
    try:
        term = create_glossary_term(db, current_user, payload)
    except GlossaryServiceError as exc:
        _raise_service_error(exc)
    return GlossaryTermResponse.model_validate(term)


@router.patch("/glossary/{term_id}", response_model=GlossaryTermResponse)
def edit_glossary_term(
    term_id: uuid.UUID,
    payload: GlossaryTermUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> GlossaryTermResponse:
    try:
        term = update_glossary_term(db, current_user, term_id, payload)
    except GlossaryServiceError as exc:
        _raise_service_error(exc)
    if term is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Term not found")
    return GlossaryTermResponse.model_validate(term)


@router.delete("/glossary/{term_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_glossary_term(
    term_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    if not delete_glossary_term(db, current_user, term_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Term not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/papers/{paper_id}/glossary",
    response_model=list[GlossaryTermResponse],
)
def paper_glossary_terms(
    paper_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[GlossaryTermResponse]:
    terms = list_paper_glossary(db, current_user, paper_id)
    if terms is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    return [GlossaryTermResponse.model_validate(term) for term in terms]
