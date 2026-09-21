from abc import ABC, abstractmethod

from app.ai.types import TranslationRequest, TranslationResult
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
