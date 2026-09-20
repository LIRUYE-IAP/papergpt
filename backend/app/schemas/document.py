import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import BlockType


class SectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    paper_id: uuid.UUID
    parent_id: uuid.UUID | None
    title_original: str
    title_zh: str | None
    level: int
    order_index: int
    start_page: int
    end_page: int
    summary: str | None
    created_at: datetime


class SectionOutlineResponse(SectionResponse):
    children: list["SectionOutlineResponse"] = Field(default_factory=list)


class BlockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    paper_id: uuid.UUID
    section_id: uuid.UUID | None
    page_number: int
    block_type: BlockType
    original_text: str
    reading_order: int
    bbox: dict[str, Any]
    column_index: int | None
    parent_block_id: uuid.UUID | None
    metadata: dict[str, Any] = Field(validation_alias="block_metadata")
    is_translatable: bool
    is_stale: bool
    created_at: datetime
    updated_at: datetime


class ParseResponse(BaseModel):
    paper_id: uuid.UUID
    parse_status: str
    page_count: int
    section_count: int
    block_count: int
    is_scanned: bool
