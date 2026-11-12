"""Environment-configured admin login and bearer-token protection."""

from __future__ import annotations

import hmac
import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field

ALGORITHM = "HS256"
TOKEN_HOURS = 8
bearer = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


def _secret() -> str:
    return os.getenv("SECRET_KEY", "change-this-to-a-random-secret-key-in-production")


def login_admin(credentials: LoginRequest) -> dict:
    username = os.getenv("ADMIN_USERNAME", "")
    password = os.getenv("ADMIN_PASSWORD", "")
    if not username or not password:
        raise HTTPException(status_code=503, detail="Admin login is not configured on the server")
    if not (hmac.compare_digest(credentials.username, username)
            and hmac.compare_digest(credentials.password, password)):
        raise HTTPException(status_code=401, detail="Invalid admin username or password")

    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": username, "role": "admin", "iat": now, "exp": now + timedelta(hours=TOKEN_HOURS)},
        _secret(), algorithm=ALGORITHM,
    )
    return {"access_token": token, "token_type": "bearer", "username": username, "expires_in": TOKEN_HOURS * 3600}


async def require_admin(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin login required")
    try:
        payload = jwt.decode(credentials.credentials, _secret(), algorithms=[ALGORITHM])
        username = payload.get("sub")
        if payload.get("role") != "admin" or not username:
            raise JWTError("Invalid token claims")
        return str(username)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin session expired; sign in again") from exc
