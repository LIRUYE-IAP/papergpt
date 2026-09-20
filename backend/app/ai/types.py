from dataclasses import dataclass, field


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
