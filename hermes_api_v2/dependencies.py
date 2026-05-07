"""Shared API dependencies for Hermes FastAPI v2."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from hermes_api_v2.core.database import get_db_session, get_redis
from hermes_api_v2.core.security import decode_fastapi_token

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    try:
        payload = decode_fastapi_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc

    user_id = str(payload.get("sub") or "").strip()
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
        )

    row = (
        await db.execute(
            text(
                """
                SELECT id, email, tier
                FROM users
                WHERE CAST(id AS text) = :user_id
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return {
        "id": int(row["id"]),
        "email": row["email"],
        "tier": row["tier"],
    }


async def get_redis_client():
    return await get_redis()

