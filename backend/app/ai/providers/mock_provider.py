from app.ai.providers.base import TranslationProvider, TranslationProviderError
from app.ai.types import TranslationRequest, TranslationResult


class MockTranslationProvider(TranslationProvider):
    """Deterministic, zero-cost provider for local development and tests."""

    name = "mock"
    model = "deterministic-academic-v1"

    def __init__(self, *, fail_on: str | None = None) -> None:
        self.fail_on = fail_on

    def translate(self, request: TranslationRequest) -> TranslationResult:
        if self.fail_on and self.fail_on in request.current_text:
            raise TranslationProviderError(
                f"Mock provider rejected text containing {self.fail_on!r}"
            )
        language = request.target_language
        glossary_suffix = ""
        if request.glossary:
            pairs = "; ".join(
                f"{source}={target}"
                for source, target in request.glossary.items()
            )
            glossary_suffix = f" [glossary: {pairs}]"
        return TranslationResult(
            translated_text=(
                f"[{language} academic mock] {request.current_text}{glossary_suffix}"
            ),
            provider=self.name,
            model=self.model,
        )
