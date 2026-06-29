from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.data_collector.base import SourceUnavailableError
from app.ingestion.safety import is_bot_detection_response
from app.models.product import ProductSourceRecord
from app.normalizer.text import clean_text, parse_krw_price


_BASE_URL = "https://www.musinsa.com"
_SEARCH_PATH = "/api/search/v3/goods"
_PRODUCT_URL_TEMPLATE = "https://www.musinsa.com/app/goods/{goods_no}"
_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.musinsa.com/search/musinsa/integrated",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}


class MusinsaBeautyCollector:
    """Musinsa 뷰티 검색 API 수집기."""

    name = "musinsa"

    def __init__(
        self,
        *,
        base_url: str = _BASE_URL,
        timeout_seconds: float = 6.0,
        page_size: int = 24,
        max_pages: int = 3,
        client: httpx.AsyncClient | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._page_size = min(max(page_size, 1), 48)
        self._max_pages = max(max_pages, 1)
        self._client = client

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        keyword = keyword.strip()
        if not keyword or limit <= 0:
            return []

        records: list[ProductSourceRecord] = []
        async with self._client_context() as client:
            for page in range(1, self._max_pages + 1):
                if len(records) >= limit:
                    break
                page_records = await self._fetch_page(client, keyword, page=page)
                if not page_records:
                    break
                records.extend(page_records)

        return records[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        keyword: str,
        *,
        page: int,
    ) -> list[ProductSourceRecord]:
        try:
            response = await client.get(
                f"{self._base_url}{_SEARCH_PATH}",
                params={
                    "keyword": keyword,
                    "page": page,
                    "pageSize": self._page_size,
                    "sortCode": "",
                    "category": "",
                    "goodsStatus": "",
                },
                headers=_HEADERS,
            )
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"musinsa request failed: {exc}") from exc

        if is_bot_detection_response(
            status_code=response.status_code,
            text=response.text[:4096],
            headers=dict(response.headers),
        ) or response.status_code in {401, 403, 429, 503}:
            raise SourceUnavailableError(f"musinsa returned HTTP {response.status_code}")

        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"musinsa returned HTTP {response.status_code}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise SourceUnavailableError("musinsa returned invalid JSON") from exc

        items = _extract_items(payload)
        return [r for item in items if (r := _record_from_item(item)) is not None]

    def _client_context(self):
        if self._client is not None:
            return _ExistingClientContext(self._client)
        return httpx.AsyncClient(
            timeout=self._timeout_seconds,
            follow_redirects=True,
        )


def _extract_items(payload: object) -> list[object]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("list", "goodsList", "items", "products", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    for key in ("list", "goodsList", "items", "results", "products"):
        value = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(value, list):
            return value
    return []


def _record_from_item(item: object) -> ProductSourceRecord | None:
    if not isinstance(item, dict):
        return None

    goods_no = _str(item.get("goodsNo") or item.get("goodsNumber") or item.get("id"))
    name = clean_text(item.get("goodsName") or item.get("productName") or item.get("name"))
    brand = clean_text(item.get("brandName") or _nested(item, "brand", "brandName"))
    brand_en = clean_text(item.get("brandNameEn") or _nested(item, "brand", "brandNameEn"))
    image_url = clean_text(item.get("imageUrl") or item.get("image") or item.get("thumbnail"))
    category = clean_text(
        item.get("category") or item.get("categoryName") or _nested(item, "category", "categoryName")
    )

    normal_price = parse_krw_price(item.get("normalPrice") or item.get("originalPrice"))
    sale_price = parse_krw_price(item.get("salePrice") or item.get("discountPrice"))
    if sale_price is not None and normal_price is not None and sale_price >= normal_price:
        sale_price = None

    source_url = (
        _PRODUCT_URL_TEMPLATE.format(goods_no=goods_no)
        if goods_no
        else clean_text(item.get("goodsUrl") or item.get("url") or item.get("link"))
    )

    if not any([name, image_url, source_url, normal_price]):
        return None

    return ProductSourceRecord(
        source_brand_name=brand,
        source_brand_name_en=brand_en,
        product_name_ko=name,
        category=category,
        regular_price=sale_price if sale_price is not None else normal_price,
        original_price=normal_price,
        sale_price=sale_price,
        rating=_float(item.get("rating") or item.get("avgRating")),
        review_count=_int(item.get("reviewCount") or item.get("reviewCnt")),
        currency="KRW",
        image_url=image_url,
        source="musinsa",
        source_url=source_url,
        source_product_id=goods_no,
        sold_out=_parse_sold_out(item),
    )


def _nested(item: dict[str, Any], *keys: str) -> object | None:
    obj: object = item
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _str(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value) if str(value) else None


def _int(value: object | None) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        digits = "".join(c for c in value if c.isdigit())
        return int(digits) if digits else None
    return None


def _float(value: object | None) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _parse_sold_out(item: dict[str, Any]) -> bool | None:
    v = item.get("isSoldOut") or item.get("soldOut") or item.get("outOfStock")
    if isinstance(v, bool):
        return v
    in_stock = item.get("isOnSale") or item.get("inStock") or item.get("available")
    if isinstance(in_stock, bool):
        return not in_stock
    return None


class _ExistingClientContext:
    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._client

    async def __aexit__(self, *args: object) -> None:
        return None
