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
        category = _first_value(item, "category", "categoryName", "category_name")
        image = _first_value(item, "imageUrl", "image_url", "image", "thumbnail")
        price = parse_krw_price(_first_value(item, "price", "officialPrice", "regularPrice"))
        original_price = parse_krw_price(_first_value(item, "originalPrice", "original_price"))
        sale_price = parse_krw_price(
            _first_value(item, "discountPrice", "salePrice", "sale_price")
        )
        shade = _first_value(item, "shade", "color", "option", "optionName")
        source_url = _first_value(item, "url", "sourceUrl", "source_url", "productUrl")
        product_id = _first_value(item, "goodsNo", "productId", "id")

        if not any([brand, name, image, price, shade, source_url, product_id]):
            return None

        return ProductSourceRecord(
            source_brand_name=clean_text(brand),
            product_name_ko=clean_text(name),
            category=clean_text(category),
            regular_price=price or sale_price or original_price,
            original_price=original_price,
            sale_price=sale_price,
            discount_rate=_parse_int(_first_value(item, "discountRate", "discount_rate")),
            rating=_parse_float(_first_value(item, "rating", "avgRating", "reviewScore")),
            review_count=_parse_int(_first_value(item, "reviewCount", "review_count")),
            shade=clean_text(shade),
            description=clean_text(_first_value(item, "description", "summary")),
            options=_parse_options(_first_value(item, "options", "optionNames", "variants")),
            sold_out=_parse_sold_out(item),
            image_url=clean_text(image),
            source=self.name,
            source_url=clean_text(source_url),
            source_product_id=clean_text(product_id),
            updated_at=clean_text(_first_value(item, "updatedAt", "updated_at")),
        )


def _first_value(item: dict, *keys: str) -> object | None:
    for key in keys:
        value = item.get(key)
        if value not in ("", None):
            return value
    return None


def _parse_int(value: object | None) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        digits = "".join(char for char in value if char.isdigit())
        return int(digits) if digits else None
    return None


def _parse_float(value: object | None) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", "."))
        except ValueError:
            return None
    return None


def _parse_options(value: object | None) -> list[str] | None:
    if isinstance(value, str):
        option = clean_text(value)
        return [option] if option else None
    if not isinstance(value, list):
        return None
    options: list[str] = []
    for item in value:
        option = clean_text(item) if isinstance(item, str) else None
        if isinstance(item, dict):
            option = clean_text(_first_value(item, "name", "optionName", "title", "color"))
        if option and option not in options:
            options.append(option)
    return options or None


def _parse_sold_out(item: dict) -> bool | None:
    sold_out = _first_value(item, "soldOut", "sold_out", "outOfStock")
    if isinstance(sold_out, bool):
        return sold_out
    in_stock = _first_value(item, "inStock", "in_stock", "available")
    if isinstance(in_stock, bool):
        return not in_stock
    status = clean_text(_first_value(item, "stockStatus", "availability", "status"))
    if status:
        status_key = status.casefold()
        if any(token in status_key for token in ("sold_out", "out_of_stock", "품절")):
            return True
        if any(token in status_key for token in ("in_stock", "available", "판매중")):
            return False
    return None
