from __future__ import annotations

import re
from typing import Any

import httpx

from app.core.config import Settings
from app.data_collector.base import SourceUnavailableError
from app.models.product import ProductSourceRecord
from app.normalizer.text import clean_text, parse_krw_price


class MusinsaProductCollector:
    name = "musinsa"

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self._settings = settings
        self._base_url = settings.musinsa_api_base_url.rstrip("/")
        self._client = client

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        keyword = keyword.strip()
        if not keyword:
            return []

        if self._client is not None:
            payload = await self._fetch(self._client, keyword, limit)
        else:
            async with httpx.AsyncClient(
                timeout=self._settings.musinsa_timeout_seconds,
                follow_redirects=True,
                headers={
                    "Accept": "application/json",
                    "User-Agent": self._settings.request_user_agent,
                },
            ) as client:
                payload = await self._fetch(client, keyword, limit)

        items = payload.get("data", {}).get("list", [])
        if not isinstance(items, list):
            return []

        records: list[ProductSourceRecord] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            record = self._record_from_item(item)
            if record:
                records.append(record)
            if len(records) >= limit:
                break
        return records

    async def _fetch(
        self,
        client: httpx.AsyncClient,
        keyword: str,
        limit: int,
    ) -> dict[str, Any]:
        try:
            response = await client.get(
                f"{self._base_url}/v2/plp/goods",
                params={
                    "caller": "SEARCH",
                    "gf": "A",
                    "keyword": keyword,
                    "page": 1,
                    "size": min(max(limit, 1), 48),
                    "sortCode": "POPULAR",
                    "category": self._settings.musinsa_beauty_category_code,
                },
            )
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"Musinsa request failed: {exc}") from exc

        if response.status_code in {403, 429}:
            raise SourceUnavailableError(f"Musinsa blocked the request with HTTP {response.status_code}")
        if response.status_code >= 500:
            raise SourceUnavailableError(f"Musinsa returned temporary HTTP {response.status_code}")
        response.raise_for_status()
        try:
            return response.json()
        except ValueError as exc:
            raise SourceUnavailableError("Musinsa returned invalid JSON") from exc

    def _record_from_item(self, item: dict[str, Any]) -> ProductSourceRecord | None:
        name = clean_text(item.get("goodsName"))
        brand = clean_text(item.get("brandNameEng") or item.get("brandName") or item.get("brand"))
        image = clean_text(item.get("thumbnail"))
        source_url = clean_text(item.get("goodsLinkUrl"))
        goods_no = clean_text(item.get("goodsNo"))
        price = parse_krw_price(item.get("normalPrice")) or parse_krw_price(item.get("price"))

        if not any([name, brand, image, source_url, goods_no, price]):
            return None

        return ProductSourceRecord(
            source_brand_name=brand,
            product_name_ko=name,
            regular_price=price,
            shade=self._extract_shade(name),
            image_url=image,
            source="musinsa",
            source_url=source_url,
            source_product_id=goods_no,
        )

    @staticmethod
    def _extract_shade(name: str | None) -> str | None:
        text = clean_text(name)
        if text is None:
            return None
        match = re.search(r"\(?\b\d+\s*Colors?\b\)?", text, flags=re.IGNORECASE)
        if match:
            return clean_text(match.group(0).strip("()"))
        match = re.search(r"\(?\b\d+\s*컬러\b\)?", text, flags=re.IGNORECASE)
        if match:
            return clean_text(match.group(0).strip("()"))
        return None
