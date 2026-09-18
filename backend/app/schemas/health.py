from typing import Literal

from pydantic import BaseModel

ServiceStatus = Literal["healthy", "unhealthy"]


class HealthResponse(BaseModel):
    status: ServiceStatus
    services: dict[str, ServiceStatus]
