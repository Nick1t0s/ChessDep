from datetime import datetime

import chess
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chess_engine import board_squares
from app.core.errors import AppError
from app.models import Game, GameEvent, User
from app.schemas.games import GameHistoryItem, GamesHistoryOut, PieceSquareOut
from app.schemas.history import (
    EventGameOut,
    EventPlayerOut,
    GameEventsOut,
    HistoryEventOut,
    ProfileGamesOut,
    ProfileOut,
)


def _check_square(board: chess.Board) -> str | None:
    if not board.is_check():
        return None
    king = board.king(board.turn)
    if king is None:
        return None
    return chess.square_name(king)


def _event_out(event: GameEvent) -> HistoryEventOut:
    board = chess.Board(event.fen_after)
    return HistoryEventOut(
        seq=event.seq,
        ply=event.ply,
        kind=event.kind,
        actor=event.actor,
        payload=dict(event.payload),
        board=[PieceSquareOut(**square) for square in board_squares(board)],
        check_square=_check_square(board),
        white_ms=event.white_ms,
        black_ms=event.black_ms,
        created_at=event.created_at,
    )


async def game_events(db: AsyncSession, game: Game, after_seq: int) -> dict:
    players = (
        await db.scalars(
            select(User)
            .where(User.id.in_((game.white_id, game.black_id)))
            .execution_options(populate_existing=True)
        )
    ).all()
    by_id = {user.id: user for user in players}
    events = (
        await db.scalars(
            select(GameEvent)
            .where(GameEvent.game_id == game.id, GameEvent.seq > after_seq)
            .order_by(GameEvent.seq)
        )
    ).all()
    out = GameEventsOut(
        game=EventGameOut(
            id=str(game.id),
            status=game.status,
            result=game.result,
            end_reason=game.end_reason,
            time_control=game.time_control,
            white=EventPlayerOut(
                login=by_id[game.white_id].login, elo=game.white_elo_before
            ),
            black=EventPlayerOut(
                login=by_id[game.black_id].login, elo=game.black_elo_before
            ),
            white_loadout=game.white_loadout or {},
            black_loadout=game.black_loadout or {},
            created_at=game.created_at,
            finished_at=game.finished_at,
            initial_board=[PieceSquareOut(**square) for square in board_squares(chess.Board())],
        ),
        events=[_event_out(event) for event in events],
    )
    return out.model_dump(mode="json")


async def user_by_login(db: AsyncSession, login: str) -> User:
    user = await db.scalar(select(User).where(User.login == login))
    if user is None:
        raise AppError(404, "USER_NOT_FOUND", "Игрок не найден")
    return user


async def user_profile(db: AsyncSession, login: str) -> dict:
    user = await user_by_login(db, login)
    rows = (
        await db.execute(
            select(Game.white_id, Game.black_id, Game.result).where(
                or_(Game.white_id == user.id, Game.black_id == user.id),
                Game.status == "finished",
            )
        )
    ).all()
    played = wins = draws = losses = 0
    for white_id, black_id, result in rows:
        color = "white" if white_id == user.id else "black"
        played += 1
        if result == "draw":
            draws += 1
        elif result == color:
            wins += 1
        else:
            losses += 1
    out = ProfileOut(
        login=user.login,
        elo=user.elo,
        created_at=user.created_at,
        games=ProfileGamesOut(played=played, wins=wins, draws=draws, losses=losses),
    )
    return out.model_dump(mode="json")


async def user_games(
    db: AsyncSession, user: User, before: datetime | None, limit: int
) -> dict:
    query = select(Game).where(
        or_(Game.white_id == user.id, Game.black_id == user.id),
        Game.status.in_(("finished", "aborted")),
    )
    if before is not None:
        query = query.where(Game.finished_at < before)
    query = query.order_by(Game.finished_at.desc()).limit(limit)
    games = (await db.scalars(query)).all()
    user_ids: set[int] = set()
    for game in games:
        user_ids.update((game.white_id, game.black_id))
    users = {
        u.id: u
        for u in (
            (await db.scalars(select(User).where(User.id.in_(user_ids)))).all()
        )
    }
    items = []
    for game in games:
        if game.white_id == user.id:
            color, opponent_id = "white", game.black_id
            elo_delta = (
                game.white_elo_after - game.white_elo_before
                if game.white_elo_after is not None
                else None
            )
        else:
            color, opponent_id = "black", game.white_id
            elo_delta = (
                game.black_elo_after - game.black_elo_before
                if game.black_elo_after is not None
                else None
            )
        items.append(
            GameHistoryItem(
                id=str(game.id),
                opponent_login=users[opponent_id].login,
                color=color,
                result=game.result,
                end_reason=game.end_reason,
                time_control=game.time_control,
                finished_at=game.finished_at,
                elo_delta=elo_delta,
            )
        )
    page = GamesHistoryOut(
        items=items,
        next_before=(
            items[-1].finished_at.isoformat() if items and len(items) == limit else None
        ),
    )
    return page.model_dump(mode="json")
