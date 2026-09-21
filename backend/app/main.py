from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Range"],
    expose_headers=[
        "Accept-Ranges",
        "Content-Disposition",
        "Content-Length",
        "Content-Range",
    ],
)
app.include_router(api_router, prefix=settings.api_v1_prefix)
