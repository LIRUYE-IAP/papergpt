import uuid
from datetime import datetime, timedelta, timezone

import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash

from app.core.config import settings

ALGORITHM = "HS256"
password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    return password_hash.verify(password, stored_hash)


def create_access_token(user_id: uuid.UUID) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_expiration_minutes
    )
    return jwt.encode(
        {"sub": str(user_id), "exp": expires_at},
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def decode_access_token(token: str) -> uuid.UUID | None:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
        return uuid.UUID(payload["sub"])
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        return None
