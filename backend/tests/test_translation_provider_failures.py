from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import func, select

from app.ai.errors import (
    AIAuthenticationError,
    AIConnectionError,
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
)
from app.ai.providers.base import TranslationProvider
from app.ai.types import (
    BatchTranslationRequest,
    BatchTranslationResult,
    BatchTranslationResultItem,
    TranslationRequest,
    TranslationResult,
)
from app.db.session import SessionLocal
from app.models.paper import Paper
from app.models.translation import Translation, TranslationStatus
from tests.conftest import ApiClient
from tests.helpers import (
    academic_pdf_bytes,
    auth_headers,
    login_user,
    register_user,
    upload_pdf_bytes,
)


@dataclass
class ControlledProvider(TranslationProvider):
    failure: AIProviderError | None = None
    fail_after: int = 0
    calls: int = 0

    name = "controlled-test"
    model = "controlled-test-v1"

    def translate(self, request: TranslationRequest) -> TranslationResult:
        self.calls += 1
        if self.failure is not None and self.calls > self.fail_after:
            raise self.failure
        return TranslationResult(
            translated_text=f"[controlled] {request.current_text}",
            provider=self.name,
            model=self.model,
        )

    def translate_batch(
        self, request: BatchTranslationRequest
    ) -> BatchTranslationResult:
        self.calls += 1
        if self.failure is not None and self.calls > self.fail_after:
            raise self.failure
        return BatchTranslationResult(
            items=tuple(
                BatchTranslationResultItem(
                    block_id=item.block_id,
                    translated_text=f"[controlled] {item.protected_text}",
                )
                for item in request.items
            ),
            provider=self.name,
            model=self.model,
        )


def parsed_paper(client: ApiClient, email: str) -> tuple[str, dict, str]:
    register_user(client, email)
    token = login_user(client, email)
    paper = upload_pdf_bytes(client, token, academic_pdf_bytes(), "provider.pdf")
    assert client.post(
        f"/api/v1/papers/{paper['id']}/parse", headers=auth_headers(token)
    ).status_code == 200
    blocks = client.get(
        f"/api/v1/papers/{paper['id']}/blocks", headers=auth_headers(token)
    ).json()
    block_id = next(block["id"] for block in blocks if block["is_translatable"])
    return token, paper, block_id


def install_provider(monkeypatch: pytest.MonkeyPatch, provider: ControlledProvider) -> None:
    monkeypatch.setattr(
        "app.services.translations.get_translation_provider",
        lambda: provider,
    )


def test_single_block_rate_limit_is_structured_failed_and_retry_succeeds(
    client: ApiClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token, paper, block_id = parsed_paper(
        client, "provider-rate-limit@phase1.papergpt.dev"
    )
    provider = ControlledProvider(
        failure=AIRateLimitError(retry_after_seconds=120)
    )
    install_provider(monkeypatch, provider)

    response = client.post(
        f"/api/v1/papers/{paper['id']}/blocks/{block_id}/translate",
        headers=auth_headers(token),
        json={"target_language": "zh-CN"},
    )

    assert response.status_code == 429
    assert response.json() == {
        "error": {
            "code": "AI_RATE_LIMITED",
            "message": "Translation service rate limit reached.",
            "retry_after_seconds": 120,
            "partial_result": None,
        }
    }
    assert "key" not in response.text.casefold()
    with SessionLocal() as db:
        failed = db.scalar(
            select(Translation).where(Translation.block_id == block_id)
        )
        assert failed is not None
        assert failed.status == TranslationStatus.FAILED
        assert failed.error_message == "Translation service rate limit reached."
        assert not db.scalar(
            select(func.count(Translation.id)).where(
                Translation.paper_id == paper["id"],
                Translation.status == TranslationStatus.PROCESSING,
            )
        )

    provider.failure = None
    provider.calls = 0
    retry = client.post(
        f"/api/v1/papers/{paper['id']}/blocks/{block_id}/translate",
        headers=auth_headers(token),
        json={"target_language": "zh-CN"},
    )
    assert retry.status_code == 200
    assert retry.json()["translation"]["status"] == "COMPLETED"
    assert retry.json()["translation"]["error_message"] is None


@pytest.mark.parametrize(
    ("failure", "expected_status", "expected_code"),
    (
        (AITimeoutError(), 504, "AI_TIMEOUT"),
        (AIConnectionError(), 503, "AI_CONNECTION_FAILED"),
        (AIAuthenticationError(), 502, "AI_AUTHENTICATION_FAILED"),
        (AIProviderError(), 502, "TRANSLATION_FAILED"),
    ),
)
def test_single_block_provider_failure_http_mapping(
    client: ApiClient,
    monkeypatch: pytest.MonkeyPatch,
    failure: AIProviderError,
    expected_status: int,
    expected_code: str,
) -> None:
    token, paper, block_id = parsed_paper(
        client, f"provider-{expected_code.lower()}@phase1.papergpt.dev"
    )
    install_provider(monkeypatch, ControlledProvider(failure=failure))
    response = client.post(
        f"/api/v1/papers/{paper['id']}/blocks/{block_id}/translate",
        headers=auth_headers(token),
        json={"target_language": "zh-CN"},
    )
    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
    if isinstance(failure, AIAuthenticationError):
        assert response.status_code != 401
    with SessionLocal() as db:
        assert not db.scalar(
            select(func.count(Translation.id)).where(
                Translation.paper_id == paper["id"],
                Translation.status == TranslationStatus.PROCESSING,
            )
        )


def test_whole_paper_provider_wide_failure_stops_and_preserves_partial_success(
    client: ApiClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token, paper, _ = parsed_paper(
        client, "provider-whole-rate@phase1.papergpt.dev"
    )
    provider = ControlledProvider(
        failure=AIRateLimitError(retry_after_seconds=60),
        fail_after=1,
    )
    install_provider(monkeypatch, provider)

    response = client.post(
        f"/api/v1/papers/{paper['id']}/translate",
        headers=auth_headers(token),
        json={"target_language": "zh-CN"},
    )

    assert response.status_code == 429
    error = response.json()["error"]
    assert error["code"] == "AI_RATE_LIMITED"
    assert error["partial_result"]["translated_count"] > 0
    assert error["partial_result"]["failed_count"] > 0
    assert error["partial_result"]["remaining_count"] > 0
    assert error["partial_result"]["batch_count"] == 2
    assert error["partial_result"]["provider_request_count"] == 2
    assert provider.calls == 2
    with SessionLocal() as db:
        completed = db.scalar(
            select(func.count(Translation.id)).where(
                Translation.paper_id == paper["id"],
                Translation.status == TranslationStatus.COMPLETED,
            )
        )
        failed = db.scalar(
            select(func.count(Translation.id)).where(
                Translation.paper_id == paper["id"],
                Translation.status == TranslationStatus.FAILED,
            )
        )
        processing = db.scalar(
            select(func.count(Translation.id)).where(
                Translation.paper_id == paper["id"],
                Translation.status == TranslationStatus.PROCESSING,
            )
        )
        saved_paper = db.get(Paper, paper["id"])
    assert completed == error["partial_result"]["translated_count"]
    assert failed == error["partial_result"]["failed_count"]
    assert processing == 0
    assert saved_paper is not None
    assert saved_paper.translation_status == "FAILED"
