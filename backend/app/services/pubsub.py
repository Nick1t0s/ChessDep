import json
import uuid

from redis.asyncio.client import PubSub

from app.redis import redis_client


def game_channel(game_id: uuid.UUID) -> str:
    return f"game:{game_id}"


async def publish_game(game_id: uuid.UUID, message: dict) -> None:
    await redis_client.publish(game_channel(game_id), json.dumps(message))


async def subscribe(channel: str) -> PubSub:
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel)
    return pubsub


async def unsubscribe(pubsub: PubSub, channel: str) -> None:
    await pubsub.unsubscribe(channel)
