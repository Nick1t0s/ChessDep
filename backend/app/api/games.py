import uuid
from typing import Annotated

import app.core.clock as clock
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user
from app.core.errors import AppError
from app.core.ratelimit import hit
from app.db import get_db
from app.models import Game, User
from app.schemas.games import (
    ActionIn,
    DepIn,
    DepOptionsOut,
    DepResultOut,
    GameStateOut,
    MoveIn,
)
from app.services import games
from app.services.game_view import build_dep_options, build_state, game_players, last_game_action
from app.services.settings import get_setting

router = APIRouter(prefix="/api/v1", tags=["games"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(current_user)]

_GAME_NOT_FOUND = AppError(404, "GAME_NOT_FOUND", "Партия не найдена")


async def _get_player_game(db: AsyncSession, game_id: uuid.UUID, user_id: int) -> Game:
    game = await db.get(Game, game_id)
    if game is None:
        raise _GAME_NOT_FOUND
    games.color_of(game, user_id)
    return game


async def _state(db: AsyncSession, game: Game, user_id: int) -> GameStateOut:
    players = await game_players(db, game)
    last_action = await last_game_action(db, game.id)
    return build_state(game, user_id, players, clock.now(), last_action)


@router.get("/games/{game_id}", response_model=GameStateOut)
async def get_game(game_id: uuid.UUID, user: UserDep, db: DbDep) -> GameStateOut:
    game = await _get_player_game(db, game_id, user.id)
    return await _state(db, game, user.id)


@router.get("/games/{game_id}/dep-options", response_model=DepOptionsOut)
async def get_dep_options(game_id: uuid.UUID, user: UserDep, db: DbDep) -> DepOptionsOut:
    game = await _get_player_game(db, game_id, user.id)
    color = games.color_of(game, user.id)
    multiplier = float(await get_setting(db, "dep_multiplier"))
    return build_dep_options(game, color, multiplier)


@router.post("/games/{game_id}/move", response_model=GameStateOut)
async def post_move(game_id: uuid.UUID, body: MoveIn, user: UserDep, db: DbDep) -> GameStateOut:
    await hit(f"rl:game:{user.id}", 10, 1)
    game = await games.do_move(db, user, game_id, body.uci, body.expected_version, clock.now())
    return await _state(db, game, user.id)


@router.post("/games/{game_id}/dep", response_model=DepResultOut)
async def post_dep(game_id: uuid.UUID, body: DepIn, user: UserDep, db: DbDep) -> DepResultOut:
    await hit(f"rl:game:{user.id}", 10, 1)
    game, resolution, roll_id = await games.do_dep(
        db, user, game_id, body.square, body.target, body.expected_version, clock.now()
    )
    return DepResultOut(
        success=resolution.success,
        square=resolution.square,
        from_=resolution.from_piece,
        to=resolution.to_piece,
        chance=resolution.chance,
        chance_text=resolution.chance_text,
        roll_value=resolution.roll_value,
        roll_id=roll_id,
        state=await _state(db, game, user.id),
    )


@router.post("/games/{game_id}/resign", response_model=GameStateOut)
async def post_resign(
    game_id: uuid.UUID, user: UserDep, db: DbDep, body: ActionIn | None = None
) -> GameStateOut:
    await hit(f"rl:game:{user.id}", 10, 1)
    expected = body.expected_version if body is not None else None
    game = await games.do_resign(db, user, game_id, expected, clock.now())
    return await _state(db, game, user.id)


@router.post("/games/{game_id}/draw/offer", response_model=GameStateOut)
async def post_draw_offer(
    game_id: uuid.UUID, user: UserDep, db: DbDep, body: ActionIn | None = None
) -> GameStateOut:
    await hit(f"rl:game:{user.id}", 10, 1)
    expected = body.expected_version if body is not None else None
    game = await games.do_draw_offer(db, user, game_id, expected, clock.now())
    return await _state(db, game, user.id)


@router.post("/games/{game_id}/draw/accept", response_model=GameStateOut)
async def post_draw_accept(
    game_id: uuid.UUID, user: UserDep, db: DbDep, body: ActionIn | None = None
) -> GameStateOut:
    await hit(f"rl:game:{user.id}", 10, 1)
    expected = body.expected_version if body is not None else None
    game = await games.do_draw_accept(db, user, game_id, expected, clock.now())
    return await _state(db, game, user.id)


@router.post("/games/{game_id}/draw/decline", response_model=GameStateOut)
async def post_draw_decline(
    game_id: uuid.UUID, user: UserDep, db: DbDep, body: ActionIn | None = None
) -> GameStateOut:
    await hit(f"rl:game:{user.id}", 10, 1)
    expected = body.expected_version if body is not None else None
    game = await games.do_draw_decline(db, user, game_id, expected, clock.now())
    return await _state(db, game, user.id)


@router.post("/games/{game_id}/abort", response_model=GameStateOut)
async def post_abort(
    game_id: uuid.UUID, user: UserDep, db: DbDep, body: ActionIn | None = None
) -> GameStateOut:
    await hit(f"rl:game:{user.id}", 10, 1)
    expected = body.expected_version if body is not None else None
    game = await games.do_abort(db, user, game_id, expected, clock.now())
    return await _state(db, game, user.id)
