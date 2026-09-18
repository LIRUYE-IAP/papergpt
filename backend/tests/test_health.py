import asyncio

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.schemas.health import HealthResponse


async def get_health() -> tuple[int, dict]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
    return response.status_code, response.json()


def test_health(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.health.get_health_status",
        lambda: HealthResponse(
            status="healthy",
            services={"api": "healthy", "postgresql": "healthy", "redis": "healthy"},
        ),
    )

    status_code, body = asyncio.run(get_health())

    assert status_code == 200
    assert body == {
        "status": "healthy",
        "services": {
            "api": "healthy",
            "postgresql": "healthy",
            "redis": "healthy",
        },
    }
