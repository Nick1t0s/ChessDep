import pathlib
import random

import chess
import pytest

from app.chess_engine import (EngineError, Outcome, apply_move, board_squares,
                              can_win_on_time, dep_chance, format_chance, game_outcome,
                              legal_moves_uci, list_dep_options, position_key, resolve_dep,
                              validate_dep)

sq = chess.parse_square


def opts(fen: str) -> dict[str, dict[str, bool]]:
    return {o.square: {t.piece: t.allowed for t in o.targets}
            for o in list_dep_options(chess.Board(fen), 1.0)}


def option_details(fen: str, square: str) -> dict[str, str | None]:
    for o in list_dep_options(chess.Board(fen), 1.0):
        if o.square == square:
            return {t.piece: t.reason for t in o.targets}
    raise AssertionError(f"no option for {square}")


# --- Шансы и пары ------------------------------------------------------------


def test_dep_chances_all_pairs() -> None:
    assert dep_chance("P", "N", 1.0) == pytest.approx(1 / 3)
    assert dep_chance("P", "B", 1.0) == pytest.approx(1 / 3)
    assert dep_chance("P", "R", 1.0) == pytest.approx(0.2)
    assert dep_chance("P", "Q", 1.0) == pytest.approx(1 / 9)
    assert dep_chance("N", "R", 1.0) == pytest.approx(0.6)
    assert dep_chance("N", "Q", 1.0) == pytest.approx(1 / 3)
    assert dep_chance("B", "R", 1.0) == pytest.approx(0.6)
    assert dep_chance("B", "Q", 1.0) == pytest.approx(1 / 3)
    assert dep_chance("R", "Q", 1.0) == pytest.approx(5 / 9)


def test_dep_chance_multiplier_and_clamp() -> None:
    assert dep_chance("N", "Q", 0.9) == pytest.approx(0.3)
    assert dep_chance("R", "Q", 2.0) == pytest.approx(1.0)
    assert dep_chance("N", "Q", 0.0) == 0.0


def test_dep_invalid_pairs() -> None:
    for from_letter, to_letter in [("N", "B"), ("B", "N"), ("Q", "K"), ("R", "N"),
                                   ("P", "P"), ("K", "Q"), ("X", "Q")]:
        with pytest.raises(EngineError) as exc_info:
            dep_chance(from_letter, to_letter, 1.0)
        assert exc_info.value.code == "DEP_INVALID_TARGET"


def test_format_chance() -> None:
    assert format_chance(1 / 3) == "33.33%"
    assert format_chance(0.6) == "60.00%"
    assert format_chance(1 / 9) == "11.11%"
    assert format_chance(1.0) == "100.00%"


# --- Опции депа ---------------------------------------------------------------


def test_options_start_position() -> None:
    options = list_dep_options(chess.Board(chess.STARTING_FEN), 1.0)
    assert len(options) == 14
    counts: dict[str, int] = {}
    for o in options:
        counts[o.piece] = counts.get(o.piece, 0) + 1
    assert counts == {"P": 8, "N": 2, "B": 2, "R": 2}
    squares = {o.square for o in options}
    assert "e1" not in squares
    assert "d1" not in squares
    pawn = next(o for o in options if o.piece == "P")
    assert [t.piece for t in pawn.targets] == ["N", "B", "R", "Q"]
    rook = next(o for o in options if o.piece == "R")
    assert [t.piece for t in rook.targets] == ["Q"]
    for o in options:
        for t in o.targets:
            assert t.allowed


def test_options_black_to_move() -> None:
    result = apply_move(chess.Board(chess.STARTING_FEN), "e2e4")
    options = list_dep_options(result.board, 1.0)
    assert len(options) == 14
    for o in options:
        assert o.square[1] in ("7", "8")


def test_dep_forbidden_direct_check() -> None:
    fen = "4k3/8/4P3/8/8/8/8/4K3 w - - 0 1"
    assert opts(fen)["e6"] == {"N": True, "B": True, "R": False, "Q": False}
    details = option_details(fen, "e6")
    assert details["R"] == "WOULD_CHECK_OPPONENT"
    assert details["Q"] == "WOULD_CHECK_OPPONENT"
    assert details["N"] is None
    assert details["B"] is None
    with pytest.raises(EngineError) as exc_info:
        validate_dep(chess.Board(fen), "e6", "Q")
    assert exc_info.value.code == "WOULD_CHECK_OPPONENT"


