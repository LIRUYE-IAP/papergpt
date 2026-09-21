from dataclasses import dataclass, replace
from datetime import datetime, timezone
import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.factory import get_translation_provider
from app.ai.errors import TranslationExecutionError, TranslationFailedError
from app.ai.providers import TranslationProvider
from app.models.document import Block
from app.models.paper import Paper
from app.models.translation import Translation, TranslationStatus, TranslationVersion
from app.models.user import User
from app.services.papers import get_owned_paper
from app.services.protected_tokens import (
    protect_scientific_tokens,
    restore_scientific_tokens,
)
from app.services.translation_context import (
    build_translation_context,
    get_owned_block,
    is_translation_candidate,
)
from app.services.translation_qa import (
    QA_PENDING,
    get_owned_active_translation,
    replace_translation_qa,
)


class TranslationServiceError(RuntimeError):
    def __init__(self, detail: str, status_code: int = 409) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranslationRunResult:
    translated_count: int
    skipped_count: int
    failed_count: int
    remaining_count: int = 0


@dataclass(frozen=True)
class BlockTranslationRunResult(TranslationRunResult):
    translation: Translation | None = None


@dataclass(frozen=True)
class BlockTranslationOutcome:
    succeeded: bool
    translation: Translation
    error: TranslationExecutionError | None = None


class TranslationRunInterrupted(RuntimeError):
    def __init__(
        self,
        error: TranslationExecutionError,
        result: TranslationRunResult,
    ) -> None:
        super().__init__(error.safe_message)
        self.error = error
        self.result = result


def normalize_language_tag(language: str) -> str:
    parts = language.strip().replace("_", "-").split("-")
    if not parts or not parts[0]:
        raise TranslationServiceError("target_language must not be empty", 422)
    normalized = [parts[0].lower()]
    for part in parts[1:]:
        normalized.append(part.upper() if len(part) == 2 else part)
    return "-".join(normalized)


def _existing_translation(
    db: Session,
    *,
    block_id: uuid.UUID,
    target_language: str,
) -> Translation | None:
    return db.scalar(
        select(Translation).where(
            Translation.block_id == block_id,
            Translation.target_language == target_language,
        )
    )


def _next_version_number(db: Session, translation_id: uuid.UUID) -> int:
    current = db.scalar(
        select(func.max(TranslationVersion.version_number)).where(
            TranslationVersion.translation_id == translation_id
        )
    )
    return int(current or 0) + 1


def _translate_block(
    db: Session,
    *,
    paper: Paper,
    block: Block,
    target_language: str,
    provider: TranslationProvider,
) -> BlockTranslationOutcome:
    translation = _existing_translation(
        db,
        block_id=block.id,
        target_language=target_language,
    )
    if translation is None:
        translation = Translation(
            paper_id=paper.id,
            block_id=block.id,
            source_language=paper.source_language or "auto",
            target_language=target_language,
            original_text=block.original_text,
            translated_text=None,
            provider=provider.name,
            model=provider.model,
            status=TranslationStatus.PENDING,
            user_modified=False,
            qa_status="PENDING",
        )
        db.add(translation)
        db.flush()

    translation.status = TranslationStatus.PROCESSING
    translation.error_message = None
    translation.original_text = block.original_text
    translation.source_language = paper.source_language or "auto"
    translation.provider = provider.name
    translation.model = provider.model
    db.commit()

    try:
        context = build_translation_context(
            db,
            paper=paper,
            block=block,
            target_language=target_language,
        )
        protected = protect_scientific_tokens(context.current_text)
        result = provider.translate(replace(context, current_text=protected.text))
        translated_text = restore_scientific_tokens(
            result.translated_text,
            protected.tokens,
        ).strip()
        if not translated_text:
            raise ValueError("Provider returned an empty translation")

        version_number = _next_version_number(db, translation.id)
        db.add(
            TranslationVersion(
                translation_id=translation.id,
                translated_text=translated_text,
                provider=result.provider,
                model=result.model,
                version_number=version_number,
                reason=(
                    "initial_translation" if version_number == 1 else "retranslation"
                ),
            )
        )
        translation.translated_text = translated_text
        translation.provider = result.provider
        translation.model = result.model
        translation.status = TranslationStatus.COMPLETED
        translation.translated_at = datetime.now(timezone.utc)
        translation.error_message = None
        replace_translation_qa(db, translation)
        db.commit()
        db.refresh(translation)
        return BlockTranslationOutcome(True, translation)
    except TranslationExecutionError as exc:
        failure = exc
    except Exception:
        failure = TranslationFailedError()

    try:
        db.rollback()
        failed_translation = db.get(Translation, translation.id)
        if failed_translation is None:
            raise failure
        failed_translation.status = TranslationStatus.FAILED
        failed_translation.error_message = failure.safe_message
        db.commit()
        db.refresh(failed_translation)
    except Exception:
        db.rollback()
        raise

    logger.warning(
        "translation_failed category=%s provider=%s model=%s paper_id=%s "
        "block_id=%s provider_status=%s",
        failure.code,
        provider.name,
        provider.model,
        paper.id,
        block.id,
        failure.provider_status,
    )
    return BlockTranslationOutcome(False, failed_translation, failure)


