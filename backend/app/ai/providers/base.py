from abc import ABC, abstractmethod

from app.ai.types import TranslationRequest, TranslationResult


class TranslationProviderError(RuntimeError):
    """A provider failed to return a usable translation."""


class TranslationProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def translate(self, request: TranslationRequest) -> TranslationResult:
        """Translate only request.current_text, using adjacent text as context."""
