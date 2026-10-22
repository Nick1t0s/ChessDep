import asyncio
import json
import uuid

from app.redis import redis_client
from app.services.pubsub import game_channel
from tests.conftest import start_game


async def _next_message(pubsub, attempts: int = 30) -> dict:
    for _ in range(attempts):
        raw = await asyncio.wait_for(pubsub.get_message(timeout=0.1), timeout=2.0)
        if raw is not None and raw.get("type") == "message":
            return json.loads(raw["data"])
    raise AssertionError("no pubsub message")


async def test_post_roles(alice, bob, carol, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    url = f"/api/v1/games/{game_id}/chat"

    resp = await alice.post(url, json={"body": "  gg  "})
    assert resp.status_code == 201, resp.text
    message = resp.json()
    assert message["role"] == "white"
    assert message["login"] == "alice"
    assert message["body"] == "gg"
    assert message["created_at"] is not None

    resp = await bob.post(url, json={"body": "успех"})
    assert resp.status_code == 201, resp.text
    assert resp.json()["role"] == "black"
    assert resp.json()["login"] == "bob"

    resp = await carol.post(url, json={"body": "привет"})
    assert resp.status_code == 201, resp.text
    spectator = resp.json()
    assert spectator["role"] == "spectator"
    assert spectator["login"] == "carol"


async def test_post_validation(alice, bob, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    url = f"/api/v1/games/{game_id}/chat"

    resp = await alice.post(url, json={"body": "   "})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    resp = await alice.post(url, json={"body": "x" * 301})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    resp = await alice.post(url, json={"body": "x" * 300})
    assert resp.status_code == 201, resp.text
    assert resp.json()["body"] == "x" * 300


async def test_rate_limit(alice, bob, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    url = f"/api/v1/games/{game_id}/chat"

    resp = await alice.post(url, json={"body": "первое"})
    assert resp.status_code == 201, resp.text

    resp = await alice.post(url, json={"body": "второе"})
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "RATE_LIMITED"


async def test_list_pagination(alice, bob, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    url = f"/api/v1/games/{game_id}/chat"
    alice_id = (await alice.get("/api/v1/me")).json()["id"]

    ids = []
    for i in range(5):
        resp = await alice.post(url, json={"body": f"msg{i}"})
        assert resp.status_code == 201, resp.text
        ids.append(resp.json()["id"])
        await redis_client.delete(f"rl:chat:{alice_id}")

    resp = await alice.get(url, params={"limit": 2})
    assert resp.status_code == 200
    page = resp.json()
    assert [m["id"] for m in page["items"]] == ids[3:]
    assert [m["body"] for m in page["items"]] == ["msg3", "msg4"]
    assert page["next_cursor"] == ids[3]

    resp = await alice.get(url, params={"before_id": page["next_cursor"], "limit": 2})
    page2 = resp.json()
    assert [m["id"] for m in page2["items"]] == ids[1:3]
    assert [m["body"] for m in page2["items"]] == ["msg1", "msg2"]
    assert page2["next_cursor"] == ids[1]

    resp = await alice.get(url, params={"before_id": ids[1], "limit": 5})
    page3 = resp.json()
    assert [m["id"] for m in page3["items"]] == [ids[0]]
    assert page3["next_cursor"] is None


async def test_publish_after_commit(alice, bob, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    url = f"/api/v1/games/{game_id}/chat"
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(game_channel(uuid.UUID(game_id)))

    resp = await alice.post(url, json={"body": "hello"})
    assert resp.status_code == 201, resp.text

    message = await _next_message(pubsub)
    assert set(message.keys()) == {"chat"}
    chat = message["chat"]
    assert chat["body"] == "hello"
    assert chat["login"] == "alice"
    assert chat["role"] == "white"

    await pubsub.unsubscribe(game_channel(uuid.UUID(game_id)))
    await pubsub.aclose()


async def test_chat_auth_and_404(client, alice) -> None:
    missing = str(uuid.uuid4())
    post_url = f"/api/v1/games/{missing}/chat"
    get_url = f"/api/v1/games/{missing}/chat"

    resp = await client.post(post_url, json={"body": "gg"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"

    resp = await client.get(get_url)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"

    resp = await alice.post(post_url, json={"body": "gg"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "GAME_NOT_FOUND"

    resp = await alice.get(get_url)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "GAME_NOT_FOUND"
