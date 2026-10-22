from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError

from app.api import (
    admin,
    admin_catalog,
    auth,
    chat,
    config,
    game_history,
    games,
    gifts,
    health,
    internal,
    invites,
    items,
    leaderboard,
    market,
    matchmaking,
    me,
    ws,
)
from app.core.errors import (
    AppError,
    app_error_handler,
    http_exception_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.core.origin import OriginMiddleware
from app.db import engine
from app.redis import redis_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await redis_client.aclose()
    await engine.dispose()


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

app.add_middleware(OriginMiddleware)

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_error_handler)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(me.router)
app.include_router(internal.router)
app.include_router(config.router)
app.include_router(games.router)
app.include_router(game_history.router)
app.include_router(chat.router)
app.include_router(matchmaking.router)
app.include_router(invites.router)
app.include_router(ws.router)
app.include_router(items.router)
app.include_router(admin_catalog.router)
app.include_router(admin.router)
app.include_router(market.router)
app.include_router(gifts.router)
app.include_router(leaderboard.router)
