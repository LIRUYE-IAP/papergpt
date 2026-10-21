from abc import ABC, abstractmethod

from app.ai.types import (
    BatchTranslationRequest,
    BatchTranslationResult,
    TranslationRequest,
    TranslationResult,
)
from app.ai.errors import AIProviderError


class TranslationProviderError(AIProviderError):
    """A provider failed to return a usable translation."""

    safe_message = "Translation provider failed."


class TranslationProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def translate(self, request: TranslationRequest) -> TranslationResult:
        """Translate only request.current_text, using adjacent text as context."""

    @abstractmethod
    def translate_batch(
        self, request: BatchTranslationRequest
    ) -> BatchTranslationResult:
        """Translate multiple blocks and preserve their stable UUID mapping."""
