import pytest

from app.cache.ttl import AsyncTTLCache


@pytest.mark.asyncio
async def test_async_ttl_cache_returns_value_before_expiry() -> None:
    cache = AsyncTTLCache[str](ttl_seconds=60)

    await cache.set("key", "value")

    assert await cache.get("key") == "value"


@pytest.mark.asyncio
async def test_async_ttl_cache_expires_values() -> None:
    cache = AsyncTTLCache[str](ttl_seconds=0)

    await cache.set("key", "value")

    assert await cache.get("key") is None
