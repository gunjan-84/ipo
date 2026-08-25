import json
import os

import redis.asyncio as redis

_TTL_SECONDS = int(os.environ.get("CONNECTION_TTL_SECONDS", 60 * 60 * 20))  # ~20h, matches Kite's daily enctoken expiry

client = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"), decode_responses=True)


def _key_for(account_id: str) -> str:
    return f"conn:{account_id}"


async def get(account_id: str):
    raw = await client.get(_key_for(account_id))
    return json.loads(raw) if raw else None


async def set(account_id: str, data: dict):
    await client.set(_key_for(account_id), json.dumps(data), ex=_TTL_SECONDS)


async def delete(account_id: str):
    await client.delete(_key_for(account_id))


async def connected_account_ids():
    keys = await client.keys("conn:*")
    return [k[len("conn:") :] for k in keys]
