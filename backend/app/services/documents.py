from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models.document import Block, BlockType, Section
from app.models.paper import Paper
from app.models.translation import Translation
from app.models.user import User
from app.services.document_engine import (
    PARSER_VERSION,
    DocumentEngineError,
    PDFDocumentEngine,
    ParsedDocument,
)
from app.services.papers import get_owned_paper
from app.services.storage import LocalStorage


class PaperParseError(RuntimeError):
    def __init__(self, detail: str, status_code: int = 422) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass(frozen=True)
class ParseResult:
    paper_id: uuid.UUID
    page_count: int
    section_count: int
    block_count: int
    is_scanned: bool


def _stable_document_uuid(
    paper_id: uuid.UUID, entity: str, identity: dict[str, object]
) -> uuid.UUID:
    canonical_identity = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return uuid.uuid5(
        paper_id,
        f"papergpt:{PARSER_VERSION}:{entity}:{canonical_identity}",
    )


def _set_parse_failed(db: Session, paper_id: uuid.UUID) -> None:
    db.rollback()
    paper = db.get(Paper, paper_id)
    if paper is not None:
        paper.parse_status = "FAILED"
        db.commit()


def _section_uuid(
    paper_id: uuid.UUID,
    section_data: object,
) -> uuid.UUID:
    return _stable_document_uuid(
        paper_id,
        "section",
        {
            "order_index": section_data.order_index,
            "level": section_data.level,
            "title": section_data.title_original,
            "start_page": section_data.start_page,
            "end_page": section_data.end_page,
            "parent_index": section_data.parent_index,
        },
    )


def _block_uuid(paper_id: uuid.UUID, block_data: object) -> uuid.UUID:
    return _stable_document_uuid(
        paper_id,
        "block",
        {
            "reading_order": block_data.reading_order,
            "page_number": block_data.page_number,
            "block_type": block_data.block_type.value,
            "bbox": block_data.bbox(),
            "column_index": block_data.column_index,
            "text": block_data.original_text,
        },
    )


def _reconcile_parsed_document(
    db: Session,
    paper: Paper,
    parsed: ParsedDocument,
) -> tuple[list[Section], list[Block]]:
    """Persist a parse without deleting stable Blocks that own translation history."""

    section_ids = [_section_uuid(paper.id, item) for item in parsed.sections]
    block_ids = [_block_uuid(paper.id, item) for item in parsed.blocks]

    # Detach current relationships in the same transaction before removing obsolete
    # sections. This prevents a removed parent section from cascading into a section
    # whose stable UUID is still part of the new parse.
    db.execute(
        update(Block)
        .where(Block.paper_id == paper.id)
        .values(section_id=None, parent_block_id=None)
    )
    db.execute(
        update(Section).where(Section.paper_id == paper.id).values(parent_id=None)
    )
    obsolete_sections = delete(Section).where(Section.paper_id == paper.id)
    if section_ids:
        obsolete_sections = obsolete_sections.where(Section.id.not_in(section_ids))
    db.execute(obsolete_sections)
    db.flush()

    existing_sections = {
        section.id: section
        for section in db.scalars(
            select(Section).where(Section.paper_id == paper.id)
        )
    }
    section_models: list[Section] = []
    for section_id, section_data in zip(section_ids, parsed.sections, strict=True):
        section = existing_sections.get(section_id)
        if section is None:
            section = Section(
                id=section_id,
                paper_id=paper.id,
                title_zh=None,
                summary=None,
            )
            db.add(section)
        section.title_original = section_data.title_original
        section.level = section_data.level
        section.order_index = section_data.order_index
        section.start_page = section_data.start_page
        section.end_page = section_data.end_page
        section_models.append(section)
    db.flush()
    for section, section_data in zip(section_models, parsed.sections, strict=True):
        section.parent = (
            section_models[section_data.parent_index]
            if section_data.parent_index is not None
            else None
        )
    db.flush()

    existing_blocks = {
        block.id: block
        for block in db.scalars(select(Block).where(Block.paper_id == paper.id))
    }
    translated_block_ids = set(
        db.scalars(
            select(Translation.block_id).where(Translation.paper_id == paper.id)
        )
    )
    current_block_ids = set(block_ids)
    for block_id, block in existing_blocks.items():
        if block_id in current_block_ids:
            continue
        if block_id in translated_block_ids:
            metadata = dict(block.block_metadata or {})
            metadata["papergpt_stale"] = {
                "reason": "missing_from_latest_parse",
                "parser_version": PARSER_VERSION,
            }
            block.block_metadata = metadata
            block.is_stale = True
            block.is_translatable = False
            block.section = None
            block.parent_block_id = None
        else:
            db.delete(block)
    db.flush()

    block_models: list[Block] = []
    for block_id, block_data in zip(block_ids, parsed.blocks, strict=True):
        block = existing_blocks.get(block_id)
        section = (
            section_models[block_data.section_index]
            if block_data.section_index is not None
            else None
        )
        if block is None:
            block = Block(id=block_id, paper_id=paper.id)
            db.add(block)
        block.section = section
        block.page_number = block_data.page_number
        block.block_type = block_data.block_type
        block.original_text = block_data.original_text
        block.reading_order = block_data.reading_order
        block.bbox = block_data.bbox()
        block.column_index = block_data.column_index
        block.parent_block_id = None
        block.block_metadata = dict(block_data.metadata)
        block.is_translatable = block_data.is_translatable
        block.is_stale = False
        block_models.append(block)
    db.flush()
    return section_models, block_models


