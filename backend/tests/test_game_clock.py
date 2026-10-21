from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.api.ws import ws_messages
from app.services.elo import elo_update
from app.services.game_clock import deadline, parse_time_control, remaining_ms


def _game(**kwargs) -> SimpleNamespace:
    defaults = dict(
        fen="4k3/8/8/8/8/8/8/4K3 w - - 0 1",
        status="active",
        white_ms=180000,
        black_ms=180000,
        clock_running=False,
        turn_started_at=datetime(2026, 10, 21, 12, 0, tzinfo=UTC),
        abort_deadline=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_parse_time_control() -> None:
    assert parse_time_control("3+2") == (180000, 2000)
    assert parse_time_control("10+0") == (600000, 0)
    for tc in ("3", "a+b", ""):
        try:
            parse_time_control(tc)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {tc!r}")


def test_remaining_ms() -> None:
    now = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)

    not_running = _game()
    assert remaining_ms(not_running, "white", now) == 180000
    assert remaining_ms(not_running, "black", now) == 180000

    running = _game(clock_running=True, turn_started_at=now - timedelta(milliseconds=1500))
    assert remaining_ms(running, "white", now) == 180000 - 1500
    assert remaining_ms(running, "black", now) == 180000

    exhausted = _game(clock_running=True, turn_started_at=now - timedelta(seconds=10**6))
    assert remaining_ms(exhausted, "white", now) == 0


def test_deadline() -> None:
    started_at = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
    abort_deadline = started_at + timedelta(seconds=30)

    finished = _game(status="finished", clock_running=True, abort_deadline=abort_deadline)
    assert deadline(finished) is None

    waiting = _game(abort_deadline=abort_deadline)
    assert deadline(waiting) == abort_deadline

    running = _game(clock_running=True, turn_started_at=started_at, white_ms=120000)
    assert deadline(running) == started_at + timedelta(milliseconds=120000)


def test_elo_update() -> None:
    assert elo_update(1200, 1200, 1) == (1216, 1184)
    assert elo_update(1200, 1200, 0.5) == (1200, 1200)
    assert elo_update(1400, 1200, 1) == (1408, 1192)
    assert elo_update(1400, 1200, 0) == (1376, 1224)


def test_ws_messages() -> None:
    state = {"version": 1}
    assert ws_messages({"version": 1}, state) == [{"type": "state", "data": state}]

    dep = {"by": "white", "square": "b1"}
    with_dep = ws_messages({"version": 1, "dep": dep}, state)
    assert with_dep == [
        {"type": "dep", "data": dep},
        {"type": "state", "data": state},
    ]

    game_over = {"result": "draw", "end_reason": "agreement"}
    with_both = ws_messages({"version": 1, "dep": dep, "game_over": game_over}, state)
    assert with_both == [
        {"type": "dep", "data": dep},
        {"type": "state", "data": state},
        {"type": "game_over", "data": game_over},
    ]
