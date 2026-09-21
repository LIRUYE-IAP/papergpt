import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.types import TranslationRequest
from app.models.document import Block, BlockType
from app.models.paper import Paper
from app.services.glossary import relevant_glossary

_SKIPPED_BLOCK_TYPES = {
    BlockType.HEADER,
    BlockType.FOOTER,
    BlockType.PAGE_NUMBER,
    BlockType.REFERENCE,
    BlockType.FIGURE,
    BlockType.TABLE,
    BlockType.EQUATION,
}


def is_translation_candidate(block: Block) -> bool:
    return (
        not block.is_stale
        and block.is_translatable
        and block.block_type not in _SKIPPED_BLOCK_TYPES
    )


def build_translation_context(
    db: Session,
    *,
    paper: Paper,
    block: Block,
    target_language: str,
) -> TranslationRequest:
    ordered_blocks = list(
        db.scalars(
            select(Block)
            .where(Block.paper_id == paper.id, Block.is_stale.is_(False))
            .order_by(Block.reading_order)
        )
    )
    candidates = [
        candidate for candidate in ordered_blocks if is_translation_candidate(candidate)
    ]
    candidate_ids = [candidate.id for candidate in candidates]
    try:
        current_index = candidate_ids.index(block.id)
    except ValueError:
        current_index = -1

    previous_text = (
        candidates[current_index - 1].original_text if current_index > 0 else None
    )
    next_text = (
        candidates[current_index + 1].original_text
        if current_index >= 0 and current_index + 1 < len(candidates)
        else None
    )
    section_title = block.section.title_original if block.section is not None else None
    glossary = relevant_glossary(
        db,
        user_id=paper.user_id,
        paper_id=paper.id,
        source_language=paper.source_language or "auto",
        target_language=target_language,
        texts=[previous_text, block.original_text, next_text],
    )
    return TranslationRequest(
        paper_title=paper.title or paper.original_filename,
        section_title=section_title,
        block_type=block.block_type.value,
        previous_text=previous_text,
        current_text=block.original_text,
        next_text=next_text,
        source_language=paper.source_language or "auto",
        target_language=target_language,
        glossary=glossary,
    )


def get_owned_block(
    db: Session,
    *,
    paper_id: uuid.UUID,
    block_id: uuid.UUID,
) -> Block | None:
    return db.scalar(
        select(Block).where(
            Block.id == block_id,
            Block.paper_id == paper_id,
            Block.is_stale.is_(False),
        )
    )
