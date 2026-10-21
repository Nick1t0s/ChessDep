from collections.abc import AsyncIterator
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Setting
from app.redis import redis_client
from app.services import settings as settings_service
from app.services.settings import DEFAULTS

_TRUNCATE_SQL = text("TRUNCATE users, sessions, ledger, admin_audit RESTART IDENTITY CASCADE")


@pytest_asyncio.fixture(autouse=True)
async def clean_db() -> AsyncIterator[None]:
    async with SessionLocal() as db:
        async with db.begin():
            await db.execute(_TRUNCATE_SQL)
            await db.execute(delete(Setting))
            rows: list[dict[str, Any]] = [
                {"key": key, "value": value} for key, value in DEFAULTS.items()
            ]
            await db.execute(insert(Setting).values(rows))
    settings_service.clear_cache()
    await redis_client.flushdb()
    yield
    await redis_client.aclose()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "http://test"}
    ) as client:
        yield client


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def register(
    client: AsyncClient,
    login: str = "alice",
    email: str | None = None,
    password: str = "password123",
) -> object:
    payload = {
        "login": login,
        "email": email if email is not None else f"{login}@example.com",
        "password": password,
    }
    return await client.post("/api/v1/auth/register", json=payload)
