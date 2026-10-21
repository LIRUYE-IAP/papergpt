from types import SimpleNamespace
import uuid

import httpx
import openai
import pytest

from app.ai.errors import (
    AIAuthenticationError,
    AIConnectionError,
    AIInvalidRequestError,
    AIInvalidBatchResponseError,
    AIModelNotFoundError,
    AIPermissionError,
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
    AIUnavailableError,
)
from app.ai.providers.openai_provider import (
    OPENAI_REQUEST_TIMEOUT_SECONDS,
    OpenAITranslationProvider,
)
from app.ai.types import BatchTranslationItem, BatchTranslationRequest, TranslationRequest


REQUEST = TranslationRequest(
    paper_title="Safe test paper",
    section_title="Introduction",
    block_type="PARAGRAPH",
    previous_text=None,
    current_text="Translate this test paragraph.",
    next_text=None,
    source_language="en",
    target_language="zh-CN",
)

BATCH_IDS = (
    uuid.UUID("11111111-1111-1111-1111-111111111111"),
    uuid.UUID("22222222-2222-2222-2222-222222222222"),
)
BATCH_REQUEST = BatchTranslationRequest(
    paper_title="Safe test paper",
    section_title="Introduction",
    source_language="en",
    target_language="zh-CN",
    items=(
        BatchTranslationItem(
            block_id=BATCH_IDS[0],
            block_type="PARAGRAPH",
            source_text="First",
            protected_text="First",
        ),
        BatchTranslationItem(
            block_id=BATCH_IDS[1],
            block_type="PARAGRAPH",
            source_text="Second",
            protected_text="Second",
        ),
    ),
)


def status_error(error_type, status: int, *, headers: dict[str, str] | None = None):
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(status, headers=headers, request=request)
    return error_type("provider request failed", response=response, body=None)


def translated_error(exc: Exception) -> AIProviderError:
    provider = OpenAITranslationProvider(api_key="test-only-placeholder", model="test-model")

    def raise_error(**_kwargs):
        raise exc

    provider._client = SimpleNamespace(  # type: ignore[assignment]
        responses=SimpleNamespace(create=raise_error)
    )
    with pytest.raises(AIProviderError) as captured:
        provider.translate(REQUEST)
    return captured.value


@pytest.mark.parametrize(
    ("sdk_error", "expected_type"),
    (
        (status_error(openai.AuthenticationError, 401), AIAuthenticationError),
        (status_error(openai.PermissionDeniedError, 403), AIPermissionError),
        (status_error(openai.BadRequestError, 400), AIInvalidRequestError),
        (status_error(openai.NotFoundError, 404), AIModelNotFoundError),
        (status_error(openai.InternalServerError, 500), AIUnavailableError),
    ),
)
def test_openai_status_error_mapping(sdk_error, expected_type) -> None:
    assert isinstance(translated_error(sdk_error), expected_type)


def test_openai_rate_limit_mapping_uses_safe_retry_after_header() -> None:
    error = translated_error(
        status_error(openai.RateLimitError, 429, headers={"Retry-After": "120.2"})
    )
    assert isinstance(error, AIRateLimitError)
    assert error.retry_after_seconds == 121
    assert error.code == "AI_RATE_LIMITED"
    assert "provider request failed" not in str(error)


def test_openai_timeout_and_connection_mapping() -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    assert isinstance(translated_error(openai.APITimeoutError(request)), AITimeoutError)
    assert isinstance(
        translated_error(openai.APIConnectionError(request=request)),
        AIConnectionError,
    )


def test_openai_generic_sdk_and_non_sdk_error_mapping() -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    generic_sdk = openai.APIError("provider detail", request, body=None)
    assert type(translated_error(generic_sdk)) is AIProviderError
    assert type(translated_error(RuntimeError("internal detail"))) is AIProviderError


def test_openai_client_has_bounded_timeout_and_no_automatic_retries() -> None:
    provider = OpenAITranslationProvider(api_key="test-only-placeholder", model="test-model")
    assert provider._client.timeout == OPENAI_REQUEST_TIMEOUT_SECONDS
    assert provider._client.max_retries == 0


def test_openai_batch_uses_structured_responses_and_preserves_uuid_order_independence() -> None:
    provider = OpenAITranslationProvider(api_key="test-only-placeholder", model="test-model")
    captured: dict[str, object] = {}

    def parse_response(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            output_parsed=SimpleNamespace(
                translations=[
                    SimpleNamespace(block_id=BATCH_IDS[1], translated_text="第二"),
                    SimpleNamespace(block_id=BATCH_IDS[0], translated_text="第一"),
                ]
            )
        )

    provider._client = SimpleNamespace(  # type: ignore[assignment]
        responses=SimpleNamespace(parse=parse_response)
    )
    result = provider.translate_batch(BATCH_REQUEST)

    assert captured["model"] == "test-model"
    assert captured["store"] is False
    assert captured["text_format"].__name__ == "_StructuredBatchTranslationResponse"
    assert "11111111-1111-1111-1111-111111111111" in captured["input"]
    assert [item.block_id for item in result.items] == [BATCH_IDS[1], BATCH_IDS[0]]


def test_openai_batch_rejects_missing_structured_parse_result() -> None:
    provider = OpenAITranslationProvider(api_key="test-only-placeholder", model="test-model")
    provider._client = SimpleNamespace(  # type: ignore[assignment]
        responses=SimpleNamespace(
            parse=lambda **_kwargs: SimpleNamespace(output_parsed=None)
        )
    )
    with pytest.raises(AIInvalidBatchResponseError):
        provider.translate_batch(BATCH_REQUEST)
