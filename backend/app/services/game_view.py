import uuid
from datetime import datetime

import chess
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chess_engine import (
    DEP_LIMIT_PER_GAME,
    board_squares,
    legal_moves_uci,
    list_dep_options,
)
from app.core.clock import to_ms
from app.models import Game, GameEvent, User
from app.schemas.games import (
    ClocksOut,
    DepOptionsOut,
    DepPieceOut,
    DepTargetOut,
    DepsOut,
    GameStateOut,
    PlayerInfoOut,
)
from app.services.game_clock import remaining_ms, turn_color


async def game_players(db: AsyncSession, game: Game) -> dict[str, User]:
    user_ids = [game.white_id, game.black_id]
    users = (
        await db.scalars(
            select(User)
            .where(User.id.in_(user_ids))
            .execution_options(populate_existing=True)
        )
    ).all()
    by_id = {user.id: user for user in users}
    return {"white": by_id[game.white_id], "black": by_id[game.black_id]}


async def last_game_action(db: AsyncSession, game_id: uuid.UUID) -> dict | None:
    event = await db.scalar(
        select(GameEvent)
        .where(GameEvent.game_id == game_id, GameEvent.kind.in_(("move", "dep")))
        .order_by(GameEvent.seq.desc())
        .limit(1)
    )
    if event is None:
        return None
    return {"kind": event.kind, **dict(event.payload)}


def build_state(
    game: Game,
    viewer_user_id: int,
    players: dict[str, User],
    now: datetime,
    last_action: dict | None = None,
) -> GameStateOut:
    board = chess.Board(game.fen)
    turn = turn_color(game)
    turn_board_color = chess.WHITE if turn == "white" else chess.BLACK
    active = game.status == "active"
    if viewer_user_id == game.white_id:
        you = "white"
    elif viewer_user_id == game.black_id:
        you = "black"
    else:
        you = "spectator"
    legal_moves = legal_moves_uci(board) if active and you == turn else []
    check_square = None
    if board.is_check():
        king = board.king(turn_board_color)
        if king is not None:
            check_square = chess.square_name(king)
    running = turn if game.clock_running and active else None
    return GameStateOut(
        id=str(game.id),
        version=game.version,
        status=game.status,
        time_control=game.time_control,
        you=you,
        turn=turn,
        ply=game.ply,
        board=board_squares(board),
        legal_moves=legal_moves,
        check_square=check_square,
        last_action=last_action,
        clocks=ClocksOut(
            white_ms=remaining_ms(game, "white", now),
            black_ms=remaining_ms(game, "black", now),
            running=running,
            server_time_ms=to_ms(now),
        ),
        deps=DepsOut(
            limit=DEP_LIMIT_PER_GAME,
            white_used=game.white_deps,
            black_used=game.black_deps,
            used_this_turn=game.dep_used_this_turn,
        ),
        draw_offer_by=game.draw_offer_by,
        result=game.result,
        end_reason=game.end_reason,
        players={
            "white": PlayerInfoOut(
                login=players["white"].login,
                elo=players["white"].elo,
                loadout=game.white_loadout or {},
            ),
            "black": PlayerInfoOut(
                login=players["black"].login,
                elo=players["black"].elo,
                loadout=game.black_loadout or {},
            ),
        },
    )


def build_dep_options(game: Game, viewer_color: str, multiplier: float) -> DepOptionsOut:
    active = game.status == "active"
    turn = turn_color(game)
    used = game.white_deps if viewer_color == "white" else game.black_deps
    deps_left = DEP_LIMIT_PER_GAME - used
    reason = None
    if not active:
        reason = "GAME_NOT_ACTIVE"
    elif viewer_color != turn:
        reason = "NOT_YOUR_TURN"
    elif game.dep_used_this_turn:
        reason = "DEP_ALREADY_USED_THIS_TURN"
    elif deps_left <= 0:
        reason = "DEP_LIMIT_REACHED"
    pieces = []
    for option in list_dep_options(chess.Board(game.fen), multiplier):
        pieces.append(
            DepPieceOut(
                square=option.square,
                piece=option.piece,
                targets=[
                    DepTargetOut(
                        piece=target.piece,
                        chance=target.chance,
                        chance_text=target.chance_text,
                        allowed=target.allowed,
                        reason=target.reason,
                    )
                    for target in option.targets
                ],
            )
        )
    return DepOptionsOut(
        available=reason is None,
        unavailable_reason=reason,
        deps_left=deps_left,
        pieces=pieces,
    )
