import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class PaperResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    filename: str
    original_filename: str
    title: str | None
    title_zh: str | None
    authors: list[dict[str, Any] | str]
    journal: str | None
    doi: str | None
    publication_year: int | None
    source_language: str | None
    target_language: str | None
    page_count: int | None
    file_size: int
    file_key: str
    file_hash: str
    document_type: str
    parse_status: str
    translation_status: str
    qa_status: str
    current_page: int
    reading_progress: Decimal
    created_at: datetime
    updated_at: datetime
    last_opened_at: datetime | None
