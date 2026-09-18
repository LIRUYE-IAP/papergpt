from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import engine
from app.schemas.health import HealthResponse, ServiceStatus


def check_database() -> ServiceStatus:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return "unhealthy"
    return "healthy"


def check_redis() -> ServiceStatus:
    try:
        with Redis.from_url(settings.redis_url, socket_connect_timeout=2) as client:
            client.ping()
    except RedisError:
        return "unhealthy"
    return "healthy"


def get_health_status() -> HealthResponse:
    services: dict[str, ServiceStatus] = {
        "api": "healthy",
        "postgresql": check_database(),
        "redis": check_redis(),
    }
    overall_status: ServiceStatus = (
        "healthy" if all(value == "healthy" for value in services.values()) else "unhealthy"
    )
    return HealthResponse(status=overall_status, services=services)
