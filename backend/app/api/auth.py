from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import client_ip, current_user
from app.core.errors import AppError
from app.core.ratelimit import count, hit, incr
from app.core.security import DUMMY_HASH, hash_password, verify_password
from app.core.sessions import clear_session_cookie, create_session, revoke_session, set_session_cookie
from app.api.me import me_out
from app.db import get_db
from app.models import User
from app.schemas.auth import LoginIn, MeOut, RegisterIn
from app.services.economy import apply_delta
from app.services.settings import get_setting

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.post("/register", status_code=201, response_model=MeOut)
async def register(
    body: RegisterIn, request: Request, response: Response, db: DbDep
) -> MeOut:
    ip = client_ip(request)
    await hit(f"rl:register:{ip}", limit=5, window_s=3600)
    login_taken = await db.scalar(select(User.id).where(User.login == body.login))
    if login_taken is not None:
        raise AppError(409, "LOGIN_TAKEN", "Логин уже занят")
    email_taken = await db.scalar(select(User.id).where(User.email == body.email))
    if email_taken is not None:
        raise AppError(409, "EMAIL_TAKEN", "Email уже занят")
    user = User(
        login=body.login,
        email=body.email,
        password_hash=hash_password(body.password),
        balance=0,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        constraint = getattr(exc.orig, "constraint_name", "") or ""
        if constraint.endswith("uq_users_login"):
            raise AppError(409, "LOGIN_TAKEN", "Логин уже занят") from exc
        if constraint.endswith("uq_users_email"):
            raise AppError(409, "EMAIL_TAKEN", "Email уже занят") from exc
        raise
    starting_balance = int(await get_setting(db, "starting_balance"))
    await apply_delta(db, user.id, starting_balance, "signup_bonus")
    token = await create_session(
        db, user.id, ip, request.headers.get("user-agent")
    )
    set_session_cookie(response, token)
    cooldown_h = int(await get_setting(db, "daily_bonus_cooldown_h"))
    return me_out(user, cooldown_h)


@router.post("/login", status_code=200, response_model=MeOut)
async def login(
    body: LoginIn, request: Request, response: Response, db: DbDep
) -> MeOut:
    ip = client_ip(request)
    await hit(f"rl:login:{ip}", limit=10, window_s=60)
    loginfail_key = f"rl:loginfail:{body.login.lower()}"
    if await count(loginfail_key) >= 5:
        raise AppError(429, "RATE_LIMITED", "Слишком много попыток, подождите")
    user = await db.scalar(select(User).where(User.login == body.login))
    if user is None:
        verify_password(DUMMY_HASH, body.password)
        raise AppError(401, "INVALID_CREDENTIALS", "Неверный логин или пароль")
    if not verify_password(user.password_hash, body.password):
        await incr(loginfail_key, 900)
        raise AppError(401, "INVALID_CREDENTIALS", "Неверный логин или пароль")
    if user.is_banned:
        raise AppError(403, "USER_BANNED", "Аккаунт заблокирован")
    token = await create_session(db, user.id, ip, request.headers.get("user-agent"))
    set_session_cookie(response, token)
    cooldown_h = int(await get_setting(db, "daily_bonus_cooldown_h"))
    return me_out(user, cooldown_h)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: DbDep, user=Depends(current_user)) -> None:
    session_id = getattr(request.state, "session_id", None)
    await revoke_session(db, session_id)
    clear_session_cookie(response)
