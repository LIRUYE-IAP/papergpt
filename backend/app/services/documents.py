from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.document import Block, BlockType, Section
from app.models.paper import Paper
from app.models.user import User
from app.services.document_engine import (
    PARSER_VERSION,
    DocumentEngineError,
    PDFDocumentEngine,
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

    section_models: list[Section] = []
    for section_data in parsed.sections:
        parent = (
            section_models[section_data.parent_index]
            if section_data.parent_index is not None
            else None
        )
        section_models.append(
            Section(
                id=_stable_document_uuid(
                    paper.id,
                    "section",
                    {
                        "order_index": section_data.order_index,
                        "level": section_data.level,
                        "title": section_data.title_original,
                        "start_page": section_data.start_page,
                        "end_page": section_data.end_page,
                        "parent_index": section_data.parent_index,
                    },
                ),
                paper_id=paper.id,
                parent=parent,
                title_original=section_data.title_original,
                title_zh=None,
                level=section_data.level,
                order_index=section_data.order_index,
                start_page=section_data.start_page,
                end_page=section_data.end_page,
                summary=None,
            )
        )

    block_models: list[Block] = []
    for block_data in parsed.blocks:
        section = (
            section_models[block_data.section_index]
            if block_data.section_index is not None
            else None
        )
        block_models.append(
            Block(
                id=_stable_document_uuid(
                    paper.id,
                    "block",
                    {
                        "reading_order": block_data.reading_order,
                        "page_number": block_data.page_number,
                        "block_type": block_data.block_type.value,
                        "bbox": block_data.bbox(),
                        "column_index": block_data.column_index,
                        "text": block_data.original_text,
                    },
                ),
                paper_id=paper.id,
                section=section,
                page_number=block_data.page_number,
                block_type=block_data.block_type,
                original_text=block_data.original_text,
                reading_order=block_data.reading_order,
                bbox=block_data.bbox(),
                column_index=block_data.column_index,
                parent_block_id=None,
                block_metadata=block_data.metadata,
                is_translatable=block_data.is_translatable,
            )
        )

    try:
        db.execute(delete(Block).where(Block.paper_id == paper.id))
        db.execute(delete(Section).where(Section.paper_id == paper.id))
        db.add_all(section_models)
        db.add_all(block_models)
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
    statement = select(Block).where(Block.paper_id == paper_id)
    if page is not None:
        statement = statement.where(Block.page_number == page)
    if section_id is not None:
        statement = statement.where(Block.section_id == section_id)
    if block_type is not None:
        statement = statement.where(Block.block_type == block_type)
    return list(db.scalars(statement.order_by(Block.reading_order)))
