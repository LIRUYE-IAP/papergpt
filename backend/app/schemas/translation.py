import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.translation import TranslationStatus


def _normalize_target_language(value: str) -> str:
    parts = value.strip().replace("_", "-").split("-")
    if not parts or not parts[0]:
        raise ValueError("target_language must not be empty")
    normalized = [parts[0].lower()]
    normalized.extend(part.upper() if len(part) == 2 else part for part in parts[1:])
    return "-".join(normalized)


class TranslationRequestPayload(BaseModel):
    target_language: str = Field(min_length=2, max_length=32)

    @field_validator("target_language")
    @classmethod
    def normalize_target_language(cls, value: str) -> str:
        return _normalize_target_language(value)


class TranslationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    paper_id: uuid.UUID
    block_id: uuid.UUID
    source_language: str
    target_language: str
    original_text: str
    translated_text: str | None
    provider: str
    model: str
    status: TranslationStatus
    user_modified: bool
    qa_status: str
    created_at: datetime
    updated_at: datetime
    translated_at: datetime | None
    error_message: str | None


class TranslationRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    translated_count: int
    skipped_count: int
    failed_count: int


class BlockTranslationRunResponse(TranslationRunResponse):
    translation: TranslationResponse | None


class TranslationEditPayload(BaseModel):
    translated_text: str = Field(min_length=1, max_length=200_000)

    @field_validator("translated_text")
    @classmethod
    def validate_translated_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("translated_text must not be blank")
        return normalized


class TranslationVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    translation_id: uuid.UUID
    translated_text: str
    provider: str
    model: str
    version_number: int
    created_at: datetime
    reason: str


class TranslationQAResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    translation_id: uuid.UUID
    check_type: str
    status: str
    message: str
    details: dict[str, object]
    created_at: datetime


class TranslationQAResponse(BaseModel):
    translation_id: uuid.UUID
    qa_status: str
    results: list[TranslationQAResultResponse]
