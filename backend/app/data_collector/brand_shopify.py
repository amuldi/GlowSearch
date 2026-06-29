from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from app.data_collector.base import SourceUnavailableError
from app.models.product import ProductSourceRecord
from app.normalizer.brand import BrandRegistry, BrandRegistryEntry
from app.normalizer.text import clean_text, has_hangul, has_latin


_PRODUCTS_JSON_PATH = "/products.json"
_TIMEOUT_SECONDS = 6.0
_PAGE_SIZE = 50
_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}


class BrandShopifyCollector:
    """브랜드 공식 Shopify 스토어에서 상품을 수집합니다.

    brand_registry의 sources 도메인에서 Shopify /products.json API를 사용합니다.
    검색어에 브랜드명이 포함된 경우에만 해당 브랜드 스토어를 조회합니다.
    """

    name = "official"

    def __init__(
        self,
        registry_path: Path,
        *,
        timeout_seconds: float = _TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ):
        self._entries = _load_brand_entries(registry_path)
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        keyword = keyword.strip()
        if not keyword or limit <= 0:
            return []

        matched = _match_brand_entries(keyword, self._entries)
        if not matched:
            return []

        records: list[ProductSourceRecord] = []
        async with self._client_context() as client:
            for entry in matched:
                if len(records) >= limit:
                    break
                for source_url in entry.sources:
                    if len(records) >= limit:
                        break
                    domain = _extract_domain(source_url)
                    if not domain:
                        continue
                    try:
                        page_records = await self._fetch_products(
                            client, domain, entry, keyword, limit - len(records)
                        )
                        records.extend(page_records)
                    except SourceUnavailableError:
                        continue

        return records[:limit]

    async def _fetch_products(
        self,
        client: httpx.AsyncClient,
        domain: str,
        entry: BrandRegistryEntry,
        keyword: str,
        limit: int,
    ) -> list[ProductSourceRecord]:
        try:
            response = await client.get(
                f"https://{domain}{_PRODUCTS_JSON_PATH}",
                params={"limit": min(limit, _PAGE_SIZE)},
                headers=_HEADERS,
            )
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"official:{domain} request failed: {exc}") from exc

        if response.status_code in {401, 403, 404, 429, 503}:
            raise SourceUnavailableError(f"official:{domain} returned HTTP {response.status_code}")

        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"official:{domain} returned HTTP {response.status_code}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise SourceUnavailableError(f"official:{domain} returned invalid JSON") from exc

        products = payload.get("products") if isinstance(payload, dict) else None
        if not isinstance(products, list):
            raise SourceUnavailableError(f"official:{domain} response missing products list")

        keyword_lower = keyword.lower()
        records: list[ProductSourceRecord] = []
        for item in products:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).lower()
            vendor = str(item.get("vendor", "")).lower()
            if keyword_lower not in title and keyword_lower not in vendor:
                continue
            record = _record_from_shopify_item(item, domain, entry)
            if record is not None:
                records.append(record)

        return records

    def _client_context(self):
        if self._client is not None:
            return _ExistingClientContext(self._client)
        return httpx.AsyncClient(timeout=self._timeout_seconds, follow_redirects=True)


def _record_from_shopify_item(
    item: dict[str, Any],
    domain: str,
    entry: BrandRegistryEntry,
) -> ProductSourceRecord | None:
    product_id = str(item.get("id", ""))
    title = clean_text(item.get("title"))
    handle = clean_text(item.get("handle"))
    product_type = clean_text(item.get("product_type"))
    images: list[dict[str, Any]] = item.get("images") or []
    variants: list[dict[str, Any]] = item.get("variants") or []

    image_url = clean_text(images[0].get("src")) if images else None
    source_url = (
        f"https://{domain}/products/{handle}" if handle else f"https://{domain}"
    )

    price: float | None = None
    sale_price: float | None = None
    options: list[str] = []

    for variant in variants[:10]:
        variant_price = _parse_price(variant.get("price"))
        compare_at = _parse_price(variant.get("compare_at_price"))
        if variant_price is not None and price is None:
            price = variant_price
        if compare_at is not None and variant_price is not None and compare_at > variant_price:
            if sale_price is None:
                sale_price = variant_price
                price = compare_at
        option_title = clean_text(variant.get("title"))
        if option_title and option_title.lower() not in {"default title", "기본", "단품"}:
            options.append(option_title)

    if not any([title, image_url, source_url, price]):
        return None

    return ProductSourceRecord(
        source_brand_name=entry.official_en,
        source_brand_name_en=entry.official_en,
        product_name_ko=title if (title and has_hangul(title)) else None,
        product_name_en=title if (title and has_latin(title) and not has_hangul(title)) else None,
        category=product_type,
        regular_price=int(price) if price is not None else None,
        original_price=int(price) if price is not None else None,
        sale_price=int(sale_price) if sale_price is not None else None,
        currency="KRW",
        options=options or None,
        image_url=image_url,
        source="official",
        source_url=source_url,
        source_product_id=product_id or None,
    )


def _load_brand_entries(registry_path: Path) -> list[BrandRegistryEntry]:
    if not registry_path.exists():
        return []
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        registry = BrandRegistry.model_validate(data)
        return [e for e in registry.entries if e.sources]
    except Exception:
        return []


def _match_brand_entries(keyword: str, entries: list[BrandRegistryEntry]) -> list[BrandRegistryEntry]:
    keyword_lower = keyword.lower()
    matched: list[BrandRegistryEntry] = []
    for entry in entries:
        for alias in [entry.official_en, *entry.aliases]:
            if alias and alias.lower() in keyword_lower:
                matched.append(entry)
                break
    return matched


def _extract_domain(source_url: str) -> str | None:
    url = source_url.strip()
    if url.startswith("https://"):
        url = url[8:]
    elif url.startswith("http://"):
        url = url[7:]
    domain = url.split("/")[0]
    return domain if "." in domain else None


def _parse_price(value: object) -> float | None:
    if value is None:
        return None
    try:
        price = float(str(value).replace(",", ""))
        return price if price > 0 else None
    except (TypeError, ValueError):
        return None


class _ExistingClientContext:
    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._client

    async def __aexit__(self, *args: object) -> None:
        return None
