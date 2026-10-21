from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AIErrorMetadata:
    code: str
    message: str
    http_status: int
    retry_after_seconds: int | None = None


class TranslationExecutionError(RuntimeError):
    code = "TRANSLATION_FAILED"
    safe_message = "Translation failed."
    http_status = 502
    stop_batch = False

    def __init__(
        self,
        *,
        retry_after_seconds: int | None = None,
        provider_status: int | None = None,
    ) -> None:
        super().__init__(self.safe_message)
        self.retry_after_seconds = retry_after_seconds
        self.provider_status = provider_status

    @property
    def metadata(self) -> AIErrorMetadata:
        return AIErrorMetadata(
            code=self.code,
            message=self.safe_message,
            http_status=self.http_status,
            retry_after_seconds=self.retry_after_seconds,
        )


class AIProviderError(TranslationExecutionError):
    """A provider failed without exposing SDK-specific exception details."""


class AIRateLimitError(AIProviderError):
    code = "AI_RATE_LIMITED"
    safe_message = "Translation service rate limit reached."
    http_status = 429
    stop_batch = True


class AIAuthenticationError(AIProviderError):
    code = "AI_AUTHENTICATION_FAILED"
    safe_message = "Translation provider authentication failed."
    http_status = 502
    stop_batch = True


class AIPermissionError(AIProviderError):
    code = "AI_PERMISSION_DENIED"
    safe_message = "Translation provider permission denied."
    http_status = 502
    stop_batch = True


class AIInvalidRequestError(AIProviderError):
    code = "AI_INVALID_REQUEST"
    safe_message = "Translation provider rejected the request."
    http_status = 502


class AIModelNotFoundError(AIProviderError):
    code = "AI_MODEL_UNAVAILABLE"
    safe_message = "Translation model is unavailable."
    http_status = 502
    stop_batch = True


class AITimeoutError(AIProviderError):
    code = "AI_TIMEOUT"
    safe_message = "Translation provider request timed out."
    http_status = 504
    stop_batch = True


class AIConnectionError(AIProviderError):
    code = "AI_CONNECTION_FAILED"
    safe_message = "Translation provider connection failed."
    http_status = 503
    stop_batch = True


class AIUnavailableError(AIProviderError):
    code = "AI_SERVICE_UNAVAILABLE"
    safe_message = "Translation provider is temporarily unavailable."
    http_status = 503
    stop_batch = True


class AIInvalidBatchResponseError(AIProviderError):
    code = "AI_INVALID_BATCH_RESPONSE"
    safe_message = "Translation provider returned an invalid batch response."
    http_status = 502
    stop_batch = True


class TranslationFailedError(TranslationExecutionError):
    """A non-provider translation pipeline step failed safely."""