def parse_owned_paper(
    db: Session,
    current_user: User,
    paper_id: uuid.UUID,
    storage: LocalStorage,
    engine: PDFDocumentEngine | None = None,
) -> ParseResult | None:
    paper = get_owned_paper(db, current_user, paper_id)
    if paper is None:
        return None

    paper.parse_status = "PROCESSING"
    db.commit()
    source_path = storage.path_for_key(paper.file_key)
    parser = engine or PDFDocumentEngine()
    try:
        if not source_path.is_file():
            raise DocumentEngineError("The stored PDF file is missing")
        parsed = parser.parse(source_path)
    except DocumentEngineError as exc:
        _set_parse_failed(db, paper.id)
        raise PaperParseError(str(exc)) from exc
    except Exception as exc:
        _set_parse_failed(db, paper.id)
        raise PaperParseError("PDF parsing failed") from exc

    try:
        section_models, block_models = _reconcile_parsed_document(db, paper, parsed)
        paper.page_count = int(parsed.metadata["page_count"])
        if parsed.metadata.get("title"):
            paper.title = str(parsed.metadata["title"])
        paper.parse_status = "COMPLETED"
        db.commit()
    except Exception as exc:
        _set_parse_failed(db, paper.id)
        raise PaperParseError("Could not persist the parsed document", 500) from exc

    section_json = []
    for index, (parsed_section, model) in enumerate(
        zip(parsed.sections, section_models, strict=True)
    ):
        section_json.append(
            {
                "id": str(model.id),
                **parsed_section.as_dict(),
                "parent_id": (
                    str(section_models[parsed_section.parent_index].id)
                    if parsed_section.parent_index is not None
                    else None
                ),
                "section_index": index,
            }
        )
    block_json = []
    for parsed_block, model in zip(parsed.blocks, block_models, strict=True):
        block_json.append(
            {
                "id": str(model.id),
                **parsed_block.as_dict(),
                "section_id": str(model.section.id) if model.section is not None else None,
            }
        )
    document_json = {
        "metadata": parsed.metadata,
        "pages": parsed.pages,
        "sections": section_json,
        "blocks": block_json,
    }
    try:
        storage.write_processing_artifacts(
            paper.file_key,
            {
                "raw_pdf_blocks.json": parsed.raw_pdf_blocks,
                "layout.json": parsed.layout_json(),
                "document.json": document_json,
            },
        )
    except Exception as exc:
        _set_parse_failed(db, paper.id)
        raise PaperParseError("Could not write document debug artifacts", 500) from exc

    return ParseResult(
        paper_id=paper.id,
        page_count=paper.page_count,
        section_count=len(section_models),
        block_count=len(block_models),
        is_scanned=bool(parsed.metadata["is_scanned"]),
    )


def list_owned_sections(
    db: Session, current_user: User, paper_id: uuid.UUID
) -> list[Section] | None:
    if get_owned_paper(db, current_user, paper_id) is None:
        return None
    return list(
        db.scalars(
            select(Section)
            .where(Section.paper_id == paper_id)
            .order_by(Section.order_index)
        )
    )


def list_owned_blocks(
    db: Session,
    current_user: User,
    paper_id: uuid.UUID,
    *,
    page: int | None = None,
    section_id: uuid.UUID | None = None,
    block_type: BlockType | None = None,
) -> list[Block] | None:
    if get_owned_paper(db, current_user, paper_id) is None:
        return None
    statement = select(Block).where(
        Block.paper_id == paper_id,
        Block.is_stale.is_(False),
    )
    if page is not None:
        statement = statement.where(Block.page_number == page)
    if section_id is not None:
        statement = statement.where(Block.section_id == section_id)
    if block_type is not None:
        statement = statement.where(Block.block_type == block_type)
    return list(db.scalars(statement.order_by(Block.reading_order)))
