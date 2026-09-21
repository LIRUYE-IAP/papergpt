import asyncio
from collections.abc import Generator
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import delete

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.user import User

TEST_EMAIL_SUFFIX = "@phase1.papergpt.dev"


class ApiClient:
    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        async def send() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("DELETE", path, **kwargs)


def remove_test_users() -> None:
    with SessionLocal() as db:
        db.execute(delete(User).where(User.email.like(f"%{TEST_EMAIL_SUFFIX}")))
        db.commit()


@pytest.fixture(autouse=True)
def isolated_test_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[None, None, None]:
    remove_test_users()
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    monkeypatch.setattr(settings, "ai_provider", "mock")
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "papergpt_test_ai_failure", None)
    yield
    remove_test_users()


@pytest.fixture
def client() -> ApiClient:
    return ApiClient()
