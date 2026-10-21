from dataclasses import dataclass

import chess

from .constants import COLOR_NAME, TYPE_TO_LETTER
from .errors import EngineError


@dataclass(frozen=True)
class Outcome:
    result: str       # "white" | "black" | "draw"
    end_reason: str   # "checkmate" | "stalemate" | "insufficient_material" | "fifty_move" | "threefold"


@dataclass(frozen=True)
class MoveResult:
    board: chess.Board   # новая позиция, пустой move_stack
    uci: str
    san: str
    irreversible: bool   # board.is_irreversible(move), вычислить ДО хода


def apply_move(board: chess.Board, uci: str) -> MoveResult:
    try:
        move = chess.Move.from_uci(uci)
    except ValueError as exc:
        raise EngineError("ILLEGAL_MOVE") from exc
    if move not in board.legal_moves:
        raise EngineError("ILLEGAL_MOVE")
    san = board.san(move)
    irreversible = board.is_irreversible(move)
    after = board.copy(stack=False)
    after.push(move)
    return MoveResult(board=chess.Board(after.fen()), uci=move.uci(), san=san,
                      irreversible=irreversible)


def game_outcome(board: chess.Board, repetition_count: int = 1) -> Outcome | None:
    if board.is_checkmate():
        return Outcome(result=COLOR_NAME[not board.turn], end_reason="checkmate")
    if board.is_stalemate():
        return Outcome(result="draw", end_reason="stalemate")
    if board.is_insufficient_material():
        return Outcome(result="draw", end_reason="insufficient_material")
    if board.halfmove_clock >= 100:
        return Outcome(result="draw", end_reason="fifty_move")
    if repetition_count >= 3:
        return Outcome(result="draw", end_reason="threefold")
    return None


def legal_moves_uci(board: chess.Board) -> list[str]:
    return sorted(move.uci() for move in board.legal_moves)


def board_squares(board: chess.Board) -> list[dict[str, str]]:
    squares: list[dict[str, str]] = []
    for sq in range(64):
        piece = board.piece_at(sq)
        if piece is None:
            continue
        squares.append({"square": chess.square_name(sq),
                        "piece": TYPE_TO_LETTER[piece.piece_type],
                        "color": COLOR_NAME[piece.color]})
    return squares


def position_key(board: chess.Board) -> str:
    return " ".join(board.fen(en_passant="legal").split()[:4])


def can_win_on_time(board: chess.Board, color: str) -> bool:
    if color not in COLOR_NAME.values():
        raise ValueError(f"unknown color: {color!r}")
    board_color = chess.WHITE if color == COLOR_NAME[chess.WHITE] else chess.BLACK
    return not board.has_insufficient_material(board_color)
