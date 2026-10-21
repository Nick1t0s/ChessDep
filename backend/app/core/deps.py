from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.errors import AppError
from app.core.sessions import resolve_session
from app.db import get_db
from app.models import User

_UNAUTHENTICATED = AppError(401, "UNAUTHENTICATED", "Требуется вход")


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    token = request.cookies.get(settings.cookie_name)
    if not token:
        raise _UNAUTHENTICATED
    resolved = await resolve_session(db, token)
    if resolved is None:
        raise _UNAUTHENTICATED
    row, user = resolved
    if user.is_banned:
        raise AppError(403, "USER_BANNED", "Аккаунт заблокирован")
    request.state.session_id = row.id
    return user


async def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise AppError(403, "FORBIDDEN", "Недостаточно прав")
    return user


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
