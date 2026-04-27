from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Generic, TypeVar


T = TypeVar("T")


@dataclass
class _Entry(Generic[T]):
    value: T
    expires_at: float


class AsyncTTLCache(Generic[T]):
    def __init__(self, ttl_seconds: int, max_size: int = 512):
        self._ttl_seconds = ttl_seconds
        self._max_size = max_size
        self._items: dict[str, _Entry[T]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> T | None:
        now = time.monotonic()
        async with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            if item.expires_at <= now:
                self._items.pop(key, None)
                return None
            return item.value

    async def set(self, key: str, value: T) -> None:
        now = time.monotonic()
        async with self._lock:
            if len(self._items) >= self._max_size:
                oldest_key = min(self._items, key=lambda item_key: self._items[item_key].expires_at)
                self._items.pop(oldest_key, None)
            self._items[key] = _Entry(value=value, expires_at=now + self._ttl_seconds)
