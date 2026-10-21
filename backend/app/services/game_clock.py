from datetime import datetime, timedelta

import chess

from app.chess_engine import COLOR_NAME


def parse_time_control(tc: str) -> tuple[int, int]:
    # "3+2" -> (180000, 2000)
    parts = tc.split("+")
    if len(parts) != 2:
        raise ValueError(f"invalid time control: {tc!r}")
    for part in parts:
        if not part.isdigit():
            raise ValueError(f"invalid time control: {tc!r}")
    return int(parts[0]) * 60_000, int(parts[1]) * 1000


def turn_color(game) -> str:
    board = chess.Board(game.fen)
    return COLOR_NAME[board.turn]


def remaining_ms(game, color: str, now: datetime) -> int:
    ms = game.white_ms if color == "white" else game.black_ms
    if game.clock_running and color == turn_color(game):
        delta = now - game.turn_started_at
        elapsed = (delta.days * 86_400 + delta.seconds) * 1000 + delta.microseconds // 1000
        return max(0, ms - elapsed)
    return ms


def deadline(game) -> datetime | None:
    if game.status != "active":
        return None
    if game.clock_running:
        ms = game.white_ms if turn_color(game) == "white" else game.black_ms
        return game.turn_started_at + timedelta(milliseconds=ms)
    return game.abort_deadline


def is_expired(game, now: datetime) -> bool:
    dl = deadline(game)
    return dl is not None and now >= dl