def test_dep_forbidden_discovered_check_on_fail() -> None:
    fen = "4k3/3N4/2B5/8/8/8/8/4K3 w - - 0 1"
    assert opts(fen)["d7"] == {"R": False, "Q": False}
    assert opts(fen)["c6"] == {"R": True, "Q": True}


def test_dep_on_en_passant_position() -> None:
    fen = "4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2"
    assert opts(fen)["e5"] == {"N": True, "B": True, "R": False, "Q": False}


# --- Ошибки валидации ---------------------------------------------------------


def test_validate_dep_invalid_piece() -> None:
    b = chess.Board(chess.STARTING_FEN)
    for name in ["e1", "d1", "e7", "e4", "z9"]:
        with pytest.raises(EngineError) as exc_info:
            validate_dep(b, name, "Q")
        assert exc_info.value.code == "DEP_INVALID_PIECE"


def test_validate_dep_invalid_target() -> None:
    b = chess.Board(chess.STARTING_FEN)
    for square_name, target in [("b1", "B"), ("b1", "K"), ("b1", "x"), ("a1", "R")]:
        with pytest.raises(EngineError) as exc_info:
            validate_dep(b, square_name, target)
        assert exc_info.value.code == "DEP_INVALID_TARGET"


# --- Применение исхода ---------------------------------------------------------


def test_dep_success_replaces_piece() -> None:
    b = chess.Board(chess.STARTING_FEN)
    resolution = resolve_dep(b, "b1", "Q", roll_value=0.0, multiplier=1.0)
    assert resolution.success
    piece = resolution.board.piece_at(sq("b1"))
    assert piece is not None
    assert piece.color == chess.WHITE
    assert piece.piece_type == chess.QUEEN
    assert resolution.board.turn == chess.WHITE
    assert b.fen() == chess.STARTING_FEN


def test_dep_fail_removes_piece() -> None:
    b = chess.Board(chess.STARTING_FEN)
    resolution = resolve_dep(b, "b1", "Q", roll_value=0.99, multiplier=1.0)
    assert not resolution.success
    assert resolution.board.piece_at(sq("b1")) is None
    assert b.fen() == chess.STARTING_FEN


def test_dep_roll_boundary() -> None:
    fen = "4k3/8/8/8/8/8/P7/4K3 w - - 0 1"
    resolution = resolve_dep(chess.Board(fen), "a2", "R", roll_value=0.19999, multiplier=1.0)
    assert resolution.success
    resolution = resolve_dep(chess.Board(fen), "a2", "R", roll_value=0.2, multiplier=1.0)
    assert not resolution.success
    with pytest.raises(ValueError):
        resolve_dep(chess.Board(fen), "a2", "R", roll_value=1.0, multiplier=1.0)
    with pytest.raises(ValueError):
        resolve_dep(chess.Board(fen), "a2", "R", roll_value=-0.01, multiplier=1.0)


def test_dep_allowed_self_discovered_check() -> None:
    fen = "4r2k/8/8/8/8/8/4N3/4K3 w - - 0 1"
    assert opts(fen)["e2"] == {"R": True, "Q": True}
    b = chess.Board(fen)
    resolution = resolve_dep(b, "e2", "Q", roll_value=0.99, multiplier=1.0)
    assert not resolution.success
    board = resolution.board
    assert board.is_check()
    assert len(list(board.legal_moves)) > 0
    assert game_outcome(board) is None


def test_dep_allowed_while_in_check() -> None:
    fen = "4k3/8/8/8/8/8/3N4/r3K3 w - - 0 1"
    assert opts(fen)["d2"] == {"R": True, "Q": True}
    b = chess.Board(fen)
    assert b.is_check()
    resolution = resolve_dep(b, "d2", "Q", roll_value=0.99, multiplier=1.0)
    assert not resolution.success
    board = resolution.board
    assert board.is_check()
    assert len(list(board.legal_moves)) > 0


