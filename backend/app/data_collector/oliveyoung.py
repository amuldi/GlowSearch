from __future__ import annotations

import asyncio
import math
from urllib.parse import urlencode

import httpx

from app.core.config import Settings
from app.data_collector.base import SourceUnavailableError
from app.models.product import ProductSourceRecord
from app.parser.oliveyoung_html import parse_detail_page, parse_search_results


class OliveYoungCollector:
    name = "oliveyoung"

    def __init__(self, settings: Settings):
        self._settings = settings
        self._base_url = settings.oliveyoung_base_url.rstrip("/")

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        keyword = keyword.strip()
        if not keyword:
            return []

        async with httpx.AsyncClient(
            timeout=self._settings.request_timeout_seconds,
            headers=self._headers(),
            follow_redirects=True,
        ) as client:
            records = await self._fetch_search_records(client, keyword, limit)
            if self._should_enrich(records):
                records = await self._enrich_detail_pages(client, records)
            return records[:limit]

    async def _fetch_search_records(
        self,
        client: httpx.AsyncClient,
        keyword: str,
        limit: int,
    ) -> list[ProductSourceRecord]:
        page_size = max(1, min(self._settings.oliveyoung_search_page_size, 48))
        max_pages = max(1, self._settings.oliveyoung_search_max_pages)
        target_pages = min(max_pages, max(1, math.ceil(limit / page_size)))
        records: list[ProductSourceRecord] = []
        seen: set[str] = set()

        for page in range(1, target_pages + 1):
            html = await self._fetch_search_html(
                client,
                keyword,
                page=page,
                page_size=page_size,
            )
            page_records = parse_search_results(html, base_url=self._base_url, limit=page_size)
            new_records = []
            for record in page_records:
                key = record.source_product_id or f"{record.source_brand_name}:{record.product_name_ko}"
                if key in seen:
                    continue
                seen.add(key)
                new_records.append(record)
            if not new_records:
                break
            records.extend(new_records)
            if len(records) >= limit:
                break
        return records

    async def _fetch_search_html(
        self,
        client: httpx.AsyncClient,
        keyword: str,
        *,
        page: int,
        page_size: int,
    ) -> str:
        query = urlencode(
            {
                "query": keyword,
                "pageIdx": page,
                "rowsPerPage": page_size,
                "sort": "WEIGHT/DESC",
            }
        )
        url = f"{self._base_url}/store/search/getSearchMain.do?{query}"
        try:
            response = await client.get(url)
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"Olive Young request failed: {exc}") from exc

        if response.status_code in {403, 429}:
            raise SourceUnavailableError(
                f"Olive Young blocked the request with HTTP {response.status_code}"
            )
        if response.status_code >= 500:
            raise SourceUnavailableError(
                f"Olive Young returned temporary HTTP {response.status_code}"
            )
        response.raise_for_status()
        return response.text

    def _should_enrich(self, records: list[ProductSourceRecord]) -> bool:
        return (
            self._settings.detail_enrichment_enabled
            and bool(records)
            and len(records) <= self._settings.detail_enrichment_max_records
        )

    async def _enrich_detail_pages(
        self,
        client: httpx.AsyncClient,
        records: list[ProductSourceRecord],
    ) -> list[ProductSourceRecord]:
        semaphore = asyncio.Semaphore(self._settings.detail_concurrency)

        async def enrich(record: ProductSourceRecord) -> ProductSourceRecord:
            if not record.source_url:
                return record
            async with semaphore:
                try:
                    response = await client.get(record.source_url)
                except httpx.HTTPError:
                    return record
                if response.status_code != 200:
                    return record
                detail = parse_detail_page(
                    response.text,
                    base_url=self._base_url,
                    source_url=record.source_url,
                )
                return record.model_copy(
                    update={
                        "source_brand_name": record.source_brand_name or detail.source_brand_name,
                        "product_name_ko": record.product_name_ko or detail.product_name_ko,
                        "regular_price": record.regular_price or detail.regular_price,
                        "shade": record.shade or detail.shade,
                        "image_url": record.image_url or detail.image_url,
                    }
                )

        return await asyncio.gather(*(enrich(record) for record in records))

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._settings.request_user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
