import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import chess
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, event, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.chess_engine import position_key
from app.config import settings
from app.db import SessionLocal, engine
from app.main import app
from app.models import Case, CaseDrop, Collection, Game, ItemDef, Setting, User
from app.redis import redis_client as redis
from app.seed_data import genesis_rows
from app.services import rolls
import app.core.clock as clock
from app.services.items import create_item
from app.services.settings import DEFAULTS

_TRUNCATE_SQL = text(
    "TRUNCATE users, sessions, ledger, admin_audit, games, game_events, "
    "active_players, invites, rolls, collections, item_defs, inventory_items, "
    "loadouts, cases, case_drops, market_listings, item_transfers, game_messages "
    "RESTART IDENTITY CASCADE"
)

_SEED_SEQUENCE_TABLES = ("collections", "item_defs", "cases")


async def _seed_settings(db: AsyncSession) -> None:
    await db.execute(delete(Setting))
    rows: list[dict[str, Any]] = [
        {"key": key, "value": value} for key, value in DEFAULTS.items()
    ]
    await db.execute(insert(Setting).values(rows))


async def _seed_genesis(db: AsyncSession) -> None:
    rows = genesis_rows()
    await db.execute(insert(Collection).values(rows["collections"]))
    await db.execute(insert(ItemDef).values(rows["item_defs"]))
    await db.execute(insert(Case).values(rows["cases"]))
    await db.execute(insert(CaseDrop).values(rows["case_drops"]))
    # После вставки с явными id сдвинуть последовательности.
    for table in _SEED_SEQUENCE_TABLES:
        await db.execute(text(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
            f"(SELECT max(id) FROM {table}))"
        ))


@pytest_asyncio.fixture(autouse=True)
async def clean_db() -> AsyncIterator[None]:
    async with SessionLocal() as db:
        async with db.begin():
            await db.execute(_TRUNCATE_SQL)
            await _seed_settings(db)
            await _seed_genesis(db)
    from app.services import settings as settings_service

    settings_service.clear_cache()
    await redis.flushdb()
    yield
    await redis.aclose()


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


@pytest_asyncio.fixture
async def redis_client() -> AsyncIterator[Any]:
    yield redis


class FixedRng:
    def __init__(self, values: list[float] | None = None) -> None:
        self.values: list[float] = list(values) if values is not None else []
        self._index = 0

    def random(self) -> float:
        if not self.values:
            return 0.0
        value = self.values[self._index % len(self.values)]
        self._index += 1
        return value


@pytest_asyncio.fixture
async def rng() -> AsyncIterator[FixedRng]:
    fixed = FixedRng()
    rolls.set_rng(fixed)
    yield fixed
    rolls.reset_rng()


class FrozenClock:
    def __init__(self) -> None:
        self._now = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)


@pytest_asyncio.fixture
async def frozen(monkeypatch) -> AsyncIterator[FrozenClock]:
    frozen_clock = FrozenClock()
    from app.core import clock as clock_module

    monkeypatch.setattr(clock_module, "now", frozen_clock.now)
    yield frozen_clock


@pytest_asyncio.fixture
async def alice() -> AsyncIterator[AsyncClient]:
    async with _registered_client("alice") as client:
        yield client


@pytest_asyncio.fixture
async def bob() -> AsyncIterator[AsyncClient]:
    async with _registered_client("bob") as client:
        yield client


@pytest_asyncio.fixture
async def carol() -> AsyncIterator[AsyncClient]:
    async with _registered_client("carol") as client:
        yield client


@pytest_asyncio.fixture
async def admin() -> AsyncIterator[AsyncClient]:
    async with _registered_client("admin") as client:
        async with SessionLocal() as db:
            async with db.begin():
                user = (await db.scalars(select(User).where(User.login == "admin"))).one()
                user.role = "admin"
        yield client


def _async_client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Origin": "http://test"},
    )


def anonymous() -> AsyncClient:
    """Клиент без сессии (аноним)."""
    return _async_client()


@asynccontextmanager
async def _registered_client(login: str) -> AsyncIterator[AsyncClient]:
    ctx = _async_client()
    async with ctx as client:
        resp = await register(client, login)
        assert resp.status_code == 201, resp.text
        yield client


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


async def give_items(user_login: str, codes: list[str]) -> list[int]:
    """Создать предметы через create_item в отдельной сессии; wear 0.5.

    Временно ставит FixedRng([0.5]), затем восстанавливает RNG, который был
    до вызова (иначе сломается фикстура rng).
    """
    prev = rolls.get_rng()
    rolls.set_rng(FixedRng([0.5]))
    try:
        async with SessionLocal() as db:
            async with db.begin():
                user = (await db.scalars(select(User).where(User.login == user_login))).one()
                defs = {
                    d.code: d
                    for d in (
                        await db.scalars(select(ItemDef).where(ItemDef.code.in_(codes)))
                    ).all()
                }
                now = clock.now()
                item_ids: list[int] = []
                for code in codes:
                    item = await create_item(
                        db,
                        user_id=user.id,
                        def_id=defs[code].id,
                        source="admin_grant",
                        source_ref="test",
                        now=now,
                    )
                    item_ids.append(item.id)
        return item_ids
    finally:
        rolls.set_rng(prev)


async def start_game(
    alice_client: AsyncClient, bob_client: AsyncClient, rng: FixedRng, tc: str = "3+2"
) -> str:
    rng.values = [0.0]
    resp = await alice_client.post("/api/v1/invites", json={"time_control": tc})
    assert resp.status_code == 200, resp.text
    code = resp.json()["code"]
    resp = await bob_client.post(f"/api/v1/invites/{code}/accept")
    assert resp.status_code == 200, resp.text
    return resp.json()["game_id"]


async def set_fen(game_id: str, fen: str, **fields: Any) -> None:
    async with SessionLocal() as db:
        async with db.begin():
            game = await db.get(Game, uuid.UUID(game_id))
            if game is None:
                raise AssertionError("game not found")
            board = chess.Board(fen)
            game.fen = fen
            game.repetition = {position_key(board): 1}
            for key, value in fields.items():
                setattr(game, key, value)


async def set_balance(login: str, value: int) -> None:
    """Выставить пользователю точный баланс (через apply_delta, ledger keeps sum==balance)."""
    from app.services.economy import apply_delta

    async with SessionLocal() as db:
        async with db.begin():
            user = (await db.scalars(select(User).where(User.login == login))).one()
            delta = value - user.balance
            if delta:
                await apply_delta(db, user.id, delta, "admin_adjust", ref="test-setup")


async def set_setting(key: str, value: Any) -> None:
    """Обновить строку settings напрямую и сбросить кэш."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.services import settings as settings_service

    async with SessionLocal() as db:
        async with db.begin():
            await db.execute(
                pg_insert(Setting)
                .values(key=key, value=value)
                .on_conflict_do_update(index_elements=["key"], set_={"value": value})
            )
    settings_service.clear_cache()


@asynccontextmanager
async def count_queries() -> AsyncIterator[list[str]]:
    """Считает SQL-запросы через engine внутри контекста."""
    queries: list[str] = []

    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _before_cursor_execute)
    try:
        yield queries
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _before_cursor_execute)
