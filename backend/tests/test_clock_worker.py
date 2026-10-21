import uuid

from app.core import clock as clock_module
from app.db import SessionLocal
from app.models import Game, User
from app.redis import redis_client
from app.worker import rebuild_deadlines, tick_clocks
from tests.conftest import set_fen, start_game


def _game_id(game_id: str):
    return uuid.UUID(game_id)


async def test_clock_starts_after_black_first_move(alice, bob, rng, frozen, db) -> None:
    game_id = await start_game(alice, bob, rng)

    resp = await alice.post(f"/api/v1/games/{game_id}/move", json={"uci": "e2e4"})
    assert resp.status_code == 200, resp.text
    await db.rollback()
    game = await db.get(Game, _game_id(game_id))
    assert game.clock_running is False

    resp = await bob.post(f"/api/v1/games/{game_id}/move", json={"uci": "e7e5"})
    assert resp.status_code == 200, resp.text
    await db.rollback()
    game = await db.get(Game, _game_id(game_id))
    assert game.clock_running is True
    assert game.abort_deadline is None

    frozen.advance(10)
    resp = await alice.post(f"/api/v1/games/{game_id}/move", json={"uci": "g1f3"})
    assert resp.status_code == 200, resp.text
    state = resp.json()
    assert state["clocks"]["white_ms"] == 180000 - 10000 + 2000


async def test_flag_by_worker(alice, bob, rng, frozen) -> None:
    game_id = await start_game(alice, bob, rng)
    resp = await alice.post(f"/api/v1/games/{game_id}/move", json={"uci": "e2e4"})
    assert resp.status_code == 200, resp.text
    resp = await bob.post(f"/api/v1/games/{game_id}/move", json={"uci": "e7e5"})
    assert resp.status_code == 200, resp.text

    frozen.advance(181)
    await tick_clocks(clock_module.now())

    async with SessionLocal() as check:
        game = await check.get(Game, _game_id(game_id))
    assert game.status == "finished"
    assert game.result == "black"
    assert game.end_reason == "timeout"
    assert game.white_ms == 0


async def test_flag_vs_insufficient(alice, bob, rng, frozen) -> None:
    game_id = await start_game(alice, bob, rng)
    await set_fen(
        game_id,
        "4k3/8/8/8/8/8/r7/4K3 b - - 0 1",
        ply=20,
        clock_running=True,
    )
    frozen.advance(181)
    await tick_clocks(clock_module.now())

    async with SessionLocal() as check:
        game = await check.get(Game, _game_id(game_id))
    assert game.status == "finished"
    assert game.result == "draw"
    assert game.end_reason == "timeout_vs_insufficient"


async def test_move_after_expiry_rejected(alice, bob, rng, frozen) -> None:
    game_id = await start_game(alice, bob, rng)
    resp = await alice.post(f"/api/v1/games/{game_id}/move", json={"uci": "e2e4"})
    assert resp.status_code == 200, resp.text
    resp = await bob.post(f"/api/v1/games/{game_id}/move", json={"uci": "e7e5"})
    assert resp.status_code == 200, resp.text

    frozen.advance(181)
    resp = await alice.post(f"/api/v1/games/{game_id}/move", json={"uci": "g1f3"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "TIME_EXPIRED"


async def test_abort_no_first_move(alice, bob, rng, frozen) -> None:
    game_id = await start_game(alice, bob, rng)
    frozen.advance(31)
    await tick_clocks(clock_module.now())

    async with SessionLocal() as check:
        game = await check.get(Game, _game_id(game_id))
        assert game.status == "aborted"
        assert game.end_reason == "abort_no_first_move"
        assert game.white_elo_after is None
        white = await check.get(User, game.white_id)
        black = await check.get(User, game.black_id)

    assert white.elo == 1200
    assert black.elo == 1200


async def test_rebuild_deadlines(alice, bob, rng, frozen) -> None:
    game_id = await start_game(alice, bob, rng)
    gid = _game_id(game_id)
    await redis_client.delete("clock:deadlines")
    await rebuild_deadlines()
    async with SessionLocal() as check:
        game = await check.get(Game, gid)
    expected_score = clock_module.to_ms(game.abort_deadline)
    score = await redis_client.zscore("clock:deadlines", str(gid))
    assert score is not None
    assert abs(score - expected_score) < 1


async def test_tick_clocks_skips_broken_entries(alice, bob, rng, frozen) -> None:
    game_id = await start_game(alice, bob, rng)
    for client, uci in ((alice, "e2e4"), (bob, "e7e5")):
        resp = await client.post(f"/api/v1/games/{game_id}/move", json={"uci": uci})
        assert resp.status_code == 200, resp.text
    ghost = str(uuid.uuid4())
    await redis_client.zadd("clock:deadlines", {ghost: 0, "not-a-uuid": 0})

    frozen.advance(181)
    await tick_clocks(clock_module.now())

    async with SessionLocal() as check:
        game = await check.get(Game, _game_id(game_id))
    assert game.status == "finished"
    assert game.end_reason == "timeout"
    assert await redis_client.zscore("clock:deadlines", ghost) is None
    assert await redis_client.zscore("clock:deadlines", "not-a-uuid") is None
