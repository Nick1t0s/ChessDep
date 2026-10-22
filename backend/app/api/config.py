from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.chess_engine import DEP_LIMIT_PER_GAME
from app.db import get_db
from app.services.settings import get_setting

router = APIRouter(prefix="/api/v1", tags=["config"])


@router.get("/config")
async def public_config(db: Annotated[AsyncSession, Depends(get_db)]) -> dict:
    return {
        "time_controls": await get_setting(db, "time_controls"),
        "dep_limit": DEP_LIMIT_PER_GAME,
    }
