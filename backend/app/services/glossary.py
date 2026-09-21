from __future__ import annotations

from dataclasses import dataclass
import re
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.glossary import GlossaryScope, GlossaryTerm
from app.models.user import User
from app.schemas.glossary import GlossaryTermCreate, GlossaryTermUpdate
from app.services.papers import get_owned_paper


class GlossaryServiceError(RuntimeError):
    def __init__(self, detail: str, status_code: int = 409) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass(frozen=True)
class GlossaryMatch:
    term: GlossaryTerm
    start: int
    end: int


def _duplicate_statement(
    *,
    user_id: uuid.UUID,
    paper_id: uuid.UUID | None,
    scope: GlossaryScope,
    source_term: str,
    source_language: str,
    target_language: str,
    exclude_id: uuid.UUID | None = None,
):
    statement = select(GlossaryTerm.id).where(
        GlossaryTerm.user_id == user_id,
        GlossaryTerm.scope == scope.value,
        func.lower(GlossaryTerm.source_term) == source_term.casefold(),
        func.lower(GlossaryTerm.source_language) == source_language.casefold(),
        func.lower(GlossaryTerm.target_language) == target_language.casefold(),
    )
    if paper_id is None:
        statement = statement.where(GlossaryTerm.paper_id.is_(None))
    else:
        statement = statement.where(GlossaryTerm.paper_id == paper_id)
    if exclude_id is not None:
        statement = statement.where(GlossaryTerm.id != exclude_id)
    return statement


def create_glossary_term(
    db: Session,
    current_user: User,
    payload: GlossaryTermCreate,
) -> GlossaryTerm:
    if payload.paper_id is not None and get_owned_paper(
        db, current_user, payload.paper_id
    ) is None:
        raise GlossaryServiceError("Paper not found", 404)
    duplicate = db.scalar(
        _duplicate_statement(
            user_id=current_user.id,
            paper_id=payload.paper_id,
            scope=payload.scope,
            source_term=payload.source_term,
            source_language=payload.source_language,
            target_language=payload.target_language,
        )
    )
    if duplicate is not None:
        raise GlossaryServiceError("A glossary term already exists for this scope")
    term = GlossaryTerm(
        user_id=current_user.id,
        paper_id=payload.paper_id,
        source_term=payload.source_term,
        target_term=payload.target_term,
        source_language=payload.source_language,
        target_language=payload.target_language,
        scope=payload.scope.value,
        case_sensitive=payload.case_sensitive,
        enabled=payload.enabled,
    )
    db.add(term)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise GlossaryServiceError(
            "A glossary term already exists for this scope"
        ) from exc
    db.refresh(term)
    return term


def list_user_glossary(
    db: Session,
    current_user: User,
    *,
    scope: GlossaryScope | None = None,
) -> list[GlossaryTerm]:
    statement = select(GlossaryTerm).where(GlossaryTerm.user_id == current_user.id)
    if scope is not None:
        statement = statement.where(GlossaryTerm.scope == scope.value)
    return list(
        db.scalars(
            statement.order_by(
                GlossaryTerm.scope,
                func.lower(GlossaryTerm.source_term),
            )
        )
    )


def list_paper_glossary(
    db: Session,
    current_user: User,
    paper_id: uuid.UUID,
) -> list[GlossaryTerm] | None:
    if get_owned_paper(db, current_user, paper_id) is None:
        return None
    return list(
        db.scalars(
            select(GlossaryTerm)
            .where(
                GlossaryTerm.user_id == current_user.id,
                or_(
                    GlossaryTerm.paper_id == paper_id,
                    GlossaryTerm.paper_id.is_(None),
                ),
            )
            .order_by(
                GlossaryTerm.paper_id.desc().nulls_last(),
                func.lower(GlossaryTerm.source_term),
            )
        )
    )


