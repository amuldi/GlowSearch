from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

import httpx

from app.data_collector.base import SourceUnavailableError
from app.models.product import ProductSourceRecord
from app.normalizer.text import clean_text
from app.source_adapters.base import (
    DiscoveredSource,
    SourceAdapterCapabilities,
    SourceAdapterMetadata,
)


class SerpApiShoppingCollector:
    name = "serpapi:google-shopping"

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float,
        location: str | None = None,
        gl: str | None = None,
        hl: str | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._location = location
        self._gl = gl
        self._hl = hl
        self._client = client
        self.metadata = SourceAdapterMetadata(
            name=self.name,
            priority=40,
            timeout_seconds=timeout_seconds,
            critical_path=True,
            capabilities=SourceAdapterCapabilities(product_search=True, discovery=True),
        )

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        payload = await self._fetch(keyword, limit)
        items = payload.get("shopping_results", [])
        if not isinstance(items, list):
            return []
        return [record for item in items[:limit] if (record := self._record_from_item(item))]

    async def discover(self, keyword: str, limit: int) -> list[DiscoveredSource]:
        payload = await self._fetch(keyword, limit)
        items = payload.get("shopping_results", [])
        if not isinstance(items, list):
            return []
        return [
            source
            for item in items[:limit]
            if isinstance(item, dict) and (source := self._discovered_source(item))
        ]

    async def _fetch(self, keyword: str, limit: int) -> dict[str, Any]:
        params = {
            "engine": "google_shopping",
            "q": keyword,
            "api_key": self._api_key,
            "num": min(max(limit, 1), 100),
        }
        if self._location:
            params["location"] = self._location
        if self._gl:
            params["gl"] = self._gl
        if self._hl:
            params["hl"] = self._hl

        try:
            if self._client is not None:
                response = await self._client.get("https://serpapi.com/search.json", params=params)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.get("https://serpapi.com/search.json", params=params)
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"SerpAPI request failed: {exc}") from exc

        if response.status_code in {401, 403, 429}:
            raise SourceUnavailableError(f"SerpAPI returned HTTP {response.status_code}")
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise SourceUnavailableError("SerpAPI returned invalid JSON") from exc
        if isinstance(payload, dict) and payload.get("error"):
            raise SourceUnavailableError(f"SerpAPI returned error: {payload['error']}")
        return payload if isinstance(payload, dict) else {}

    def _record_from_item(self, item: object) -> ProductSourceRecord | None:
        if not isinstance(item, dict):
            return None
        title = clean_text(item.get("title"))
        if not title:
            return None
        return ProductSourceRecord(
            source_brand_name=None,
            product_name_ko=title,
            regular_price=_integer_price(item.get("extracted_price")),
            currency=clean_text(item.get("currency")),
            image_url=clean_text(item.get("thumbnail") or item.get("serpapi_thumbnail")),
            source=self.name,
            source_url=clean_text(item.get("product_link") or item.get("link")),
            source_product_id=clean_text(item.get("product_id")),
        )

    def _discovered_source(self, item: dict[str, Any]) -> DiscoveredSource | None:
        url = clean_text(item.get("product_link") or item.get("link"))
        if not url:
            return None
        return DiscoveredSource(
            url=url,
            title=clean_text(item.get("title")),
            source=self.name,
            snippet=clean_text(item.get("snippet") or item.get("source")),
        )


