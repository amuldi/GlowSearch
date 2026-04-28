from __future__ import annotations

import json
import re
from collections.abc import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.models.product import ProductSourceRecord
from app.normalizer.text import clean_text, normalize_image_url, parse_krw_display_price, parse_krw_price


CARD_SELECTORS = (
    "li.xans-record-",
    "li[class*='item']",
    "li[class*='prd']",
    "li[class*='product']",
    "div[class*='product']",
    "div[class*='goods']",
    "div[class*='item']",
)
NAME_SELECTORS = (
    "[class*='name']",
    "[class*='Name']",
    "[class*='title']",
    "[class*='Title']",
    ".description a",
    "a[title]",
)
PRICE_SELECTORS = (
    "[class*='price']",
    "[class*='Price']",
    ".prd_price",
    ".sale",
    ".money",
    "li[rel*='판매가']",
)
OPTION_SELECTORS = (
    "select option",
    "[class*='option'] li",
    "[class*='option'] button",
    "[class*='color'] li",
)


def parse_generic_product_results(
    html: str,
    *,
    base_url: str,
    source_brand_name: str,
    limit: int,
) -> list[ProductSourceRecord]:
    soup = BeautifulSoup(html, "html.parser")
    records = _parse_structured_products(
        soup,
        base_url=base_url,
        source_brand_name=source_brand_name,
    )
    if records:
        return _dedupe(records)[:limit]

    candidates: list[Tag] = []
    for selector in CARD_SELECTORS:
        candidates.extend(tag for tag in soup.select(selector) if isinstance(tag, Tag))

    records = []
    for node in candidates:
        record = _parse_product_card(
            node,
            base_url=base_url,
            source_brand_name=source_brand_name,
        )
        if record:
            records.append(record)
    return _dedupe(records)[:limit]


def _parse_structured_products(
    soup: BeautifulSoup,
    *,
    base_url: str,
    source_brand_name: str,
) -> list[ProductSourceRecord]:
    records: list[ProductSourceRecord] = []
    for script in soup.select("script[type='application/ld+json']"):
        text = script.string or script.get_text()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        for item in _walk_json(payload):
            record = _record_from_mapping(
                item,
                base_url=base_url,
                source_brand_name=source_brand_name,
            )
            if record:
                records.append(record)
    return records


def _record_from_mapping(
    item: dict,
    *,
    base_url: str,
    source_brand_name: str,
) -> ProductSourceRecord | None:
    if str(item.get("@type", "")).casefold() not in {"product", ""}:
        return None

    name = _clean_product_name(item.get("name"))
    offers = item.get("offers") if isinstance(item.get("offers"), dict) else {}
    price = (
        parse_krw_price(item.get("price"))
        or parse_krw_price(offers.get("price"))
        or parse_krw_display_price(offers.get("lowPrice"))
    )
    image = item.get("image")
    if isinstance(image, list):
        image = next((value for value in image if isinstance(value, str)), None)
    source_url = item.get("url")
    if not isinstance(source_url, str):
        source_url = None
    source_url = urljoin(base_url, source_url) if source_url else None
    product_id = clean_text(item.get("sku") or item.get("mpn") or item.get("productID"))
    shade = clean_text(item.get("color") or item.get("size"))

    if not name:
        return None

    return ProductSourceRecord(
        source_brand_name=source_brand_name,
        product_name_ko=name,
        regular_price=price,
        shade=shade,
        image_url=normalize_image_url(clean_text(image), base_url),
        source="official",
        source_url=source_url,
        source_product_id=product_id or source_url,
    )


def _parse_product_card(
    node: Tag,
    *,
    base_url: str,
    source_brand_name: str,
) -> ProductSourceRecord | None:
    name = _card_name(node)
    source_url = _card_url(node, base_url)
    price = _card_price(node)
    image = _card_image(node, base_url)
    shade = _card_shade(node)

    if not name or not any([source_url, price, image]):
        return None

    return ProductSourceRecord(
        source_brand_name=source_brand_name,
        product_name_ko=name,
        regular_price=price,
        shade=shade,
        image_url=image,
        source="official",
        source_url=source_url,
        source_product_id=source_url,
    )


def _card_name(node: Tag) -> str | None:
    for selector in NAME_SELECTORS:
        found = node.select_one(selector)
        if not found:
            continue
        text = _clean_product_name(found.get("title") or found.get_text(" ", strip=True))
        if text and not _is_noise(text):
            return text
    return None


def _card_url(node: Tag, base_url: str) -> str | None:
    for anchor in node.select("a[href]"):
        href = clean_text(anchor.get("href"))
        if not href or href.startswith("#") or "javascript:" in href.casefold():
            continue
        if any(token in href.casefold() for token in ("product", "goods", "item")):
            return urljoin(base_url, href)
    return None


def _card_price(node: Tag) -> int | None:
    for selector in PRICE_SELECTORS:
        found = node.select_one(selector)
        if not found:
            continue
        text = found.get_text(" ", strip=True)
        price = parse_krw_price(text) or parse_krw_display_price(text)
        if price is not None:
            return price
    return None


def _card_image(node: Tag, base_url: str) -> str | None:
    for image in node.select("img"):
        src = (
            image.get("src")
            or image.get("data-src")
            or image.get("data-original")
            or image.get("ec-data-src")
        )
        normalized = normalize_image_url(clean_text(src), base_url)
        if normalized:
            return normalized
    return None


def _card_shade(node: Tag) -> str | None:
    shades: list[str] = []
    for selector in OPTION_SELECTORS:
        for option in node.select(selector):
            text = clean_text(option.get_text(" ", strip=True))
            if text and not _is_noise(text):
                shades.append(text)
    if not shades:
        return None
    return ", ".join(dict.fromkeys(shades).keys())


def _walk_json(value: object) -> Iterator[dict]:
    if isinstance(value, dict):
        if "name" in value and ("offers" in value or str(value.get("@type", "")).casefold() == "product"):
            yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _is_noise(text: str) -> bool:
    exact_noise = {
        "품절",
        "sold out",
        "soldout",
        "more",
        "view",
    }
    contains_noise = (
        "장바구니",
        "관심상품",
        "옵션",
        "선택",
    )
    normalized = text.casefold()
    return normalized in exact_noise or any(item in normalized for item in contains_noise)


def _clean_product_name(value: object | None) -> str | None:
    text = clean_text(value)
    if text is None:
        return None
    text = re.sub(r"^\s*(?:상품명|제품명)\s*[:：]\s*", "", text)
    return clean_text(text)


def _dedupe(records: list[ProductSourceRecord]) -> list[ProductSourceRecord]:
    deduped: list[ProductSourceRecord] = []
    seen: set[str] = set()
    for record in records:
        name_key = re.sub(r"[\s\-_./|+&'():\[\],]+", "", record.product_name_ko or "").casefold()
        key = f"{record.source_brand_name}:{name_key}" if name_key else record.source_url
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped
