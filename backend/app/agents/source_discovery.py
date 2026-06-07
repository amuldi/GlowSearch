from __future__ import annotations

import asyncio

from app.source_adapters.base import DiscoveredSource, DiscoveryAdapter


class SourceDiscoveryAgent:
    """Find candidate product URLs and source pages for later ingestion."""

    def __init__(self, adapters: list[DiscoveryAdapter]):
        self._adapters = adapters

    async def discover(self, keyword: str, limit: int) -> list[DiscoveredSource]:
        if not keyword.strip() or limit <= 0 or not self._adapters:
            return []

        async def run(adapter: DiscoveryAdapter) -> list[DiscoveredSource]:
            try:
                return await asyncio.wait_for(
                    adapter.discover(keyword, limit),
                    timeout=adapter.metadata.timeout_seconds,
                )
            except Exception:
                return []

        discovered = await asyncio.gather(*(run(adapter) for adapter in self._adapters))
        return self._dedupe([source for sources in discovered for source in sources])[:limit]

    @staticmethod
    def _dedupe(sources: list[DiscoveredSource]) -> list[DiscoveredSource]:
        deduped: list[DiscoveredSource] = []
        seen: set[str] = set()
        for source in sources:
            key = source.url.strip().casefold()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(source)
        return deduped