def update_glossary_term(
    db: Session,
    current_user: User,
    term_id: uuid.UUID,
    payload: GlossaryTermUpdate,
) -> GlossaryTerm | None:
    term = db.scalar(
        select(GlossaryTerm).where(
            GlossaryTerm.id == term_id,
            GlossaryTerm.user_id == current_user.id,
        )
    )
    if term is None:
        return None
    values = payload.model_dump(exclude_unset=True)
    candidate_source = values.get("source_term", term.source_term)
    candidate_source_language = values.get("source_language", term.source_language)
    candidate_target_language = values.get("target_language", term.target_language)
    duplicate = db.scalar(
        _duplicate_statement(
            user_id=current_user.id,
            paper_id=term.paper_id,
            scope=GlossaryScope(term.scope),
            source_term=candidate_source,
            source_language=candidate_source_language,
            target_language=candidate_target_language,
            exclude_id=term.id,
        )
    )
    if duplicate is not None:
        raise GlossaryServiceError("A glossary term already exists for this scope")
    for field_name, value in values.items():
        setattr(term, field_name, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise GlossaryServiceError(
            "A glossary term already exists for this scope"
        ) from exc
    db.refresh(term)
    return term


def delete_glossary_term(
    db: Session,
    current_user: User,
    term_id: uuid.UUID,
) -> bool:
    term = db.scalar(
        select(GlossaryTerm).where(
            GlossaryTerm.id == term_id,
            GlossaryTerm.user_id == current_user.id,
        )
    )
    if term is None:
        return False
    db.delete(term)
    db.commit()
    return True


def _term_pattern(term: GlossaryTerm) -> re.Pattern[str]:
    flags = 0 if term.case_sensitive else re.IGNORECASE
    return re.compile(
        rf"(?<![\w]){re.escape(term.source_term)}(?![\w])",
        flags,
    )


def match_glossary_terms(
    terms: list[GlossaryTerm],
    text: str,
) -> list[GlossaryTerm]:
    enabled = [term for term in terms if term.enabled]
    by_source: dict[str, GlossaryTerm] = {}
    for term in sorted(
        enabled,
        key=lambda item: (
            0 if item.scope == GlossaryScope.PAPER.value else 1,
            -len(item.source_term),
            item.source_term.casefold(),
        ),
    ):
        by_source.setdefault(term.source_term.casefold(), term)

    matches: list[GlossaryMatch] = []
    for term in by_source.values():
        matches.extend(
            GlossaryMatch(term=term, start=match.start(), end=match.end())
            for match in _term_pattern(term).finditer(text)
        )
    matches.sort(
        key=lambda item: (
            -(item.end - item.start),
            0 if item.term.scope == GlossaryScope.PAPER.value else 1,
            item.start,
        )
    )
    occupied: list[tuple[int, int]] = []
    selected: list[GlossaryTerm] = []
    selected_ids: set[uuid.UUID] = set()
    for match in matches:
        if any(match.start < end and match.end > start for start, end in occupied):
            continue
        occupied.append((match.start, match.end))
        if match.term.id not in selected_ids:
            selected.append(match.term)
            selected_ids.add(match.term.id)
    return sorted(
        selected,
        key=lambda item: (
            -len(item.source_term),
            0 if item.scope == GlossaryScope.PAPER.value else 1,
            item.source_term.casefold(),
        ),
    )


def relevant_glossary(
    db: Session,
    *,
    user_id: uuid.UUID,
    paper_id: uuid.UUID,
    source_language: str,
    target_language: str,
    texts: list[str | None],
) -> dict[str, str]:
    language_conditions = [
        func.lower(GlossaryTerm.target_language) == target_language.casefold()
    ]
    if source_language.casefold() != "auto":
        language_conditions.append(
            func.lower(GlossaryTerm.source_language) == source_language.casefold()
        )
    terms = list(
        db.scalars(
            select(GlossaryTerm).where(
                GlossaryTerm.user_id == user_id,
                GlossaryTerm.enabled.is_(True),
                or_(
                    GlossaryTerm.paper_id == paper_id,
                    GlossaryTerm.paper_id.is_(None),
                ),
                *language_conditions,
            )
        )
    )
    context_text = "\n".join(text for text in texts if text)
    return {
        term.source_term: term.target_term
        for term in match_glossary_terms(terms, context_text)
    }
