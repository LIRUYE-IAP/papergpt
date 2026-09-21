from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math

from openai import (
    APIConnectionError as OpenAIAPIConnectionError,
    APIError as OpenAIAPIError,
    APIStatusError as OpenAIAPIStatusError,
    APITimeoutError as OpenAIAPITimeoutError,
    AuthenticationError as OpenAIAuthenticationError,
    BadRequestError as OpenAIBadRequestError,
    InternalServerError as OpenAIInternalServerError,
    NotFoundError as OpenAINotFoundError,
    OpenAI,
    PermissionDeniedError as OpenAIPermissionDeniedError,
    RateLimitError as OpenAIRateLimitError,
)

from app.ai.errors import (
    AIAuthenticationError,
    AIConnectionError,
    AIInvalidRequestError,
    AIModelNotFoundError,
    AIPermissionError,
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
    AIUnavailableError,
)
from app.ai.prompts import (
    ACADEMIC_TRANSLATION_INSTRUCTIONS,
    build_academic_translation_input,
)
from app.ai.providers.base import TranslationProvider, TranslationProviderError
from app.ai.types import TranslationRequest, TranslationResult

OPENAI_REQUEST_TIMEOUT_SECONDS = 60.0


def _retry_after_seconds(exc: OpenAIAPIStatusError) -> int | None:
    response = getattr(exc, "response", None)
    if response is None:
        return None
    value = response.headers.get("retry-after")
    if not value:
        return None
    try:
        seconds = math.ceil(float(value))
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            seconds = math.ceil(
                (retry_at - datetime.now(timezone.utc)).total_seconds()
            )
        except (TypeError, ValueError, OverflowError):
            return None
    return max(0, seconds)


def _map_openai_error(exc: Exception) -> AIProviderError:
    status_code = getattr(exc, "status_code", None)
    if isinstance(exc, OpenAIRateLimitError):
        return AIRateLimitError(
            retry_after_seconds=_retry_after_seconds(exc),
            provider_status=status_code,
        )
    if isinstance(exc, OpenAIAuthenticationError):
        return AIAuthenticationError(provider_status=status_code)
    if isinstance(exc, OpenAIPermissionDeniedError):
        return AIPermissionError(provider_status=status_code)
    if isinstance(exc, OpenAIBadRequestError):
        return AIInvalidRequestError(provider_status=status_code)
    if isinstance(exc, OpenAINotFoundError):
        return AIModelNotFoundError(provider_status=status_code)
    if isinstance(exc, OpenAIAPITimeoutError):
        return AITimeoutError()
    if isinstance(exc, OpenAIAPIConnectionError):
        return AIConnectionError()
    if isinstance(exc, OpenAIInternalServerError):
        return AIUnavailableError(provider_status=status_code)
    if isinstance(exc, OpenAIAPIStatusError) and (status_code or 0) >= 500:
        return AIUnavailableError(provider_status=status_code)
    return AIProviderError(provider_status=status_code)


class OpenAITranslationProvider(TranslationProvider):
    name = "openai"

    def __init__(self, *, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for the OpenAI provider")
        self.model = model
        self._client = OpenAI(
            api_key=api_key,
            timeout=OPENAI_REQUEST_TIMEOUT_SECONDS,
            max_retries=0,
        )

    def translate(self, request: TranslationRequest) -> TranslationResult:
        try:
            response = self._client.responses.create(
                model=self.model,
                instructions=ACADEMIC_TRANSLATION_INSTRUCTIONS,
                input=build_academic_translation_input(request),
                store=False,
            )
        except OpenAIAPIError as exc:
            raise _map_openai_error(exc) from exc
        except Exception as exc:
            raise AIProviderError() from exc

        translated_text = response.output_text.strip()
        if not translated_text:
            raise TranslationProviderError()
        return TranslationResult(
            translated_text=translated_text,
            provider=self.name,
            model=self.model,
        )
