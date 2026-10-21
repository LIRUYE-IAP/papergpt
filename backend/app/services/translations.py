from dataclasses import dataclass, replace
from datetime import datetime, timezone
import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.factory import get_translation_provider
from app.ai.errors import (
    AIInvalidBatchResponseError,
    TranslationExecutionError,
    TranslationFailedError,
)
from app.ai.providers import TranslationProvider
from app.ai.types import BatchTranslationItem, BatchTranslationRequest
from app.core.config import settings
from app.models.document import Block
from app.models.paper import Paper
from app.models.translation import Translation, TranslationStatus, TranslationVersion
from app.models.user import User
from app.services.papers import get_owned_paper
from app.services.glossary import relevant_glossary
from app.services.protected_tokens import (
    ProtectedText,
    protect_scientific_tokens,
    restore_scientific_tokens,
)
from app.services.translation_batches import TranslationBatch, build_translation_batches
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
    batch_count: int = 0
    provider_request_count: int = 0


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


def _get_or_create_translation(
    db: Session,
    *,
    paper: Paper,
    block: Block,
    target_language: str,
    provider: TranslationProvider,
) -> Translation:
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
    return translation


def _set_translation_processing(
    translation: Translation,
    *,
    paper: Paper,
    block: Block,
    provider: TranslationProvider,
) -> None:
    translation.status = TranslationStatus.PROCESSING
    translation.error_message = None
    translation.original_text = block.original_text
    translation.source_language = paper.source_language or "auto"
    translation.provider = provider.name
    translation.model = provider.model


def _set_translation_failed(
    translation: Translation,
    error: TranslationExecutionError,
) -> None:
    translation.status = TranslationStatus.FAILED
    translation.error_message = error.safe_message


def _persist_translation_success(
    db: Session,
    *,
    translation: Translation,
    translated_text: str,
    provider: str,
    model: str,
) -> None:
    version_number = _next_version_number(db, translation.id)
    db.add(
        TranslationVersion(
            translation_id=translation.id,
            translated_text=translated_text,
            provider=provider,
            model=model,
            version_number=version_number,
            reason="initial_translation" if version_number == 1 else "retranslation",
        )
    )
    translation.translated_text = translated_text
    translation.provider = provider
    translation.model = model
    translation.status = TranslationStatus.COMPLETED
    translation.translated_at = datetime.now(timezone.utc)
    translation.error_message = None
    replace_translation_qa(db, translation)


def _translate_block(
    db: Session,
    *,
    paper: Paper,
    block: Block,
    target_language: str,
    provider: TranslationProvider,
) -> BlockTranslationOutcome:
    translation = _get_or_create_translation(
        db,
        paper=paper,
        block=block,
        target_language=target_language,
        provider=provider,
    )
    _set_translation_processing(
        translation,
        paper=paper,
        block=block,
        provider=provider,
    )
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

        _persist_translation_success(
            db,
            translation=translation,
            translated_text=translated_text,
            provider=result.provider,
            model=result.model,
        )
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
        _set_translation_failed(failed_translation, failure)
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


def _batch_external_context(
    batch: TranslationBatch,
    candidates: list[Block],
) -> tuple[str | None, str | None]:
    indexes = {block.id: index for index, block in enumerate(candidates)}
    first_index = indexes[batch.blocks[0].id]
    last_index = indexes[batch.blocks[-1].id]
    previous_text = candidates[first_index - 1].original_text if first_index > 0 else None
    next_text = (
        candidates[last_index + 1].original_text
        if last_index + 1 < len(candidates)
        else None
    )
    return previous_text, next_text


def _build_batch_request(
    db: Session,
    *,
    paper: Paper,
    batch: TranslationBatch,
    candidates: list[Block],
    target_language: str,
) -> tuple[BatchTranslationRequest, dict[uuid.UUID, ProtectedText]]:
    previous_text, next_text = _batch_external_context(batch, candidates)
    source_language = paper.source_language or "auto"
    batch_glossary = relevant_glossary(
        db,
        user_id=paper.user_id,
        paper_id=paper.id,
        source_language=source_language,
        target_language=target_language,
        texts=[
            previous_text,
            *(block.original_text for block in batch.blocks),
            next_text,
        ],
    )
    protections: dict[uuid.UUID, ProtectedText] = {}
    items: list[BatchTranslationItem] = []
    for block in batch.blocks:
        protected = protect_scientific_tokens(
            block.original_text,
            namespace_seed=str(block.id),
        )
        protections[block.id] = protected
        item_glossary = relevant_glossary(
            db,
            user_id=paper.user_id,
            paper_id=paper.id,
            source_language=source_language,
            target_language=target_language,
            texts=[block.original_text],
        )
        items.append(
            BatchTranslationItem(
                block_id=block.id,
                block_type=block.block_type.value,
                source_text=block.original_text,
                protected_text=protected.text,
                relevant_glossary=item_glossary,
            )
        )
    return (
        BatchTranslationRequest(
            paper_title=paper.title or paper.original_filename,
            section_title=batch.section_title,
            source_language=source_language,
            target_language=target_language,
            items=tuple(items),
            glossary=batch_glossary,
            external_previous_context=previous_text,
            external_next_context=next_text,
        ),
        protections,
    )


def _validated_batch_results(request, result):
    requested_ids = {item.block_id for item in request.items}
    mapped = {}
    for item in result.items:
        if item.block_id not in requested_ids or item.block_id in mapped:
            raise AIInvalidBatchResponseError()
        mapped[item.block_id] = item
    return mapped


