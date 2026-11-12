from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user
from app.db import get_db
from app.models.user import User
from app.schemas.trade_history import TradeHistoryPageOut
from app.services.trade_history import get_trade_history

router = APIRouter(prefix="/api/v1", tags=["trade_history"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(current_user)]


@router.get("/me/trades", response_model=TradeHistoryPageOut)
async def list_user_trades(
    user: UserDep,
    db: DbDep,
    before_id: Annotated[int | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    item_def_id: Annotated[int | None, Query()] = None,
    direction: Annotated[Literal["all", "buy", "sell"], Query()] = "all",
) -> TradeHistoryPageOut:
    return await get_trade_history(
        db,
        user.id,
        before_id=before_id,
        limit=limit,
        item_def_id=item_def_id,
        direction=direction,
    )
