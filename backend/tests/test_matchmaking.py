import uuid

import pytest
from sqlalchemy import select

from app.core import clock as clock_module
from app.db import SessionLocal
from app.models import ActivePlayer, Game, User
from app.redis import redis_client
from app.services import matchmaking
from app.worker import tick_clocks
from tests.conftest import register


def _user_key(user_id: int) -> str:
    return f"mm:user:{user_id}"


def _queue_key(tc: str) -> str:
    return f"mm:queue:{tc}"


async def _user_id(login: str) -> int:
    async with SessionLocal() as db:
        return await db.scalar(select(User.id).where(User.login == login))


async def test_queue_and_match(alice, bob) -> None:
    resp = await alice.post("/api/v1/matchmaking/queue", json={"time_control": "3+2"})
    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "queued"
    resp = await bob.post("/api/v1/matchmaking/queue", json={"time_control": "3+2"})
    assert resp.status_code == 202, resp.text

    for client in (alice, bob):
        resp = await client.get("/api/v1/matchmaking/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert data["time_control"] == "3+2"
        assert data["game_id"] is None

    alice_id, bob_id = await _user_id("alice"), await _user_id("bob")
    assert await redis_client.lindex(_queue_key("3+2"), 0) == str(alice_id)
    assert await redis_client.lindex(_queue_key("3+2"), 1) == str(bob_id)

    await matchmaking.tick(clock_module.now())

    game_ids = []
    for client in (alice, bob):
        resp = await client.get("/api/v1/matchmaking/status")
        data = resp.json()
        assert data["status"] == "matched", resp.text
        assert data["game_id"] is not None
        assert data["time_control"] == "3+2"
        game_ids.append(data["game_id"])
    assert game_ids[0] == game_ids[1]

    assert await redis_client.llen(_queue_key("3+2")) == 0
    for user_id in (alice_id, bob_id):
        assert await redis_client.get(_user_key(user_id)) is None

    async with SessionLocal() as db:
        active_count = len(
            (await db.scalars(select(ActivePlayer).where(ActivePlayer.game_id == uuid.UUID(game_ids[0])))).all()
        )
    assert active_count == 2


async def test_queue_errors(alice) -> None:
    resp = await alice.post("/api/v1/matchmaking/queue", json={"time_control": "1+0"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_TIME_CONTROL"

    resp = await alice.post("/api/v1/matchmaking/queue", json={"time_control": "3+2"})
    assert resp.status_code == 202, resp.text
    alice_id = await _user_id("alice")
    assert await redis_client.llen(_queue_key("3+2")) == 1

    # Повторное подключение продлевает heartbeat и не дублирует запись.
    resp = await alice.post("/api/v1/matchmaking/queue", json={"time_control": "3+2"})
    assert resp.status_code == 202, resp.text
    assert await redis_client.llen(_queue_key("3+2")) == 1


async def test_stale_heartbeat_skipped(alice, bob) -> None:
    resp = await alice.post("/api/v1/matchmaking/queue", json={"time_control": "3+2"})
    assert resp.status_code == 202
    alice_id = await _user_id("alice")
    # Heartbeat истёк: mm:user-ключ пропал, а запись в очереди осталась.
    await redis_client.delete(_user_key(alice_id))

    resp = await bob.post("/api/v1/matchmaking/queue", json={"time_control": "3+2"})
    assert resp.status_code == 202

    await matchmaking.tick(clock_module.now())

    async with SessionLocal() as db:
        active_rows = (await db.scalars(select(ActivePlayer))).all()
    assert len(active_rows) == 0

    bob_id = await _user_id("bob")
    resp = await bob.get("/api/v1/matchmaking/status")
    assert resp.json()["status"] == "queued"
    assert await redis_client.lindex(_queue_key("3+2"), 0) == str(bob_id)


async def test_dequeue(alice) -> None:
    resp = await alice.post("/api/v1/matchmaking/queue", json={"time_control": "3+2"})
    assert resp.status_code == 202

    resp = await alice.delete("/api/v1/matchmaking/queue")
    assert resp.status_code == 204

    resp = await alice.get("/api/v1/matchmaking/status")
    assert resp.json()["status"] == "idle"
    assert await redis_client.llen(_queue_key("3+2")) == 0
    alice_id = await _user_id("alice")
    assert await redis_client.get(_user_key(alice_id)) is None


async def test_queue_from_different_time_controls_not_matched(alice, bob) -> None:
    resp = await alice.post("/api/v1/matchmaking/queue", json={"time_control": "3+2"})
    assert resp.status_code == 202
    resp = await bob.post("/api/v1/matchmaking/queue", json={"time_control": "5+0"})
    assert resp.status_code == 202

    await matchmaking.tick(clock_module.now())

    async with SessionLocal() as db:
        active_rows = (await db.scalars(select(ActivePlayer))).all()
    assert len(active_rows) == 0
    assert await redis_client.llen(_queue_key("3+2")) == 1
    assert await redis_client.llen(_queue_key("5+0")) == 1


async def test_already_in_game_pushed_back(alice, bob, client, rng) -> None:
    resp = await alice.post("/api/v1/matchmaking/queue", json={"time_control": "3+2"})
    assert resp.status_code == 202
    resp = await bob.post("/api/v1/matchmaking/queue", json={"time_control": "3+2"})
    assert resp.status_code == 202

    alice_id, bob_id = await _user_id("alice"), await _user_id("bob")

    resp = await register(client, "carol")
    assert resp.status_code == 201
    resp = await client.post("/api/v1/invites", json={"time_control": "3+2"})
    code = resp.json()["code"]
    resp = await alice.post(f"/api/v1/invites/{code}/accept")
    assert resp.status_code == 200, resp.text

    await matchmaking.tick(clock_module.now())

    async with SessionLocal() as db:
        active = await db.get(ActivePlayer, bob_id)
    assert active is None
    resp = await bob.get("/api/v1/matchmaking/status")
    assert resp.json()["status"] == "queued"

    # Alice уже в партии: её mm:user удалён, bob возвращён в начало очереди.
    assert await redis_client.get(_user_key(alice_id)) is None
    assert await redis_client.lindex(_queue_key("3+2"), 0) == str(bob_id)
    assert await redis_client.llen(_queue_key("3+2")) == 1


async def _queue_both(alice, bob) -> tuple[int, int]:
    for client in (alice, bob):
        resp = await client.post("/api/v1/matchmaking/queue", json={"time_control": "3+2"})
        assert resp.status_code == 202, resp.text
    return await _user_id("alice"), await _user_id("bob")


async def test_matched_game_has_deadline(alice, bob) -> None:
    await _queue_both(alice, bob)
    await matchmaking.tick(clock_module.now())

    game_id = (await alice.get("/api/v1/matchmaking/status")).json()["game_id"]
    async with SessionLocal() as db:
        game = await db.get(Game, uuid.UUID(game_id))
    assert game is not None
    score = await redis_client.zscore("clock:deadlines", game_id)
    assert score == clock_module.to_ms(game.abort_deadline)


async def test_matched_game_aborts_without_moves(alice, bob, frozen) -> None:
    await _queue_both(alice, bob)
    await matchmaking.tick(clock_module.now())
    game_id = (await alice.get("/api/v1/matchmaking/status")).json()["game_id"]

    frozen.advance(31)
    await tick_clocks(clock_module.now())

    async with SessionLocal() as db:
        game = await db.get(Game, uuid.UUID(game_id))
    assert game.status == "aborted"
    assert game.end_reason == "abort_no_first_move"
    for client in (alice, bob):
        assert (await client.get("/api/v1/me/active-game")).json() == {"game_id": None}


async def test_requeue_when_missing_from_list(alice) -> None:
    resp = await alice.post("/api/v1/matchmaking/queue", json={"time_control": "3+2"})
    assert resp.status_code == 202
    alice_id = await _user_id("alice")

    await redis_client.lrem(_queue_key("3+2"), 0, str(alice_id))
    status = (await alice.get("/api/v1/matchmaking/status")).json()
    assert status["status"] == "queued"
    assert await redis_client.llen(_queue_key("3+2")) == 1

    await redis_client.lrem(_queue_key("3+2"), 0, str(alice_id))
    resp = await alice.post("/api/v1/matchmaking/queue", json={"time_control": "3+2"})
    assert resp.status_code == 202
    assert await redis_client.llen(_queue_key("3+2")) == 1


async def test_match_failure_requeues_both(alice, bob, monkeypatch) -> None:
    alice_id, bob_id = await _queue_both(alice, bob)

    async def broken_create_game(*args, **kwargs):
        raise RuntimeError("db is down")

    monkeypatch.setattr(matchmaking, "create_game", broken_create_game)
    with pytest.raises(RuntimeError):
        await matchmaking.tick(clock_module.now())

    assert await redis_client.lrange(_queue_key("3+2"), 0, -1) == [str(alice_id), str(bob_id)]
