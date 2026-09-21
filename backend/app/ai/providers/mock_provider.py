from app.ai.errors import (
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
    AIUnavailableError,
)
from app.ai.providers.base import TranslationProvider, TranslationProviderError
from app.ai.types import TranslationRequest, TranslationResult


class MockTranslationProvider(TranslationProvider):
    """Deterministic, zero-cost provider for local development and tests."""

    name = "mock"
    model = "deterministic-academic-v1"

    def __init__(
        self,
        *,
        fail_on: str | None = None,
        failure_mode: str | None = None,
    ) -> None:
        self.fail_on = fail_on
        self.failure_mode = failure_mode
        self.calls = 0

    def translate(self, request: TranslationRequest) -> TranslationResult:
        self.calls += 1
        if self.failure_mode == "rate_limit":
            raise AIRateLimitError(retry_after_seconds=120)
        if self.failure_mode == "rate_limit_after_one" and self.calls > 1:
            raise AIRateLimitError(retry_after_seconds=120)
        if self.failure_mode == "timeout":
            raise AITimeoutError()
        if self.failure_mode == "unavailable":
            raise AIUnavailableError()
        if self.failure_mode == "generic":
            raise AIProviderError()
        if self.fail_on and self.fail_on in request.current_text:
            raise TranslationProviderError()
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
