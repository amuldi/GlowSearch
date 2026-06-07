from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic


SleepFunc = Callable[[float], Awaitable[None]]


BOT_DETECTION_MARKERS = (
    "cf_chl",
    "cf-chl",
    "cloudflare",
    "enable javascript and cookies",
    "captcha",
    "bot detection",
    "잠시만 기다려 주세요",
    "자동화된 요청",
)


@dataclass(frozen=True)
class RetryConfig:
    attempts: int = 2
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 4.0
    jitter_ratio: float = 0.15


class AsyncRateLimiter:
    def __init__(
        self,
        *,
        requests_per_second: float,
        sleep: SleepFunc = asyncio.sleep,
    ):
        self._min_interval_seconds = (
            0.0 if requests_per_second <= 0 else 1.0 / requests_per_second
        )
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._next_allowed_at = 0.0

    async def wait(self) -> None:
        if self._min_interval_seconds <= 0:
            return
        async with self._lock:
            now = monotonic()
            wait_seconds = self._next_allowed_at - now
            if wait_seconds > 0:
                await self._sleep(wait_seconds)
                now = monotonic()
            self._next_allowed_at = now + self._min_interval_seconds


def backoff_delay_seconds(attempt_index: int, config: RetryConfig) -> float:
    base = max(config.base_delay_seconds, 0.0)
    capped = min(base * (2 ** max(attempt_index, 0)), max(config.max_delay_seconds, 0.0))
    jitter_ratio = max(config.jitter_ratio, 0.0)
    if capped <= 0 or jitter_ratio <= 0:
        return capped
    return capped + random.uniform(0, capped * jitter_ratio)


def is_bot_detection_response(
    *,
    status_code: int,
    text: str | None = None,
    headers: dict[str, str] | None = None,
) -> bool:
    if status_code in {403, 429, 503}:
        return True
    normalized_headers = {key.casefold(): value.casefold() for key, value in (headers or {}).items()}
    if normalized_headers.get("cf-mitigated") == "challenge":
        return True
    if "captcha" in normalized_headers.get("x-captcha", ""):
        return True
    body = (text or "").casefold()
    return any(marker in body for marker in BOT_DETECTION_MARKERS)
