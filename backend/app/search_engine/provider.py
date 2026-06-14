from __future__ import annotations

from typing import Protocol

from app.models.product import ProductSourceRecord
from app.search_engine.query import SearchQuery, SearchResultPage


class SearchProvider(Protocol):
    name: str

    async def search(self, query: SearchQuery) -> SearchResultPage:
        ...

    async def autocomplete(self, prefix: str, limit: int) -> list[str]:
        ...

    async def upsert_products(self, products: list[ProductSourceRecord]) -> None:
        ...

    async def close(self) -> None:
        ...
