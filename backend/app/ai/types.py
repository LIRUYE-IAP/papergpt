from dataclasses import dataclass, field
import uuid


@dataclass(frozen=True)
class TranslationRequest:
    paper_title: str
    section_title: str | None
    block_type: str
    previous_text: str | None
    current_text: str
    next_text: str | None
    source_language: str
    target_language: str
    glossary: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TranslationResult:
    translated_text: str
    provider: str
    model: str


@dataclass(frozen=True)
class BatchTranslationItem:
    block_id: uuid.UUID
    block_type: str
    source_text: str
    protected_text: str
    relevant_glossary: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BatchTranslationRequest:
    paper_title: str
    section_title: str | None
    source_language: str
    target_language: str
    items: tuple[BatchTranslationItem, ...]
    glossary: dict[str, str] = field(default_factory=dict)
    external_previous_context: str | None = None
    external_next_context: str | None = None


@dataclass(frozen=True)
class BatchTranslationResultItem:
    block_id: uuid.UUID
    translated_text: str


@dataclass(frozen=True)
class BatchTranslationResult:
    items: tuple[BatchTranslationResultItem, ...]
    provider: str
    model: str
    usage: dict[str, int] | None = None
