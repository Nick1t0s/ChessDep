import uuid
from datetime import timedelta

from app.db import SessionLocal
from app.models import Game
from tests.conftest import start_game


async def _state(client, game_id: str) -> dict:
    resp = await client.get(f"/api/v1/games/{game_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_dep_pauses_running_clock(alice, bob, rng, frozen) -> None:
    game_id = await start_game(alice, bob, rng)
    resp = await alice.post(f"/api/v1/games/{game_id}/move", json={"uci": "e2e4"})
    assert resp.status_code == 200, resp.text
    resp = await bob.post(f"/api/v1/games/{game_id}/move", json={"uci": "e7e5"})
    assert resp.status_code == 200, resp.text
    frozen.advance(5)
    before = (await _state(alice, game_id))["clocks"]["white_ms"]
    rng.values = [0.0]
    resp = await alice.post(f"/api/v1/games/{game_id}/dep", json={"square": "b1", "target": "Q"})
    assert resp.status_code == 200, resp.text
    frozen.advance(2)
    assert (await _state(alice, game_id))["clocks"]["white_ms"] == before
    frozen.advance(2)
    assert (await _state(alice, game_id))["clocks"]["white_ms"] == before - 1000


async def test_dep_extends_abort_deadline(alice, bob, rng, frozen) -> None:
    game_id = await start_game(alice, bob, rng)
    async with SessionLocal() as db:
        before = (await db.get(Game, uuid.UUID(game_id))).abort_deadline
    rng.values = [0.0]
    resp = await alice.post(f"/api/v1/games/{game_id}/dep", json={"square": "b1", "target": "Q"})
    assert resp.status_code == 200, resp.text
    async with SessionLocal() as db:
        after = (await db.get(Game, uuid.UUID(game_id))).abort_deadline
    assert after == before + timedelta(milliseconds=3000)
