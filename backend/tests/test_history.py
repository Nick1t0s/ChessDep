import uuid

from tests.conftest import anonymous, start_game


async def _play_fools_mate(game_id: str, alice, bob) -> None:
    for who, uci in (("alice", "f2f3"), ("bob", "e7e5"), ("alice", "g2g4"), ("bob", "d8h4")):
        actor = alice if who == "alice" else bob
        resp = await actor.post(f"/api/v1/games/{game_id}/move", json={"uci": uci})
        assert resp.status_code == 200, resp.text


async def test_events_fools_mate(alice, bob, rng, carol) -> None:
    game_id = await start_game(alice, bob, rng)
    await _play_fools_mate(game_id, alice, bob)

    resp = await carol.get(f"/api/v1/games/{game_id}/events")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    game = data["game"]
    assert game["id"] == game_id
    assert game["status"] == "finished"
    assert game["result"] == "black"
    assert game["end_reason"] == "checkmate"
    assert game["white"]["login"] == "alice"
    assert game["white"]["elo"] == 1200
    assert game["black"]["login"] == "bob"
    assert len(game["initial_board"]) == 32

    events = data["events"]
    assert len(events) == 5
    seqs = [event["seq"] for event in events]
    assert seqs == sorted(seqs)
    moves = [event for event in events if event["kind"] == "move"]
    assert len(moves) == 4
    game_over = events[-1]
    assert game_over["kind"] == "game_over"
    assert game_over["payload"]["result"] == "black"
    assert game_over["payload"]["end_reason"] == "checkmate"

    last_move = moves[-1]
    assert last_move["payload"]["san"] == "Qh4#"
    assert last_move["actor"] == "black"
    squares = {(sq["square"], sq["piece"], sq["color"]) for sq in last_move["board"]}
    assert ("h4", "Q", "black") in squares
    assert last_move["check_square"] == "e1"


async def test_events_after_seq(alice, bob, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    resp = await alice.post(f"/api/v1/games/{game_id}/move", json={"uci": "f2f3"})
    assert resp.status_code == 200, resp.text
    resp = await bob.post(f"/api/v1/games/{game_id}/move", json={"uci": "e7e5"})
    assert resp.status_code == 200, resp.text

    resp = await alice.get(f"/api/v1/games/{game_id}/events")
    assert resp.status_code == 200, resp.text
    all_events = resp.json()["events"]
    seqs = [event["seq"] for event in all_events]
    assert len(seqs) == 2
    assert seqs == [1, 2]

    resp = await alice.get(f"/api/v1/games/{game_id}/events", params={"after_seq": 2})
    assert resp.status_code == 200, resp.text
    events = resp.json()["events"]
    assert [event["seq"] for event in events] == []

    resp = await alice.get(f"/api/v1/games/{game_id}/events", params={"after_seq": 1})
    assert resp.status_code == 200, resp.text
    events = resp.json()["events"]
    assert [event["seq"] for event in events] == [2]


async def test_events_dep_payload(alice, bob, rng) -> None:
    game_id = await start_game(alice, bob, rng)
    rng.values = [0.0]
    resp = await alice.post(f"/api/v1/games/{game_id}/dep", json={"square": "b1", "target": "Q"})
    assert resp.status_code == 200, resp.text

    resp = await alice.get(f"/api/v1/games/{game_id}/events")
    assert resp.status_code == 200, resp.text
    events = resp.json()["events"]
    dep_events = [event for event in events if event["kind"] == "dep"]
    assert len(dep_events) == 1
    dep = dep_events[0]
    assert dep["payload"]["success"] is True
    squares = {(sq["square"], sq["piece"], sq["color"]) for sq in dep["board"]}
    assert ("b1", "Q", "white") in squares


async def test_events_spectator_and_auth(alice, bob, rng, carol) -> None:
    game_id = await start_game(alice, bob, rng)

    resp = await carol.get(f"/api/v1/games/{game_id}/events")
    assert resp.status_code == 200, resp.text

    anon = anonymous()
    resp = await anon.get(f"/api/v1/games/{game_id}/events")
    assert resp.status_code == 401

    resp = await carol.get(f"/api/v1/games/{uuid.uuid4()}/events")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "GAME_NOT_FOUND"


async def test_user_profile_stats(alice, bob, rng, carol) -> None:
    game_id = await start_game(alice, bob, rng)
    await _play_fools_mate(game_id, alice, bob)

    resp = await carol.get("/api/v1/users/alice")
    assert resp.status_code == 200, resp.text
    profile = resp.json()
    assert profile["login"] == "alice"
    assert profile["games"] == {"played": 1, "wins": 0, "draws": 0, "losses": 1}

    resp = await carol.get("/api/v1/users/bob")
    assert resp.status_code == 200, resp.text
    assert resp.json()["games"]["wins"] == 1

    resp = await carol.get("/api/v1/users/nobody")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "USER_NOT_FOUND"


async def test_user_games_shape(alice, bob, rng, carol) -> None:
    game_id = await start_game(alice, bob, rng)
    await _play_fools_mate(game_id, alice, bob)

    resp = await carol.get("/api/v1/users/bob/games")
    assert resp.status_code == 200, resp.text
    page = resp.json()
    assert len(page["items"]) == 1
    item = page["items"][0]
    assert item["id"] == game_id
    assert item["opponent_login"] == "alice"
    assert item["color"] == "black"
    assert item["result"] == "black"
    assert item["end_reason"] == "checkmate"
    assert item["time_control"] == "3+2"
    assert item["finished_at"] is not None
    assert item["elo_delta"] == 16
