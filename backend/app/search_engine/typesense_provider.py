from __future__ import annotations

from app.models.product import ProductSourceRecord
from app.search_engine.provider import SearchProvider
from app.search_engine.query import SearchQuery, SearchResultPage


class TypesenseSearchProvider(SearchProvider):
    name = "typesense"

    async def search(self, query: SearchQuery) -> SearchResultPage:
        raise NotImplementedError("Typesense provider is not configured yet.")

    async def autocomplete(self, prefix: str, limit: int) -> list[str]:
        raise NotImplementedError("Typesense provider is not configured yet.")

    async def upsert_products(self, products: list[ProductSourceRecord]) -> None:
        raise NotImplementedError("Typesense provider is not configured yet.")

    async def close(self) -> None:
        return None
