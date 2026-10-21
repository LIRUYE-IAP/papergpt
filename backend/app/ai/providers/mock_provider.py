from app.ai.errors import (
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
    AIUnavailableError,
)
from app.ai.providers.base import TranslationProvider, TranslationProviderError
from app.ai.types import (
    BatchTranslationRequest,
    BatchTranslationResult,
    BatchTranslationResultItem,
    TranslationRequest,
    TranslationResult,
)


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
        self._raise_configured_failure()
        if self.fail_on and self.fail_on in request.current_text:
            raise TranslationProviderError()
        language = request.target_language
        glossary_suffix = self._glossary_suffix(request.glossary)
        return TranslationResult(
            translated_text=(
                f"[{language} academic mock] {request.current_text}{glossary_suffix}"
            ),
            provider=self.name,
            model=self.model,
        )

    def translate_batch(
        self, request: BatchTranslationRequest
    ) -> BatchTranslationResult:
        self.calls += 1
        self._raise_configured_failure()
        results = [
            BatchTranslationResultItem(
                block_id=item.block_id,
                translated_text=(
                    ""
                    if self.fail_on and self.fail_on in item.source_text
                    else (
                        f"[{request.target_language} academic mock] "
                        f"{item.protected_text}"
                        f"{self._glossary_suffix(item.relevant_glossary)}"
                    )
                ),
            )
            for item in request.items
        ]

        if self.failure_mode in {"reverse", "reverse_order", "different_order"}:
            results.reverse()
        elif self.failure_mode == "random_order" and len(results) > 1:
            results = results[1:] + results[:1]
        elif self.failure_mode == "missing_id" and results:
            results.pop()
        elif self.failure_mode == "duplicate_id" and results:
            results.append(results[0])
        elif self.failure_mode == "unknown_id":
            from uuid import UUID

            results.append(
                BatchTranslationResultItem(
                    block_id=UUID("00000000-0000-0000-0000-000000000001"),
                    translated_text="unknown",
                )
            )
        elif self.failure_mode == "protected_token_corruption":
            for index, result in enumerate(results):
                if "__PAPERGPT_" in result.translated_text:
                    results[index] = BatchTranslationResultItem(
                        block_id=result.block_id,
                        translated_text=result.translated_text.replace(
                            "__PAPERGPT_", "__CORRUPTED_", 1
                        ),
                    )
                    break

        return BatchTranslationResult(
            items=tuple(results),
            provider=self.name,
            model=self.model,
        )

    def _raise_configured_failure(self) -> None:
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

    @staticmethod
    def _glossary_suffix(glossary: dict[str, str]) -> str:
        if glossary:
            pairs = "; ".join(
                f"{source}={target}"
                for source, target in glossary.items()
            )
            return f" [glossary: {pairs}]"
        return ""
