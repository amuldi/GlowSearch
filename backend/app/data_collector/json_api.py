from __future__ import annotations

from typing import Any

import httpx

from app.data_collector.base import SourceUnavailableError
from app.ingestion.safety import is_bot_detection_response
from app.models.product import ProductSourceRecord
from app.normalizer.text import clean_text, parse_krw_price


class JsonApiProductCollector:
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        timeout_seconds: float,
        query_param: str = "q",
        limit_param: str = "limit",
        barcode_only: bool = False,
        client: httpx.AsyncClient | None = None,
    ):
        self.name = name
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._query_param = query_param
        self._limit_param = limit_param
        self._barcode_only = barcode_only
        self._client = client

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        keyword = keyword.strip()
        if not keyword or limit <= 0 or (self._barcode_only and not _looks_like_barcode(keyword)):
            return []

        try:
            async with self._client_context() as client:
                response = await client.get(
                    self._base_url,
                    params={self._query_param: keyword, self._limit_param: limit},
                )
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"{self.name} request failed: {exc}") from exc

        if is_bot_detection_response(
            status_code=response.status_code,
            text=response.text[:4096],
            headers=dict(response.headers),
        ) or response.status_code in {401, 403, 429, 503}:
            raise SourceUnavailableError(f"{self.name} returned HTTP {response.status_code}")
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"{self.name} returned HTTP {response.status_code}") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise SourceUnavailableError(f"{self.name} returned invalid JSON") from exc

        items = _items_from_payload(payload)
        return [
            record
            for item in items[:limit]
            if (record := self._record_from_item(item)) is not None
        ]

    def _record_from_item(self, item: object) -> ProductSourceRecord | None:
        if not isinstance(item, dict):
            return None
        brand = _first_value(item, "brand_ko", "brandKo", "brand", "brandName", "brand_name")
        name = _first_value(item, "product_name_ko", "productNameKo", "productName", "name", "title")
        category = _first_value(item, "category", "categoryName", "category_name", "categories")
        image = _first_value(item, "image_url", "imageUrl", "image", "thumbnail")
        source_url = _first_value(item, "source_url", "sourceUrl", "url", "productUrl", "link")
        product_id = _first_value(item, "source_product_id", "productId", "goodsNo", "id", "gtin", "barcode")
        price = parse_krw_price(_first_value(item, "price", "regular_price", "regularPrice"))
        original_price = parse_krw_price(_first_value(item, "original_price", "originalPrice"))
        sale_price = parse_krw_price(_first_value(item, "sale_price", "salePrice"))
        discount_rate = _parse_int(_first_value(item, "discount_rate", "discountRate"))
        shade = _first_value(item, "shade", "color", "option", "optionName")
        currency = clean_text(_first_value(item, "currency")) or "KRW"
        options = _parse_options(_first_value(item, "options", "optionNames", "variants"))
        sold_out = _parse_sold_out(item)

        if not any([brand, name, image, source_url, product_id, price, original_price, sale_price]):
            return None
        return ProductSourceRecord(
            source_brand_name=clean_text(brand),
            product_name_ko=clean_text(name),
            category=_clean_category(category),
            regular_price=price or sale_price or original_price,
            original_price=original_price,
            sale_price=sale_price,
            discount_rate=discount_rate,
            rating=_parse_float(_first_value(item, "rating", "avgRating", "reviewScore")),
            review_count=_parse_int(_first_value(item, "review_count", "reviewCount", "reviewsCount")),
            currency=currency,
            shade=clean_text(shade),
            description=clean_text(_first_value(item, "description", "summary", "desc")),
            options=options,
            sold_out=sold_out,
            image_url=clean_text(image),
            source=self.name,
            source_url=clean_text(source_url),
            source_product_id=clean_text(product_id),
            updated_at=clean_text(_first_value(item, "updated_at", "updatedAt", "lastUpdatedAt")),
        )

    def _client_context(self):
        if self._client is not None:
            return _ExistingClientContext(self._client)
        return httpx.AsyncClient(timeout=self._timeout_seconds, follow_redirects=True)


def _items_from_payload(payload: object) -> list[object]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("products", "items", "results", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _items_from_payload(value)
            if nested:
                return nested
    return []


def _first_value(item: dict[str, Any], *keys: str) -> object | None:
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
            option = clean_text(
                _first_value(item, "name", "optionName", "option_name", "title", "color")
            )
        if option and option not in options:
            options.append(option)
    return options or None


def _parse_sold_out(item: dict[str, Any]) -> bool | None:
    value = _first_value(item, "sold_out", "soldOut", "outOfStock")
    if isinstance(value, bool):
        return value
    in_stock = _first_value(item, "in_stock", "inStock", "available")
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


def _clean_category(value: object | None) -> str | None:
    if isinstance(value, list):
        return clean_text(" > ".join(str(item) for item in value if item))
    return clean_text(value)


def _looks_like_barcode(value: str) -> bool:
    digits = "".join(char for char in value if char.isdigit())
    return len(digits) in {8, 12, 13, 14}


class _ExistingClientContext:
    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._client

    async def __aexit__(self, *args: object) -> None:
        return None
