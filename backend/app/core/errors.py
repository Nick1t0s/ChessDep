import logging
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _body(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content=_body(exc.code, exc.message))


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(status_code=422, content=_body("VALIDATION_ERROR", "Некорректные данные"))


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    if exc.status_code == 404:
        return JSONResponse(status_code=404, content=_body("NOT_FOUND", "Не найдено"))
    if exc.status_code == 405:
        return JSONResponse(
            status_code=405, content=_body("METHOD_NOT_ALLOWED", "Метод не разрешён")
        )
    return JSONResponse(
        status_code=exc.status_code, content=_body("HTTP_ERROR", "Ошибка запроса")
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content=_body("INTERNAL", "Внутренняя ошибка"))
