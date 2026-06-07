from __future__ import annotations

from typing import Any

import httpx

from app.data_collector.base import SourceUnavailableError
from app.models.product import ProductSourceRecord
from app.normalizer.text import clean_text
from app.source_adapters.base import SourceAdapterCapabilities, SourceAdapterMetadata


class OpenBeautyFactsCollector:
    name = "openbeautyfacts"

    def __init__(
        self,
        *,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ):
        self._timeout_seconds = timeout_seconds
        self._client = client
        self.metadata = SourceAdapterMetadata(
            name=self.name,
            priority=30,
            timeout_seconds=timeout_seconds,
            critical_path=True,
            capabilities=SourceAdapterCapabilities(product_search=True, barcode_lookup=True),
        )

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        barcode = _barcode(keyword)
        if not barcode or limit <= 0:
            return []
        try:
            if self._client is not None:
                response = await self._client.get(
                    f"https://world.openbeautyfacts.org/api/v2/product/{barcode}.json"
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.get(
                        f"https://world.openbeautyfacts.org/api/v2/product/{barcode}.json"
                    )
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"Open Beauty Facts request failed: {exc}") from exc
        if response.status_code in {403, 429}:
            raise SourceUnavailableError(f"Open Beauty Facts returned HTTP {response.status_code}")
        if response.status_code == 404:
            return []
        response.raise_for_status()
        payload = response.json()
        product = payload.get("product") if isinstance(payload, dict) else None
        if not isinstance(product, dict):
            return []
        record = self._record_from_product(product, barcode)
        return [record] if record else []

    def _record_from_product(self, product: dict[str, Any], barcode: str) -> ProductSourceRecord | None:
        name = clean_text(
            product.get("product_name")
            or product.get("product_name_en")
            or product.get("generic_name")
        )
        brand = clean_text(product.get("brands"))
        if not name and not brand:
            return None
        return ProductSourceRecord(
            source_brand_name=brand,
            product_name_ko=name,
            regular_price=None,
            currency=None,
            image_url=clean_text(product.get("image_front_url") or product.get("image_url")),
            source=self.name,
            source_url=f"https://world.openbeautyfacts.org/product/{barcode}",
            source_product_id=barcode,
        )


class BarcodeLookupCollector:
    name = "barcodelookup"

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ):
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._client = client
        self.metadata = SourceAdapterMetadata(
            name=self.name,
            priority=45,
            timeout_seconds=timeout_seconds,
            critical_path=False,
            capabilities=SourceAdapterCapabilities(product_search=True, barcode_lookup=True),
        )

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        params = {"key": self._api_key}
        barcode = _barcode(keyword)
        if barcode:
            params["barcode"] = barcode
        else:
            params["search"] = keyword
            params["category"] = "Health & Beauty"
        try:
            if self._client is not None:
                response = await self._client.get(
                    "https://api.barcodelookup.com/v3/products",
                    params=params,
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.get(
                        "https://api.barcodelookup.com/v3/products",
                        params=params,
                    )
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"Barcode Lookup request failed: {exc}") from exc
        if response.status_code in {401, 403, 429}:
            raise SourceUnavailableError(f"Barcode Lookup returned HTTP {response.status_code}")
        response.raise_for_status()
        payload = response.json()
        products = payload.get("products", []) if isinstance(payload, dict) else []
        if not isinstance(products, list):
            return []
        return [record for item in products[:limit] if (record := self._record_from_item(item))]

    def _record_from_item(self, item: object) -> ProductSourceRecord | None:
        if not isinstance(item, dict):
            return None
        name = clean_text(item.get("title"))
        brand = clean_text(item.get("brand") or item.get("manufacturer"))
        if not name and not brand:
            return None
        images = item.get("images")
        image_url = clean_text(images[0]) if isinstance(images, list) and images else None
        return ProductSourceRecord(
            source_brand_name=brand,
            product_name_ko=name,
            regular_price=None,
            currency=None,
            image_url=image_url,
            source=self.name,
            source_url=clean_text(item.get("details_page_url")),
            source_product_id=clean_text(item.get("barcode_number")),
        )


class UPCItemDBCollector:
    name = "upcitemdb"

    def __init__(
        self,
        *,
        timeout_seconds: float,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        self._timeout_seconds = timeout_seconds
        self._api_key = api_key
        self._client = client
        self._base_url = (
            "https://api.upcitemdb.com/prod/v1"
            if api_key
            else "https://api.upcitemdb.com/prod/trial"
        )
        self.metadata = SourceAdapterMetadata(
            name=self.name,
            priority=50,
            timeout_seconds=timeout_seconds,
            critical_path=False,
            capabilities=SourceAdapterCapabilities(product_search=True, barcode_lookup=True),
        )

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        barcode = _barcode(keyword)
        endpoint = "lookup" if barcode else "search"
        params = {"upc": barcode} if barcode else {"s": keyword, "match_mode": "0"}
        headers = {"user_key": self._api_key, "key_type": "3scale"} if self._api_key else {}
        try:
            if self._client is not None:
                response = await self._client.get(
                    f"{self._base_url}/{endpoint}",
                    params=params,
                    headers=headers,
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.get(
                        f"{self._base_url}/{endpoint}",
                        params=params,
                        headers=headers,
                    )
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"UPCitemDB request failed: {exc}") from exc
        if response.status_code in {401, 403, 429}:
            raise SourceUnavailableError(f"UPCitemDB returned HTTP {response.status_code}")
        response.raise_for_status()
        payload = response.json()
        items = payload.get("items", []) if isinstance(payload, dict) else []
        if not isinstance(items, list):
            return []
        return [record for item in items[:limit] if (record := self._record_from_item(item))]

    def _record_from_item(self, item: object) -> ProductSourceRecord | None:
        if not isinstance(item, dict):
            return None
        name = clean_text(item.get("title"))
        brand = clean_text(item.get("brand"))
        if not name and not brand:
            return None
        images = item.get("images")
        image_url = clean_text(images[0]) if isinstance(images, list) and images else None
        return ProductSourceRecord(
            source_brand_name=brand,
            product_name_ko=name,
            regular_price=None,
            currency=None,
            image_url=image_url,
            source=self.name,
            source_url=clean_text(item.get("detail_page_url")),
            source_product_id=clean_text(item.get("ean") or item.get("upc")),
        )


def _barcode(keyword: str) -> str | None:
    value = "".join(char for char in keyword if char.isdigit())
    if len(value) in {7, 8, 10, 11, 12, 13, 14}:
        return value
    return None
