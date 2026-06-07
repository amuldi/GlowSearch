from __future__ import annotations

from collections.abc import Iterable

from app.indexing.store import ProductIndexStore
from app.models.product import ProductSourceRecord
from app.normalizer.text import clean_text


class SourceDiscoveryAgent:
    def __init__(self, seed_queries: Iterable[str]):
        self._seed_queries = tuple(seed_queries)

    def seed_queries(self) -> list[str]:
        queries: list[str] = []
        seen: set[str] = set()
        for seed in self._seed_queries:
            query = clean_text(seed)
            key = query.casefold() if query else ""
            if not query or key in seen:
                continue
            seen.add(key)
            queries.append(query)
        return queries


class ProductIngestionAgent:
    def __init__(self, store: ProductIndexStore):
        self._store = store

    async def ingest_search_results(
        self,
        queries: Iterable[str],
        records: list[ProductSourceRecord],
    ) -> None:
        clean_queries = [query for query in (clean_text(query) for query in queries) if query]
        if not clean_queries or not records:
            return
        for query in clean_queries:
            await self._store.upsert_search_results(query, records)