def _mark_batch_failed(
    db: Session,
    translations: dict[uuid.UUID, Translation],
    error: TranslationExecutionError,
) -> None:
    db.rollback()
    for translation in translations.values():
        persisted = db.get(Translation, translation.id)
        if persisted is not None:
            _set_translation_failed(persisted, error)
    db.commit()


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

    candidates = [block for block in blocks if is_translation_candidate(block)]
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
        if existing is not None and existing.status == TranslationStatus.COMPLETED:
            skipped_count += 1
            continue
        translatable_blocks.append(block)

    batches = build_translation_batches(
        translatable_blocks,
        max_blocks=settings.translation_batch_max_blocks,
        max_chars=settings.translation_batch_max_chars,
    )
    translated_count = 0
    failed_count = 0
    provider_request_count = 0
    attempted_batch_count = 0
    for batch_index, batch in enumerate(batches):
        attempted_batch_count += 1
        request, protections = _build_batch_request(
            db,
            paper=paper,
            batch=batch,
            candidates=candidates,
            target_language=normalized_target,
        )
        translations: dict[uuid.UUID, Translation] = {}
        for block in batch.blocks:
            translation = _get_or_create_translation(
                db,
                paper=paper,
                block=block,
                target_language=normalized_target,
                provider=active_provider,
            )
            _set_translation_processing(
                translation,
                paper=paper,
                block=block,
                provider=active_provider,
            )
            translations[block.id] = translation
        db.commit()
        provider_request_count += 1
        started_at = datetime.now(timezone.utc)
        provider_failure: TranslationExecutionError | None = None
        try:
            result = active_provider.translate_batch(request)
            mapped_results = _validated_batch_results(request, result)
        except TranslationExecutionError as exc:
            provider_failure = exc
        except Exception:
            provider_failure = TranslationFailedError()
        if provider_failure is not None:
            _mark_batch_failed(db, translations, provider_failure)
            failed_count += len(batch.blocks)
            paper = db.get(Paper, paper.id)
            if paper is not None:
                paper.translation_status = TranslationStatus.FAILED.value
                db.commit()
            logger.warning(
                "translation_batch_failed category=%s provider=%s model=%s "
                "paper_id=%s batch_index=%s block_count=%s character_count=%s "
                "provider_status=%s",
                provider_failure.code,
                active_provider.name,
                active_provider.model,
                paper_id,
                batch_index,
                len(batch.blocks),
                batch.character_count,
                provider_failure.provider_status,
            )
            remaining_count = sum(
                len(remaining.blocks) for remaining in batches[batch_index + 1 :]
            )
            raise TranslationRunInterrupted(
                provider_failure,
                TranslationRunResult(
                    translated_count=translated_count,
                    skipped_count=skipped_count,
                    failed_count=failed_count,
                    remaining_count=remaining_count,
                    batch_count=attempted_batch_count,
                    provider_request_count=provider_request_count,
                ),
            ) from provider_failure

        item_failure = TranslationFailedError()
        batch_completed_count = 0
        batch_failed_count = 0
        try:
            for block in batch.blocks:
                translation = translations[block.id]
                result_item = mapped_results.get(block.id)
                if result_item is None:
                    _set_translation_failed(translation, item_failure)
                    batch_failed_count += 1
                    continue
                try:
                    translated_text = restore_scientific_tokens(
                        result_item.translated_text,
                        protections[block.id].tokens,
                    ).strip()
                    if not translated_text:
                        raise ValueError("Provider returned an empty translation")
                except ValueError:
                    _set_translation_failed(translation, item_failure)
                    batch_failed_count += 1
                    logger.warning(
                        "translation_batch_item_failed category=%s provider=%s "
                        "model=%s paper_id=%s batch_index=%s block_id=%s",
                        item_failure.code,
                        active_provider.name,
                        active_provider.model,
                        paper_id,
                        batch_index,
                        block.id,
                    )
                    continue
                _persist_translation_success(
                    db,
                    translation=translation,
                    translated_text=translated_text,
                    provider=result.provider,
                    model=result.model,
                )
                batch_completed_count += 1
            db.commit()
            translated_count += batch_completed_count
            failed_count += batch_failed_count
        except Exception:
            failure = TranslationFailedError()
            _mark_batch_failed(db, translations, failure)
            failed_count += len(batch.blocks)
            paper = db.get(Paper, paper.id)
            if paper is not None:
                paper.translation_status = TranslationStatus.FAILED.value
                db.commit()
            raise TranslationRunInterrupted(
                failure,
                TranslationRunResult(
                    translated_count=translated_count,
                    skipped_count=skipped_count,
                    failed_count=failed_count,
                    remaining_count=sum(
                        len(remaining.blocks)
                        for remaining in batches[batch_index + 1 :]
                    ),
                    batch_count=attempted_batch_count,
                    provider_request_count=provider_request_count,
                ),
            ) from None

        duration_ms = int(
            (datetime.now(timezone.utc) - started_at).total_seconds() * 1000
        )
        logger.info(
            "translation_batch_completed paper_id=%s batch_index=%s "
            "block_count=%s character_count=%s provider=%s model=%s duration_ms=%s",
            paper_id,
            batch_index,
            len(batch.blocks),
            batch.character_count,
            active_provider.name,
            active_provider.model,
            duration_ms,
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
        batch_count=len(batches),
        provider_request_count=provider_request_count,
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
            batch_count=0,
            provider_request_count=0,
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
        batch_count=1,
        provider_request_count=1,
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
