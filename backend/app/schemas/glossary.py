import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.glossary import GlossaryScope


class GlossaryTermCreate(BaseModel):
    source_term: str = Field(min_length=1, max_length=500)
    target_term: str = Field(min_length=1, max_length=500)
    source_language: str = Field(default="en", min_length=2, max_length=32)
    target_language: str = Field(default="zh-CN", min_length=2, max_length=32)
    scope: GlossaryScope
    paper_id: uuid.UUID | None = None
    case_sensitive: bool = False
    enabled: bool = True

    @model_validator(mode="after")
    def validate_scope(self) -> "GlossaryTermCreate":
        if self.scope == GlossaryScope.PAPER and self.paper_id is None:
            raise ValueError("paper_id is required for PAPER glossary terms")
        if self.scope == GlossaryScope.USER_GLOBAL and self.paper_id is not None:
            raise ValueError("USER_GLOBAL glossary terms cannot have paper_id")
        self.source_term = self.source_term.strip()
        self.target_term = self.target_term.strip()
        self.source_language = self.source_language.strip()
        self.target_language = self.target_language.strip()
        if not all(
            (
                self.source_term,
                self.target_term,
                self.source_language,
                self.target_language,
            )
        ):
            raise ValueError("glossary term fields must not be blank")
        return self


class GlossaryTermUpdate(BaseModel):
    source_term: str | None = Field(default=None, min_length=1, max_length=500)
    target_term: str | None = Field(default=None, min_length=1, max_length=500)
    source_language: str | None = Field(default=None, min_length=2, max_length=32)
    target_language: str | None = Field(default=None, min_length=2, max_length=32)
    case_sensitive: bool | None = None
    enabled: bool | None = None

    @model_validator(mode="after")
    def validate_update(self) -> "GlossaryTermUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        for field_name in (
            "source_term",
            "target_term",
            "source_language",
            "target_language",
        ):
            value = getattr(self, field_name)
            if value is not None:
                normalized = value.strip()
                if not normalized:
                    raise ValueError(f"{field_name} must not be blank")
                setattr(self, field_name, normalized)
        return self


class GlossaryTermResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    paper_id: uuid.UUID | None
    source_term: str
    target_term: str
    source_language: str
    target_language: str
    scope: GlossaryScope
    case_sensitive: bool
    enabled: bool
    created_at: datetime
    updated_at: datetime
