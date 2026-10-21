from dataclasses import dataclass

import chess

from .constants import DEP_TARGETS, LETTER_TO_TYPE, PIECE_VALUES, TYPE_TO_LETTER
from .errors import EngineError


@dataclass(frozen=True)
class DepTarget:
    piece: str            # "N" | "B" | "R" | "Q"
    chance: float
    chance_text: str
    allowed: bool
    reason: str | None    # None | "WOULD_CHECK_OPPONENT"


@dataclass(frozen=True)
class DepPieceOption:
    square: str           # "c3"
    piece: str            # "P" | "N" | "B" | "R"
    targets: tuple[DepTarget, ...]


@dataclass(frozen=True)
class DepResolution:
    success: bool
    square: str
    from_piece: str
    to_piece: str
    chance: float
    chance_text: str
    roll_value: float
    board: chess.Board    # позиция после исхода; ход всё ещё за тем же игроком


def dep_chance(from_letter: str, to_letter: str, multiplier: float) -> float:
    from_type = LETTER_TO_TYPE.get(from_letter)
    to_type = LETTER_TO_TYPE.get(to_letter)
    if (from_type is None or to_type is None
            or from_type not in DEP_TARGETS
            or to_type not in DEP_TARGETS[from_type]):
        raise EngineError("DEP_INVALID_TARGET")
    chance = PIECE_VALUES[from_type] / PIECE_VALUES[to_type] * multiplier
    return min(1.0, max(0.0, chance))


def format_chance(chance: float) -> str:
    return f"{chance * 100:.2f}%"


def apply_dep_outcome(board: chess.Board, square: int, target: int | None) -> chess.Board:
    b = board.copy(stack=False)
    color = b.piece_at(square).color
    b.remove_piece_at(square)
    if target is not None:
        b.set_piece_at(square, chess.Piece(target, color))
    b.castling_rights = b.clean_castling_rights()
    if b.ep_square is not None and not b.has_legal_en_passant():
        b.ep_square = None
    b.halfmove_clock = 0
    return b


def _gives_check(b: chess.Board) -> bool:
    king = b.king(not b.turn)
    return king is not None and b.is_attacked_by(b.turn, king)


def validate_dep(board: chess.Board, square_name: str, target_letter: str) -> tuple[int, int]:
    try:
        sq = chess.parse_square(square_name)
    except ValueError as exc:
        raise EngineError("DEP_INVALID_PIECE") from exc
    piece = board.piece_at(sq)
    if piece is None or piece.color != board.turn or piece.piece_type not in DEP_TARGETS:
        raise EngineError("DEP_INVALID_PIECE")
    to_type = LETTER_TO_TYPE.get(target_letter)
    if to_type is None or to_type not in DEP_TARGETS[piece.piece_type]:
        raise EngineError("DEP_INVALID_TARGET")
    if _gives_check(apply_dep_outcome(board, sq, to_type)) or \
            _gives_check(apply_dep_outcome(board, sq, None)):
        raise EngineError("WOULD_CHECK_OPPONENT")
    return sq, to_type


def list_dep_options(board: chess.Board, multiplier: float) -> list[DepPieceOption]:
    options: list[DepPieceOption] = []
    for sq in range(64):
        piece = board.piece_at(sq)
        if piece is None or piece.color != board.turn or piece.piece_type not in DEP_TARGETS:
            continue
        from_letter = TYPE_TO_LETTER[piece.piece_type]
        targets: list[DepTarget] = []
        for to_type in DEP_TARGETS[piece.piece_type]:
            to_letter = TYPE_TO_LETTER[to_type]
            chance = dep_chance(from_letter, to_letter, multiplier)
            try:
                validate_dep(board, chess.square_name(sq), to_letter)
                allowed, reason = True, None
            except EngineError as exc:
                if exc.code != "WOULD_CHECK_OPPONENT":
                    raise
                allowed, reason = False, "WOULD_CHECK_OPPONENT"
            targets.append(DepTarget(piece=to_letter, chance=chance,
                                     chance_text=format_chance(chance),
                                     allowed=allowed, reason=reason))
        options.append(DepPieceOption(square=chess.square_name(sq), piece=from_letter,
                                      targets=tuple(targets)))
    return options


def resolve_dep(board: chess.Board, square_name: str, target_letter: str,
                roll_value: float, multiplier: float) -> DepResolution:
    if not 0.0 <= roll_value < 1.0:
        raise ValueError("roll_value out of range")
    sq, to_type = validate_dep(board, square_name, target_letter)
    from_letter = TYPE_TO_LETTER[board.piece_at(sq).piece_type]
    to_letter = TYPE_TO_LETTER[to_type]
    chance = dep_chance(from_letter, to_letter, multiplier)
    success = roll_value < chance
    new_board = apply_dep_outcome(board, sq, to_type if success else None)
    return DepResolution(success=success, square=chess.square_name(sq),
                         from_piece=from_letter, to_piece=to_letter,
                         chance=chance, chance_text=format_chance(chance),
                         roll_value=roll_value, board=new_board)