def test_dep_fail_leads_to_selfmate() -> None:
    fen = "k7/8/8/8/8/8/6PP/r2N3K w - - 0 1"
    assert opts(fen)["d1"] == {"R": True, "Q": True}
    b = chess.Board(fen)
    resolution = resolve_dep(b, "d1", "R", roll_value=0.99, multiplier=1.0)
    assert not resolution.success
    assert game_outcome(resolution.board) == Outcome(result="black", end_reason="checkmate")
    b = chess.Board(fen)
    resolution = resolve_dep(b, "d1", "R", roll_value=0.0, multiplier=1.0)
    assert resolution.success
    assert game_outcome(resolution.board) is None


def test_dep_fail_leads_to_stalemate() -> None:
    fen = "N7/8/8/8/8/7p/5k1P/7K w - - 0 1"
    b = chess.Board(fen)
    resolution = resolve_dep(b, "a8", "Q", roll_value=0.99, multiplier=1.0)
    assert not resolution.success
    assert game_outcome(resolution.board) == Outcome(result="draw", end_reason="stalemate")
    b = chess.Board(fen)
    resolution = resolve_dep(b, "a8", "Q", roll_value=0.0, multiplier=1.0)
    assert resolution.success
    assert game_outcome(resolution.board) is None


def test_dep_rook_clears_castling() -> None:
    fen = "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"
    for roll in (0.0, 0.99):
        resolution = resolve_dep(chess.Board(fen), "h1", "Q", roll_value=roll, multiplier=1.0)
        assert resolution.board.castling_xfen() == "Qkq"
    for roll in (0.0, 0.99):
        resolution = resolve_dep(chess.Board(fen), "a1", "Q", roll_value=roll, multiplier=1.0)
        assert resolution.board.castling_xfen() == "Kkq"
    bfen = "r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 1"
    resolution = resolve_dep(chess.Board(bfen), "a8", "Q", roll_value=0.99, multiplier=1.0)
    assert resolution.board.castling_xfen() == "KQk"
    resolution = resolve_dep(chess.Board(bfen), "h8", "Q", roll_value=0.0, multiplier=1.0)
    assert resolution.board.castling_xfen() == "KQq"


def test_dep_clears_en_passant() -> None:
    fen = "4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2"
    assert chess.Board(fen).has_legal_en_passant()
    resolution = resolve_dep(chess.Board(fen), "e5", "N", roll_value=0.0, multiplier=1.0)
    assert resolution.success
    assert resolution.board.ep_square is None
    resolution = resolve_dep(chess.Board(fen), "e5", "N", roll_value=0.99, multiplier=1.0)
    assert not resolution.success
    assert resolution.board.ep_square is None


def test_dep_resets_halfmove_clock() -> None:
    fen = "4k3/8/8/8/8/8/P7/4K3 w - - 57 80"
    for roll in (0.0, 0.99):
        resolution = resolve_dep(chess.Board(fen), "a2", "R", roll_value=roll, multiplier=1.0)
        assert resolution.board.halfmove_clock == 0
        assert resolution.board.fullmove_number == 80


def test_dep_insufficient_material() -> None:
    fen = "4k3/8/8/8/8/8/P7/4K3 w - - 0 1"
    resolution = resolve_dep(chess.Board(fen), "a2", "R", roll_value=0.99, multiplier=1.0)
    assert not resolution.success
    assert game_outcome(resolution.board) == Outcome(
        result="draw", end_reason="insufficient_material")
    resolution = resolve_dep(chess.Board(fen), "a2", "N", roll_value=0.0, multiplier=1.0)
    assert resolution.success
    assert game_outcome(resolution.board) == Outcome(
        result="draw", end_reason="insufficient_material")
    resolution = resolve_dep(chess.Board(fen), "a2", "R", roll_value=0.0, multiplier=1.0)
    assert resolution.success
    assert game_outcome(resolution.board) is None


def test_dep_probability() -> None:
    rng = random.Random(42)
    total = 10000
    successes = 0
    for _ in range(total):
        resolution = resolve_dep(chess.Board(chess.STARTING_FEN), "b1", "Q",
                                 roll_value=rng.random(), multiplier=1.0)
        if resolution.success:
            successes += 1
    share = successes / total
    assert 1 / 3 - 0.02 <= share <= 1 / 3 + 0.02