def translate_owned_paper(
    db: Session,
    current_user: User,
    paper_id: uuid.UUID,
    target_language: str,
    *,
    provider: TranslationProvider | None = None,
) -> TranslationRunResult | None:
    paper = get_owned_paper(db, current_user, paper_id)
    if paper is None:
        return None
    if paper.parse_status != "COMPLETED":
        raise TranslationServiceError("Paper must be parsed before translation")

    normalized_target = normalize_language_tag(target_language)
    active_provider = provider or get_translation_provider()
    blocks = list(
        db.scalars(
            select(Block)
            .where(Block.paper_id == paper.id, Block.is_stale.is_(False))
            .order_by(Block.reading_order)
        )
    )

    paper.translation_status = TranslationStatus.PROCESSING.value
    paper.target_language = normalized_target
    db.commit()

    translatable_blocks: list[Block] = []
    skipped_count = 0
    for block in blocks:
        if not is_translation_candidate(block):
            skipped_count += 1
            continue
        existing = _existing_translation(
            db,
            block_id=block.id,
            target_language=normalized_target,
        )
        if existing is not None and existing.user_modified:
            skipped_count += 1
            continue
        translatable_blocks.append(block)

    translated_count = 0
    failed_count = 0
    for index, block in enumerate(translatable_blocks):
        outcome = _translate_block(
            db,
            paper=paper,
            block=block,
            target_language=normalized_target,
            provider=active_provider,
        )
        if outcome.succeeded:
            translated_count += 1
        else:
            failed_count += 1
            if outcome.error is not None and outcome.error.stop_batch:
                paper = db.get(Paper, paper.id)
                if paper is not None:
                    paper.translation_status = TranslationStatus.FAILED.value
                    db.commit()
                raise TranslationRunInterrupted(
                    outcome.error,
                    TranslationRunResult(
                        translated_count=translated_count,
                        skipped_count=skipped_count,
                        failed_count=failed_count,
                        remaining_count=len(translatable_blocks) - index - 1,
                    ),
                )

    paper = db.get(Paper, paper.id)
    if paper is not None:
        paper.translation_status = (
            TranslationStatus.FAILED.value
            if failed_count
            else TranslationStatus.COMPLETED.value
        )
        db.commit()

    return TranslationRunResult(
        translated_count=translated_count,
        skipped_count=skipped_count,
        failed_count=failed_count,
    )


def translate_owned_block(
    db: Session,
    current_user: User,
    paper_id: uuid.UUID,
    block_id: uuid.UUID,
    target_language: str,
    *,
    provider: TranslationProvider | None = None,
) -> BlockTranslationRunResult | None:
    paper = get_owned_paper(db, current_user, paper_id)
    if paper is None:
        return None
    if paper.parse_status != "COMPLETED":
        raise TranslationServiceError("Paper must be parsed before translation")
    block = get_owned_block(db, paper_id=paper.id, block_id=block_id)
    if block is None:
        return None

    normalized_target = normalize_language_tag(target_language)
    existing = _existing_translation(
        db,
        block_id=block.id,
        target_language=normalized_target,
    )
    if not is_translation_candidate(block) or (
        existing is not None and existing.user_modified
    ):
        return BlockTranslationRunResult(
            translated_count=0,
            skipped_count=1,
            failed_count=0,
            translation=existing,
        )

    outcome = _translate_block(
        db,
        paper=paper,
        block=block,
        target_language=normalized_target,
        provider=provider or get_translation_provider(),
    )
    paper.translation_status = (
        TranslationStatus.COMPLETED.value
        if outcome.succeeded
        else TranslationStatus.FAILED.value
    )
    paper.target_language = normalized_target
    db.commit()
    if outcome.error is not None:
        raise outcome.error
    return BlockTranslationRunResult(
        translated_count=1 if outcome.succeeded else 0,
        skipped_count=0,
        failed_count=0 if outcome.succeeded else 1,
        translation=outcome.translation,
    )


def list_owned_translations(
    db: Session,
    current_user: User,
    paper_id: uuid.UUID,
    *,
    target_language: str | None = None,
    page: int | None = None,
    section_id: uuid.UUID | None = None,
) -> list[Translation] | None:
    if get_owned_paper(db, current_user, paper_id) is None:
        return None
    statement = (
        select(Translation)
        .join(Block, Block.id == Translation.block_id)
        .where(Translation.paper_id == paper_id, Block.is_stale.is_(False))
        .order_by(Block.reading_order)
    )
    if target_language:
        statement = statement.where(
            Translation.target_language == normalize_language_tag(target_language)
        )
    if page is not None:
        statement = statement.where(Block.page_number == page)
    if section_id is not None:
        statement = statement.where(Block.section_id == section_id)
    return list(db.scalars(statement))


def edit_owned_translation(
    db: Session,
    current_user: User,
    paper_id: uuid.UUID,
    translation_id: uuid.UUID,
    translated_text: str,
) -> Translation | None:
    translation = get_owned_active_translation(
        db, current_user, paper_id, translation_id
    )
    if translation is None:
        return None
    version_number = _next_version_number(db, translation.id)
    db.add(
        TranslationVersion(
            translation_id=translation.id,
            translated_text=translated_text,
            provider="user",
            model="manual-edit",
            version_number=version_number,
            reason="USER_EDIT",
        )
    )
    translation.translated_text = translated_text
    translation.provider = "user"
    translation.model = "manual-edit"
    translation.user_modified = True
    translation.status = TranslationStatus.COMPLETED
    translation.qa_status = QA_PENDING
    translation.error_message = None
    translation.translated_at = datetime.now(timezone.utc)
    db.flush()
    replace_translation_qa(db, translation)
    db.commit()
    db.refresh(translation)
    return translation


def list_owned_translation_versions(
    db: Session,
    current_user: User,
    paper_id: uuid.UUID,
    translation_id: uuid.UUID,
) -> list[TranslationVersion] | None:
    translation = get_owned_active_translation(
        db, current_user, paper_id, translation_id
    )
    if translation is None:
        return None
    return list(
        db.scalars(
            select(TranslationVersion)
            .where(TranslationVersion.translation_id == translation.id)
            .order_by(TranslationVersion.version_number)
        )
    )
