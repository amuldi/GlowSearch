from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Protocol

import httpx

from app.core.config import Settings
from app.indexing.store import ProductIndexStore
from app.models.product import ProductSourceRecord
from app.normalizer.text import clean_text
from app.parser.oliveyoung_html import parse_detail_page


class ProductDetailEnricher(Protocol):
    async def enrich(self, records: list[ProductSourceRecord]) -> list[ProductSourceRecord]: ...


class SourceDiscoveryAgent:
    def __init__(
        self,
        seed_queries: Iterable[str],
        *,
        category_queries: Iterable[str] = (),
        brand_queries: Iterable[str] = (),
        max_seed_queries: int | None = None,
    ):
        self._seed_queries = tuple(seed_queries)
        self._category_queries = tuple(category_queries)
        self._brand_queries = tuple(brand_queries)
        self._max_seed_queries = max_seed_queries

    def seed_queries(self) -> list[str]:
        queries = self._dedupe(
            [
                *self._seed_queries,
                *self._category_queries,
                *self._brand_queries,
            ]
        )
        if self._max_seed_queries is not None and self._max_seed_queries >= 0:
            return queries[: self._max_seed_queries]
        return queries

    def category_queries(self) -> list[str]:
        return self._dedupe(self._category_queries)

    def brand_queries(self) -> list[str]:
        return self._dedupe(self._brand_queries)

    @staticmethod
    def _dedupe(values: Iterable[str]) -> list[str]:
        queries: list[str] = []
        seen: set[str] = set()
        for value in values:
            query = clean_text(value)
            key = query.casefold() if query else ""
            if not query or key in seen:
                continue
            seen.add(key)
            queries.append(query)
        return queries


class OliveYoungDetailEnrichmentAgent:
    def __init__(self, settings: Settings):
        self._base_url = settings.oliveyoung_base_url.rstrip("/")
        self._timeout = settings.request_timeout_seconds
        self._user_agent = settings.request_user_agent
        self._max_records = max(settings.product_index_detail_enrichment_max_records, 1)
        self._concurrency = max(settings.detail_concurrency, 1)

    async def enrich(self, records: list[ProductSourceRecord]) -> list[ProductSourceRecord]:
        if not records:
            return records
        enriched = list(records)
        candidates = [
            (index, record)
            for index, record in enumerate(records)
            if self._should_enrich(record)
        ][: self._max_records]
        if not candidates:
            return records

        semaphore = asyncio.Semaphore(self._concurrency)
        async with httpx.AsyncClient(
            timeout=self._timeout,
            headers=self._headers(),
            follow_redirects=True,
        ) as client:

            async def enrich_one(index: int, record: ProductSourceRecord) -> None:
                async with semaphore:
                    detail = await self._fetch_detail(client, record)
                    if detail is not None:
                        enriched[index] = self._merge(record, detail)

            await asyncio.gather(
                *(enrich_one(index, record) for index, record in candidates),
                return_exceptions=True,
            )
        return enriched

    @staticmethod
    def _should_enrich(record: ProductSourceRecord) -> bool:
        return bool(
            record.source_url
            and (record.source == "oliveyoung" or record.source.startswith("oliveyoung:"))
        )

    async def _fetch_detail(
        self,
        client: httpx.AsyncClient,
        record: ProductSourceRecord,
    ) -> ProductSourceRecord | None:
        if not record.source_url:
            return None
        try:
            response = await client.get(record.source_url)
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        return parse_detail_page(
            response.text,
            base_url=self._base_url,
            source_url=record.source_url,
        )

    @staticmethod
    def _merge(
        record: ProductSourceRecord,
        detail: ProductSourceRecord,
    ) -> ProductSourceRecord:
        detail_has_price = any(
            price is not None
            for price in [detail.regular_price, detail.original_price, detail.sale_price]
        )
        return record.model_copy(
            update={
                "source_brand_name": detail.source_brand_name or record.source_brand_name,
                "product_name_ko": detail.product_name_ko or record.product_name_ko,
                "regular_price": (
                    detail.regular_price
                    if detail.regular_price is not None
                    else record.regular_price
                ),
                "original_price": (
                    detail.original_price
                    if detail.original_price is not None
                    else record.original_price
                ),
                "sale_price": detail.sale_price if detail_has_price else record.sale_price,
                "discount_rate": (
                    detail.discount_rate if detail_has_price else record.discount_rate
                ),
                "currency": detail.currency or record.currency,
                "shade": detail.shade or record.shade,
                "image_url": detail.image_url or record.image_url,
                "source_url": detail.source_url or record.source_url,
                "source_product_id": detail.source_product_id or record.source_product_id,
            }
        )

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }


class ProductIngestionAgent:
    def __init__(
        self,
        store: ProductIndexStore,
        detail_enricher: ProductDetailEnricher | None = None,
    ):
        self._store = store
        self._detail_enricher = detail_enricher

    async def ingest_search_results(
        self,
        queries: Iterable[str],
        records: list[ProductSourceRecord],
    ) -> None:
        clean_queries = [query for query in (clean_text(query) for query in queries) if query]
        if not clean_queries or not records:
            return
        if self._detail_enricher is not None:
            records = await self._detail_enricher.enrich(records)
        for query in clean_queries:
            await self._store.upsert_search_results(query, records)
