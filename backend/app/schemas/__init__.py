from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.schemas.health import HealthResponse
from app.schemas.paper import PaperResponse

__all__ = [
    "HealthResponse",
    "LoginRequest",
    "PaperResponse",
    "RegisterRequest",
    "TokenResponse",
    "UserResponse",
]
