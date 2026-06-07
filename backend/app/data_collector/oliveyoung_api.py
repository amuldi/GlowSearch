from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings
from app.data_collector.base import SourceUnavailableError
from app.models.product import ProductSourceRecord
from app.normalizer.text import clean_text, parse_krw_price


class OliveYoungPublicApiCollector:
    name = "oliveyoung:public-api"

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self._settings = settings
        self._base_url = settings.oliveyoung_public_api_base_url.rstrip("/")
        self._client = client

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        keyword = keyword.strip()
        if not keyword or limit <= 0:
            return []

        params = {"keyword": keyword, "size": min(max(limit, 1), 48)}
        try:
            if self._client is not None:
                response = await self._client.get(
                    f"{self._base_url}/api/oliveyoung/products",
                    params=params,
                )
            else:
                async with httpx.AsyncClient(
                    timeout=self._settings.oliveyoung_public_api_timeout_seconds,
                    follow_redirects=True,
                ) as client:
                    response = await client.get(
                        f"{self._base_url}/api/oliveyoung/products",
                        params=params,
                    )
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"Olive Young public API request failed: {exc}") from exc

        if response.status_code in {403, 429, 503}:
            raise SourceUnavailableError(
                f"Olive Young public API returned HTTP {response.status_code}"
            )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise SourceUnavailableError("Olive Young public API returned invalid JSON") from exc

        products = payload.get("data", {}).get("products", []) if isinstance(payload, dict) else []
        if not isinstance(products, list):
            return []
        return [record for item in products[:limit] if (record := self._record_from_item(item))]

    def _record_from_item(self, item: object) -> ProductSourceRecord | None:
        if not isinstance(item, dict):
            return None

        goods_no = clean_text(item.get("goodsNumber") or item.get("goodsNo"))
        name = clean_text(item.get("goodsName") or item.get("productName"))
        image_url = clean_text(item.get("imageUrl"))
        original_price = parse_krw_price(item.get("originalPrice"))
        sale_price = parse_krw_price(item.get("priceToPay"))
        discount_rate = _parse_int(item.get("discountRate"))
        if not any([goods_no, name, image_url, original_price, sale_price]):
            return None

        source_url = (
            f"{self._settings.oliveyoung_base_url.rstrip('/')}"
            f"/store/goods/getGoodsDetail.do?goodsNo={goods_no}"
            if goods_no
            else None
        )
        return ProductSourceRecord(
            source_brand_name=None,
            product_name_ko=name,
            regular_price=sale_price if sale_price is not None else original_price,
            original_price=original_price,
            sale_price=sale_price,
            discount_rate=discount_rate,
            currency="KRW",
            image_url=image_url,
            source="oliveyoung",
            source_url=source_url,
            source_product_id=goods_no,
        )


def _parse_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        digits = "".join(char for char in value if char.isdigit())
        return int(digits) if digits else None
    return None
