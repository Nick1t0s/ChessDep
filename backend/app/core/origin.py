from collections.abc import Awaitable, Callable

from fastapi.responses import JSONResponse
from starlette.datastructures import Headers

from app.config import settings

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_BAD_ORIGIN_BODY = {
    "error": {"code": "BAD_ORIGIN", "message": "Запрос с недопустимого источника"}
}


class OriginMiddleware:
    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            method = str(scope.get("method", "")).upper()
            if method not in _SAFE_METHODS and not self._origin_allowed(scope):
                response = JSONResponse(status_code=403, content=_BAD_ORIGIN_BODY)
                await response(scope, receive, send)
                return
        elif scope["type"] == "websocket":
            if not self._origin_allowed(scope):
                await send({"type": "websocket.close", "code": 4403})
                return
        await self.app(scope, receive, send)

    @staticmethod
    def _origin_allowed(scope) -> bool:
        headers = Headers(scope=scope)
        origin = headers.get("origin")
        return origin is not None and origin in settings.allowed_origins
