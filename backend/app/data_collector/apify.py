from __future__ import annotations

import httpx

from app.core.config import Settings
from app.data_collector.base import SourceUnavailableError
from app.models.product import ProductSourceRecord
from app.normalizer.text import clean_text, parse_krw_price


class ApifyOliveYoungCollector:
    name = "oliveyoung:apify"

    def __init__(self, settings: Settings):
        if not settings.apify_token:
            raise ValueError("APIFY token is required")
        self._settings = settings
        self._actor_id = settings.apify_actor_id.replace("/", "~")

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        url = f"https://api.apify.com/v2/acts/{self._actor_id}/run-sync-get-dataset-items"
        params = {"token": self._settings.apify_token}
        payload = {"query": keyword, "maxItems": limit}

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(url, params=params, json=payload)
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"Apify Olive Young request failed: {exc}") from exc

        if response.status_code >= 400:
            raise SourceUnavailableError(f"Apify Olive Young returned HTTP {response.status_code}")

        items = response.json()
        if not isinstance(items, list):
            raise SourceUnavailableError("Apify Olive Young returned an unexpected payload")
        return [record for item in items[:limit] if (record := self._record_from_item(item))]

    def _record_from_item(self, item: object) -> ProductSourceRecord | None:
        if not isinstance(item, dict):
            return None

        brand = _first_value(item, "brand", "brandName", "brand_name")
        name = _first_value(item, "productName", "product_name", "name", "title")
        image = _first_value(item, "imageUrl", "image_url", "image", "thumbnail")
        price = parse_krw_price(_first_value(item, "price", "officialPrice", "regularPrice"))
        shade = _first_value(item, "shade", "color", "option", "optionName")
        source_url = _first_value(item, "url", "sourceUrl", "source_url", "productUrl")
        product_id = _first_value(item, "goodsNo", "productId", "id")

        if not any([brand, name, image, price, shade, source_url, product_id]):
            return None

        return ProductSourceRecord(
            source_brand_name=clean_text(brand),
            product_name_ko=clean_text(name),
            regular_price=price,
            shade=clean_text(shade),
            image_url=clean_text(image),
            source=self.name,
            source_url=clean_text(source_url),
            source_product_id=clean_text(product_id),
        )


def _first_value(item: dict, *keys: str) -> object | None:
    for key in keys:
        value = item.get(key)
        if value not in ("", None):
            return value
    return None
