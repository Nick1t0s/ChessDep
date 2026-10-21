import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.errors import AppError
from app.core.security import hash_password
from app.db import SessionLocal
from app.models import Ledger, User
from app.services.economy import apply_delta
from app.services.settings import DEFAULTS
from tests.conftest import register


async def _seed_user(db, login: str, balance: int) -> int:
    async with db.begin():
        user = User(
            login=login,
            email=f"{login}@example.com",
            password_hash=hash_password("password123"),
            balance=balance,
        )
        db.add(user)
        await db.flush()
        db.add(
            Ledger(
                user_id=user.id,
                delta=balance,
                balance_after=balance,
                reason="signup_bonus",
            )
        )
        return user.id


async def test_apply_delta_never_negative(db) -> None:
    user_id = await _seed_user(db, "neguser", 1000)
    balance_before = 1000

    async with db.begin():
        _ = await db.scalar(select(func.count()).select_from(Ledger))

    with pytest.raises(AppError) as excinfo:
        async with db.begin():
            await apply_delta(db, user_id, -2000, "daily_bonus")
    assert excinfo.value.code == "INSUFFICIENT_FUNDS"

    async with SessionLocal() as check:
        user = await check.get(User, user_id)
        ledger_count = await check.scalar(select(func.count()).select_from(Ledger))
        ledger_sum = await check.scalar(
            select(func.coalesce(func.sum(Ledger.delta), 0)).where(Ledger.user_id == user_id)
        )
    assert user is not None
    assert user.balance == balance_before
    assert ledger_count == 1
    assert ledger_sum == balance_before


async def test_apply_delta_concurrent(db) -> None:
    user_id = await _seed_user(db, "concuser", 1000)

    async def spend(amount: int) -> int:
        async with SessionLocal() as session:
            async with session.begin():
                return await apply_delta(session, user_id, -amount, "daily_bonus")

    results = await asyncio.gather(
        *[spend(200) for _ in range(10)], return_exceptions=True
    )

    ok = [r for r in results if isinstance(r, int)]
    failed = [r for r in results if isinstance(r, AppError)]
    assert len(ok) == 5
    assert len(failed) == 5
    assert all(r.code == "INSUFFICIENT_FUNDS" for r in failed)

    async with SessionLocal() as check:
        user = await check.get(User, user_id)
        deltas = (await check.scalars(select(Ledger.delta).where(Ledger.user_id == user_id))).all()
    assert user is not None
    assert user.balance == 0
    assert sum(deltas) == user.balance


async def test_daily_bonus_concurrent(client, db) -> None:
    resp = await register(client)
    assert resp.status_code == 201

    responses = await asyncio.gather(
        *[client.post("/api/v1/me/daily-bonus") for _ in range(10)]
    )
    ok = [r for r in responses if r.status_code == 200]
    cooldown = [r for r in responses if r.status_code == 400]
    assert len(ok) == 1
    assert len(cooldown) == 9
    assert all(r.json()["error"]["code"] == "BONUS_COOLDOWN" for r in cooldown)

    async with SessionLocal() as check:
        user = (await check.scalars(select(User))).one()
        daily_rows = (
            await check.scalars(select(Ledger).where(Ledger.reason == "daily_bonus"))
        ).all()
        deltas = (await check.scalars(select(Ledger.delta).where(Ledger.user_id == user.id))).all()
    assert len(daily_rows) == 1
    assert user.balance == DEFAULTS["starting_balance"] + DEFAULTS["daily_bonus"]
    assert sum(deltas) == user.balance


async def test_apply_delta_with_preloaded_user(db) -> None:
    user_id = await _seed_user(db, "preloaduser", 1000)

    async def spend() -> None:
        async with SessionLocal() as session:
            async with session.begin():
                _ = await session.get(User, user_id)
                await asyncio.sleep(0.05)
                await apply_delta(session, user_id, -600, "admin_adjust")

    results = await asyncio.gather(spend(), spend(), return_exceptions=True)

    ok = [r for r in results if r is None]
    failed = [r for r in results if isinstance(r, AppError)]
    assert len(ok) == 1
    assert len(failed) == 1
    assert failed[0].code == "INSUFFICIENT_FUNDS"

    async with SessionLocal() as check:
        user = await check.get(User, user_id)
        deltas = (await check.scalars(select(Ledger.delta).where(Ledger.user_id == user_id))).all()
    assert user is not None
    assert user.balance == 400
    assert sum(deltas) == user.balance


async def test_me_daily_bonus_available_at(client, db) -> None:
    resp = await register(client)
    assert resp.status_code == 201

    me = (await client.get("/api/v1/me")).json()
    assert me["daily_bonus_available_at"] is None

    bonus = await client.post("/api/v1/me/daily-bonus")
    assert bonus.status_code == 200
    me = (await client.get("/api/v1/me")).json()
    available_at = me["daily_bonus_available_at"]
    assert available_at is not None
    assert datetime.fromisoformat(available_at) > datetime.now(UTC)

    async with db.begin():
        user = (await db.scalars(select(User))).one()
        user.last_daily_bonus_at = datetime.now(UTC) - timedelta(hours=25)

    me = (await client.get("/api/v1/me")).json()
    assert me["daily_bonus_available_at"] is None


async def test_daily_bonus_cooldown(client, db) -> None:
    resp = await register(client)
    assert resp.status_code == 201

    first = await client.post("/api/v1/me/daily-bonus")
    assert first.status_code == 200
    assert first.json()["balance"] == 1200

    second = await client.post("/api/v1/me/daily-bonus")
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "BONUS_COOLDOWN"

    async with db.begin():
        row = (await db.scalars(select(User))).one()
        row.last_daily_bonus_at = datetime.now(UTC) - timedelta(hours=25)

    third = await client.post("/api/v1/me/daily-bonus")
    assert third.status_code == 200
    assert third.json()["balance"] == 1400


async def test_ledger_pagination(client, db) -> None:
    resp = await register(client)
    assert resp.status_code == 201
    async with db.begin():
        user = (await db.scalars(select(User))).one()
        for _ in range(7):
            await apply_delta(db, user.id, -10, "daily_bonus")
            user.last_daily_bonus_at = datetime.now(UTC) - timedelta(hours=25)

    page1 = (await client.get("/api/v1/me/ledger?limit=3")).json()
    assert [item["id"] for item in page1["items"]] == [8, 7, 6]
    assert page1["next_cursor"] == 6

    page2 = (await client.get("/api/v1/me/ledger?limit=3&cursor=6")).json()
    assert [item["id"] for item in page2["items"]] == [5, 4, 3]
    assert page2["next_cursor"] == 3

    page3 = (await client.get("/api/v1/me/ledger?limit=3&cursor=3")).json()
    assert [item["id"] for item in page3["items"]] == [2, 1]
    assert page3["next_cursor"] is None
