from redis import asyncio as redis_asyncio

from app.config import settings

redis_client = redis_asyncio.from_url(settings.redis_url, decode_responses=True)
