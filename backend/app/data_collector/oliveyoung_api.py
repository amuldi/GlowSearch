from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.config import Settings
from app.data_collector.base import SourceUnavailableError
from app.ingestion.safety import (
    AsyncRateLimiter,
    RetryConfig,
    SleepFunc,
    backoff_delay_seconds,
    is_bot_detection_response,
)
from app.models.product import ProductSourceRecord
from app.normalizer.text import clean_text, parse_krw_price


class OliveYoungPublicApiCollector:
    name = "oliveyoung:public-api"

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        *,
        sleep: SleepFunc = asyncio.sleep,
        rate_limiter: AsyncRateLimiter | None = None,
    ):
        self._settings = settings
        self._base_url = settings.oliveyoung_public_api_base_url.rstrip("/")
        self._client = client
        self._sleep = sleep
        self._retry_config = RetryConfig(
            attempts=max(settings.oliveyoung_public_api_retry_attempts, 1),
            base_delay_seconds=settings.oliveyoung_public_api_retry_base_delay_seconds,
            max_delay_seconds=settings.oliveyoung_public_api_retry_max_delay_seconds,
        )
        self._rate_limiter = rate_limiter or AsyncRateLimiter(
            requests_per_second=settings.oliveyoung_public_api_rate_limit_per_second,
            sleep=sleep,
        )

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        keyword = keyword.strip()
        if not keyword or limit <= 0:
            return []

        records: list[ProductSourceRecord] = []
        page = 1
        page_size = min(
            max(limit, 1),
            max(self._settings.oliveyoung_search_page_size, 1),
            48,
        )
        max_pages = max(1, self._settings.oliveyoung_search_max_pages)
        async with self._client_context() as client:
            while len(records) < limit and page <= max_pages:
                payload = await self._fetch_page(client, keyword, page=page, size=page_size)
                data = payload.get("data", {}) if isinstance(payload, dict) else {}
                products = data.get("products", []) if isinstance(data, dict) else []
                if not isinstance(products, list) or not products:
                    break
                records.extend(
                    record
                    for item in products
                    if (record := self._record_from_item(item)) is not None
                )
                if not data.get("nextPage"):
                    break
                page += 1
        return records[:limit]

    def _client_context(self):
        if self._client is not None:
            return _ExistingClientContext(self._client)
        return httpx.AsyncClient(
            timeout=self._settings.oliveyoung_public_api_timeout_seconds,
            follow_redirects=True,
        )

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        keyword: str,
        *,
        page: int,
        size: int,
    ) -> dict[str, Any]:
        params = {"keyword": keyword, "size": size, "page": page}
        last_error: SourceUnavailableError | None = None
        for attempt_index in range(self._retry_config.attempts):
            await self._rate_limiter.wait()
            try:
                response = await client.get(
                    f"{self._base_url}/api/oliveyoung/products",
                    params=params,
                )
            except httpx.HTTPError as exc:
                last_error = SourceUnavailableError(
                    f"Olive Young public API request failed: {exc}"
                )
                if attempt_index + 1 >= self._retry_config.attempts:
                    raise last_error from exc
                await self._sleep(backoff_delay_seconds(attempt_index, self._retry_config))
                continue

            if is_bot_detection_response(
                status_code=response.status_code,
                text=response.text[:4096],
                headers=dict(response.headers),
            ):
                last_error = SourceUnavailableError(
                    f"Olive Young public API returned HTTP {response.status_code}"
                )
                if attempt_index + 1 >= self._retry_config.attempts:
                    raise last_error
                await self._sleep(backoff_delay_seconds(attempt_index, self._retry_config))
                continue
            try:
                response.raise_for_status()
            except httpx.HTTPError as exc:
                last_error = SourceUnavailableError(
                    f"Olive Young public API returned HTTP {response.status_code}"
                )
                if attempt_index + 1 >= self._retry_config.attempts:
                    raise last_error from exc
                await self._sleep(backoff_delay_seconds(attempt_index, self._retry_config))
                continue
            try:
                payload = response.json()
            except ValueError as exc:
                raise SourceUnavailableError(
                    "Olive Young public API returned invalid JSON"
                ) from exc
            return payload if isinstance(payload, dict) else {}
        raise last_error or SourceUnavailableError("Olive Young public API request failed")

    def _record_from_item(self, item: object) -> ProductSourceRecord | None:
        if not isinstance(item, dict):
            return None

        goods_no = clean_text(item.get("goodsNumber") or item.get("goodsNo"))
        name = clean_text(item.get("goodsName") or item.get("productName"))
        image_url = clean_text(item.get("imageUrl"))
        category = clean_text(
            _first_value(
                item,
                "category",
                "categoryName",
                "categoryFullName",
                "displayCategory",
                "dispCatNm",
            )
        )
        original_price = parse_krw_price(item.get("originalPrice"))
        discount_rate = _parse_int(item.get("discountRate"))
        price_to_pay = parse_krw_price(item.get("priceToPay"))
        has_discount = (
            discount_rate is not None
            and discount_rate > 0
            and original_price is not None
            and price_to_pay is not None
            and price_to_pay < original_price
        )
        sale_price = price_to_pay if has_discount else None
        if not any([goods_no, name, image_url, original_price, price_to_pay]):
            return None

        source_url = (
            f"{self._settings.oliveyoung_base_url.rstrip('/')}"
            f"/store/goods/getGoodsDetail.do?goodsNo={goods_no}"
            if goods_no
            else None
        )
        return ProductSourceRecord(
            source_brand_name=_infer_brand_from_name(name),
            product_name_ko=name,
            category=category,
            regular_price=sale_price if sale_price is not None else price_to_pay or original_price,
            original_price=original_price,
            sale_price=sale_price,
            discount_rate=discount_rate if has_discount else None,
            rating=_parse_float(_first_value(item, "rating", "avgRating", "reviewScore")),
            review_count=_parse_int(
                _first_value(item, "reviewCount", "reviewsCount", "reviewCnt")
            ),
            currency="KRW",
            description=clean_text(
                _first_value(item, "description", "summary", "goodsDescription", "goodsDesc")
            ),
            options=_parse_options(
                _first_value(item, "options", "optionNames", "variants", "items")
            ),
            sold_out=_parse_sold_out(item),
            image_url=image_url,
            source="oliveyoung",
            source_url=source_url,
            source_product_id=goods_no,
            updated_at=clean_text(_first_value(item, "updatedAt", "updated_at", "lastUpdatedAt")),
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


def _parse_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized = value.replace(",", ".").strip()
        try:
            return float(normalized)
        except ValueError:
            return None
    return None


def _parse_options(value: Any) -> list[str] | None:
    if isinstance(value, str):
        option = clean_text(value)
        return [option] if option else None
    if not isinstance(value, list):
        return None
    options: list[str] = []
    for item in value:
        if isinstance(item, str):
            option = clean_text(item)
        elif isinstance(item, dict):
            option = clean_text(
                _first_value(item, "name", "optionName", "option_name", "title", "color")
            )
        else:
            option = None
        if option and option not in options:
            options.append(option)
    return options or None


def _parse_sold_out(item: dict[str, Any]) -> bool | None:
    in_stock = item.get("inStock")
    if isinstance(in_stock, bool):
        return not in_stock
    status = clean_text(item.get("stockStatus") or item.get("availability"))
    if status:
        status_key = status.casefold()
        if any(token in status_key for token in ("sold_out", "out_of_stock", "품절")):
            return True
        if any(token in status_key for token in ("in_stock", "available", "판매중")):
            return False
    return None


def _first_value(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in ("", None):
            return value
    return None


class _ExistingClientContext:
    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._client

    async def __aexit__(self, *args: object) -> None:
        return None


def _infer_brand_from_name(name: str | None) -> str | None:
    text = clean_text(name)
    if not text:
        return None
    text = _strip_leading_badges(text)
    token = text.split(maxsplit=1)[0] if text else ""
    return token or None


def _strip_leading_badges(text: str) -> str:
    stripped = text.strip()
    while stripped.startswith("["):
        end_index = stripped.find("]")
        if end_index < 0:
            break
        stripped = stripped[end_index + 1 :].strip()
    return stripped
