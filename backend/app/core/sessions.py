from datetime import UTC, datetime, timedelta

from fastapi import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import hash_token, new_session_token
from app.models import Session as SessionModel
from app.models import Session, User

_LAST_SEEN_UPDATE_S = 60


async def create_session(
    db: AsyncSession, user_id: int, ip: str | None, user_agent: str | None
) -> str:
    token = new_session_token()
    now = datetime.now(UTC)
    db.add(
        Session(
            user_id=user_id,
            token_hash=hash_token(token),
            created_at=now,
            expires_at=now + timedelta(days=settings.session_ttl_days),
            last_seen_at=now,
            ip=ip,
            user_agent=(user_agent or "")[:512],
        )
    )
    return token


async def resolve_session(
    db: AsyncSession, token: str
) -> tuple[SessionModel, User] | None:
    row = await db.scalar(select(SessionModel).where(SessionModel.token_hash == hash_token(token)))
    if row is None:
        return None
    now = datetime.now(UTC)
    if row.revoked_at is not None or row.expires_at <= now:
        return None
    if (now - row.last_seen_at).total_seconds() > _LAST_SEEN_UPDATE_S:
        row.last_seen_at = now
    user = await db.get(User, row.user_id)
    if user is None:
        return None
    return row, user


async def revoke_session(db: AsyncSession, session_id: int) -> None:
    row = await db.get(SessionModel, session_id)
    if row is not None and row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)


async def revoke_all(
    db: AsyncSession, user_id: int, except_session_id: int | None = None
) -> None:
    rows = await db.scalars(select(SessionModel).where(SessionModel.user_id == user_id))
    now = datetime.now(UTC)
    for row in rows:
        if row.id != except_session_id and row.revoked_at is None:
            row.revoked_at = now


def _ttl_seconds() -> int:
    return settings.session_ttl_days * 24 * 60 * 60


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.cookie_name,
        token,
        max_age=_ttl_seconds(),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )
