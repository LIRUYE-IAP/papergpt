from fastapi import APIRouter, Response, status

from app.schemas.health import HealthResponse
from app.services.health import get_health_status

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(response: Response) -> HealthResponse:
    health_status = get_health_status()
    if health_status.status != "healthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return health_status