class BingWebSearchCollector:
    name = "bing:web-search"

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float,
        market: str = "en-US",
        endpoint: str = "https://api.bing.microsoft.com/v7.0/search",
        client: httpx.AsyncClient | None = None,
    ):
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._market = market
        self._endpoint = endpoint
        self._client = client
        self.metadata = SourceAdapterMetadata(
            name=self.name,
            priority=70,
            timeout_seconds=timeout_seconds,
            critical_path=False,
            capabilities=SourceAdapterCapabilities(product_search=True, discovery=True),
        )

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        return [
            ProductSourceRecord(
                source_brand_name=None,
                product_name_ko=source.title,
                source=self.name,
                source_url=source.url,
            )
            for source in await self.discover(keyword, limit)
            if source.title
        ]

    async def discover(self, keyword: str, limit: int) -> list[DiscoveredSource]:
        params = {
            "q": f"{keyword} cosmetics product",
            "count": min(max(limit, 1), 50),
            "mkt": self._market,
            "responseFilter": "Webpages",
        }
        headers = {"Ocp-Apim-Subscription-Key": self._api_key}
        try:
            if self._client is not None:
                response = await self._client.get(self._endpoint, params=params, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.get(self._endpoint, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"Bing Web Search request failed: {exc}") from exc
        if response.status_code in {401, 403, 429}:
            raise SourceUnavailableError(f"Bing Web Search returned HTTP {response.status_code}")
        response.raise_for_status()
        payload = response.json()
        values = payload.get("webPages", {}).get("value", []) if isinstance(payload, dict) else []
        if not isinstance(values, list):
            return []
        return [
            DiscoveredSource(
                url=url,
                title=clean_text(item.get("name")),
                source=self.name,
                snippet=clean_text(item.get("snippet")),
            )
            for item in values[:limit]
            if isinstance(item, dict) and (url := clean_text(item.get("url")))
        ]


class GoogleProgrammableSearchCollector:
    name = "google:programmable-search"

    def __init__(
        self,
        *,
        api_key: str,
        search_engine_id: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ):
        self._api_key = api_key
        self._search_engine_id = search_engine_id
        self._timeout_seconds = timeout_seconds
        self._client = client
        self.metadata = SourceAdapterMetadata(
            name=self.name,
            priority=75,
            timeout_seconds=timeout_seconds,
            critical_path=False,
            capabilities=SourceAdapterCapabilities(product_search=True, discovery=True),
        )

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        return [
            ProductSourceRecord(
                source_brand_name=None,
                product_name_ko=source.title,
                source=self.name,
                source_url=source.url,
            )
            for source in await self.discover(keyword, limit)
            if source.title
        ]

    async def discover(self, keyword: str, limit: int) -> list[DiscoveredSource]:
        params = {
            "key": self._api_key,
            "cx": self._search_engine_id,
            "q": f"{keyword} cosmetics product",
            "num": min(max(limit, 1), 10),
        }
        try:
            if self._client is not None:
                response = await self._client.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params=params,
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.get(
                        "https://www.googleapis.com/customsearch/v1",
                        params=params,
                    )
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"Google Programmable Search request failed: {exc}") from exc
        if response.status_code in {401, 403, 429}:
            raise SourceUnavailableError(
                f"Google Programmable Search returned HTTP {response.status_code}"
            )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("items", []) if isinstance(payload, dict) else []
        if not isinstance(items, list):
            return []
        return [
            DiscoveredSource(
                url=url,
                title=clean_text(item.get("title")),
                source=self.name,
                snippet=clean_text(item.get("snippet")),
            )
            for item in items[:limit]
            if isinstance(item, dict) and (url := clean_text(item.get("link")))
        ]


class BrightDataSerpCollector:
    name = "brightdata:serp"

    def __init__(
        self,
        *,
        api_key: str,
        zone: str,
        timeout_seconds: float,
        country: str = "us",
        client: httpx.AsyncClient | None = None,
    ):
        self._api_key = api_key
        self._zone = zone
        self._timeout_seconds = timeout_seconds
        self._country = country
        self._client = client
        self.metadata = SourceAdapterMetadata(
            name=self.name,
            priority=65,
            timeout_seconds=timeout_seconds,
            critical_path=False,
            capabilities=SourceAdapterCapabilities(
                product_search=True,
                discovery=True,
                managed_scraping=True,
            ),
        )

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        return [
            ProductSourceRecord(
                source_brand_name=None,
                product_name_ko=source.title,
                source=self.name,
                source_url=source.url,
            )
            for source in await self.discover(keyword, limit)
            if source.title
        ]

    async def discover(self, keyword: str, limit: int) -> list[DiscoveredSource]:
        payload = {
            "zone": self._zone,
            "url": f"https://www.google.com/search?q={quote_plus(keyword + ' cosmetics product')}",
            "format": "json",
            "method": "GET",
            "country": self._country,
            "data_format": "markdown",
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            if self._client is not None:
                response = await self._client.post(
                    "https://api.brightdata.com/request",
                    json=payload,
                    headers=headers,
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(
                        "https://api.brightdata.com/request",
                        json=payload,
                        headers=headers,
                    )
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"Bright Data SERP request failed: {exc}") from exc
        if response.status_code in {401, 403, 429}:
            raise SourceUnavailableError(f"Bright Data SERP returned HTTP {response.status_code}")
        response.raise_for_status()
        result = response.json()
        organic = result.get("organic", []) if isinstance(result, dict) else []
        if not isinstance(organic, list):
            return []
        return [
            DiscoveredSource(
                url=url,
                title=clean_text(item.get("title")),
                source=self.name,
                snippet=clean_text(item.get("description") or item.get("snippet")),
            )
            for item in organic[:limit]
            if isinstance(item, dict) and (url := clean_text(item.get("link") or item.get("url")))
        ]


def _integer_price(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None