# --- Ходы и окончание партии ---------------------------------------------------


def test_apply_move_ok_and_illegal() -> None:
    b = chess.Board(chess.STARTING_FEN)
    result = apply_move(b, "e2e4")
    assert result.san == "e4"
    assert result.irreversible is True
    assert result.board.move_stack == []
    assert b.fen() == chess.STARTING_FEN
    for bad_uci in ["e2e5", "zzzz", ""]:
        with pytest.raises(EngineError) as exc_info:
            apply_move(chess.Board(chess.STARTING_FEN), bad_uci)
        assert exc_info.value.code == "ILLEGAL_MOVE"


def test_apply_move_promotion() -> None:
    fen = "8/P7/8/8/8/8/8/k6K w - - 0 1"
    result = apply_move(chess.Board(fen), "a7a8q")
    piece = result.board.piece_at(sq("a8"))
    assert piece is not None
    assert piece.color == chess.WHITE
    assert piece.piece_type == chess.QUEEN
    with pytest.raises(EngineError) as exc_info:
        apply_move(chess.Board(fen), "a7a8")
    assert exc_info.value.code == "ILLEGAL_MOVE"


def test_fools_mate() -> None:
    board = chess.Board(chess.STARTING_FEN)
    for uci in ["f2f3", "e7e5", "g2g4", "d8h4"]:
        board = apply_move(board, uci).board
    assert game_outcome(board) == Outcome(result="black", end_reason="checkmate")


def test_fifty_move_rule() -> None:
    assert game_outcome(chess.Board("4k3/8/8/8/8/8/R7/4K3 w - - 99 120")) is None
    outcome = game_outcome(chess.Board("4k3/8/8/8/8/8/R7/4K3 w - - 100 120"))
    assert outcome == Outcome(result="draw", end_reason="fifty_move")


def test_threefold() -> None:
    b = chess.Board(chess.STARTING_FEN)
    assert game_outcome(b, 2) is None
    assert game_outcome(b, 3) == Outcome(result="draw", end_reason="threefold")


def test_position_key() -> None:
    fen_a = "4k3/8/8/8/8/8/R7/4K3 w - - 5 10"
    fen_b = "4k3/8/8/8/8/8/R7/4K3 w - - 9 30"
    assert position_key(chess.Board(fen_a)) == position_key(chess.Board(fen_b))
    fen_c = "4k3/8/8/8/3P4/8/8/4K3 b - d3 0 1"
    fen_d = "4k3/8/8/8/3P4/8/8/4K3 b - - 0 1"
    assert position_key(chess.Board(fen_c)) == position_key(chess.Board(fen_d))


def test_can_win_on_time() -> None:
    b = chess.Board("4k3/8/8/8/8/8/8/N3K3 w - - 0 1")
    assert can_win_on_time(b, "white") is False
    assert can_win_on_time(b, "black") is False
    b = chess.Board("4k3/8/8/8/8/8/R7/4K3 w - - 0 1")
    assert can_win_on_time(b, "white") is True
    assert can_win_on_time(b, "black") is False
    with pytest.raises(ValueError):
        can_win_on_time(b, "purple")


def test_board_squares() -> None:
    squares = board_squares(chess.Board(chess.STARTING_FEN))
    assert len(squares) == 32
    assert squares[0] == {"square": "a1", "piece": "R", "color": "white"}
    assert squares[-1] == {"square": "h8", "piece": "R", "color": "black"}


def test_legal_moves_uci() -> None:
    moves = legal_moves_uci(chess.Board(chess.STARTING_FEN))
    assert len(moves) == 20
    assert moves == sorted(moves)
    assert "g1f3" in moves


# --- Чистота модуля ------------------------------------------------------------


def test_engine_is_pure() -> None:
    engine_dir = pathlib.Path(__file__).resolve().parents[1] / "app" / "chess_engine"
    forbidden = ["import random", "import secrets", "sqlalchemy", "fastapi", "redis",
                 "from app.db", "from app.services", "from app.core"]
    paths = sorted(engine_dir.glob("*.py"))
    assert paths
    for path in paths:
        source = path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in source, f"{path.name} contains {needle!r}"
