from app.core.errors import AppError
from app.redis import redis_client

_RATE_LIMITED = AppError(429, "RATE_LIMITED", "Слишком много запросов, подождите")


async def hit(key: str, limit: int, window_s: int) -> None:
    value = await incr(key, window_s)
    if value > limit:
        raise _RATE_LIMITED


async def count(key: str) -> int:
    value = await redis_client.get(key)
    return int(value) if value is not None else 0


async def incr(key: str, window_s: int) -> int:
    pipe = redis_client.pipeline()
    pipe.incr(key)
    pipe.expire(key, window_s, nx=True)
    result = await pipe.execute()
    return int(result[0])
