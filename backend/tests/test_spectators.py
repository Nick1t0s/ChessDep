from app.api.ws import is_chat_event
from tests.conftest import start_game


async def test_spectator_sees_state(alice, bob, carol, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    resp = await carol.get(f"/api/v1/games/{game_id}")
    assert resp.status_code == 200, resp.text
    state = resp.json()
    assert state["you"] == "spectator"
    assert state["legal_moves"] == []
    assert len(state["board"]) == 32


async def test_spectator_cannot_act(alice, bob, carol, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    base = f"/api/v1/games/{game_id}"

    resp = await carol.post(f"{base}/move", json={"uci": "e2e4"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "GAME_NOT_FOUND"

    resp = await carol.post(f"{base}/dep", json={"square": "b1", "target": "Q"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "GAME_NOT_FOUND"

    resp = await carol.post(f"{base}/resign")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "GAME_NOT_FOUND"

    resp = await carol.post(f"{base}/draw/offer")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "GAME_NOT_FOUND"

    resp = await carol.post(f"{base}/abort")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "GAME_NOT_FOUND"

    resp = await carol.get(f"{base}/dep-options")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "GAME_NOT_FOUND"


async def test_live_games_list(alice, bob, carol, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    resp = await alice.post(f"/api/v1/games/{game_id}/move", json={"uci": "e2e4"})
    assert resp.status_code == 200, resp.text

    resp = await carol.get("/api/v1/games/live")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 1
    item = items[0]
    assert item["id"] == game_id
    assert item["white"]["login"] == "alice"
    assert item["white"]["elo"] == 1200
    assert item["black"]["login"] == "bob"
    assert item["black"]["elo"] == 1200
    assert item["time_control"] == "3+2"
    assert item["ply"] == 1
    assert item["deps_used"] == 0
    assert item["created_at"]

    resp = await bob.post(f"/api/v1/games/{game_id}/resign")
    assert resp.status_code == 200, resp.text

    resp = await carol.get("/api/v1/games/live")
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test_live_route_not_uuid(carol) -> None:
    resp = await carol.get("/api/v1/games/live")
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test_live_requires_auth(client) -> None:
    resp = await client.get("/api/v1/games/live")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


def test_is_chat_event() -> None:
    assert is_chat_event({"chat": {}}) is True
    assert is_chat_event({"version": 1}) is False
