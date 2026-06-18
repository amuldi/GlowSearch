from __future__ import annotations

import json
import re
from pathlib import Path

from app.models.product import ProductSourceRecord
from app.normalizer.text import clean_text
from app.search.synonyms import search_key


class LocalVerifiedCatalogCollector:
    name = "oliveyoung:verified-cache"

    def __init__(self, catalog_path: Path):
        self._catalog_path = catalog_path

    async def all_records(self, limit: int | None = None) -> list[ProductSourceRecord]:
        products = self._products()
        records: list[ProductSourceRecord] = []
        seen: set[str] = set()
        for item in products:
            record = _record_from_item(item)
            key = _record_key(record)
            if key in seen:
                continue
            seen.add(key)
            records.append(record)
            if limit is not None and limit > 0 and len(records) >= limit:
                break
        return records

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        keyword_key = self._key(keyword)
        if not keyword_key or not self._catalog_path.exists():
            return []

        products = self._products()
        canonical_groups = _canonical_groups(products)
        records: list[ProductSourceRecord] = []
        seen: set[str] = set()
        for item in products:
            haystack = self._item_haystack_key(item)
            keyword_tokens = self._tokens(keyword)
            if keyword_key not in haystack and not all(token in haystack for token in keyword_tokens):
                continue
            for grouped_item in self._expand_canonical_group(item, canonical_groups):
                record = _record_from_item(grouped_item)
                key = _record_key(record)
                if key in seen:
                    continue
                seen.add(key)
                records.append(record)
                if len(records) >= limit:
                    break
            if len(records) >= limit:
                break
        return records

    def _products(self) -> list[object]:
        if not self._catalog_path.exists():
            return []
        payload = json.loads(self._catalog_path.read_text(encoding="utf-8"))
        products = payload.get("products", [])
        if not isinstance(products, list):
            return []
        return products

    def _item_haystack_key(self, item: object) -> str:
        if not isinstance(item, dict):
            return ""
        return self._key(
            " ".join(
                str(value)
                for value in [
                    item.get("brand_ko"),
                    item.get("brand_en"),
                    item.get("product_name_ko"),
                    item.get("product_name_en"),
                    item.get("product_name_display_ko"),
                    item.get("product_name_display_en"),
                    item.get("category"),
                    item.get("description"),
                    _join_texts(item.get("options")),
                    _join_texts(item.get("keywords")),
                ]
                if value
            )
        )

    @staticmethod
    def _expand_canonical_group(
        item: object,
        canonical_groups: dict[str, list[object]],
    ) -> list[object]:
        if not isinstance(item, dict):
            return [item]
        canonical_id = clean_text(item.get("canonical_product_id") or item.get("canonical_id"))
        if not canonical_id:
            return [item]
        return canonical_groups.get(canonical_id, [item])

    @staticmethod
    def _key(value: str | None) -> str:
        text = search_key(value)
        return (
            text.replace("glowy", "글로이")
            .replace("tear", "티어")
            .replace("비타민씨", "비타")
            .replace("여백살롱", "여백카롱")
            .replace("및서재", "밑서재")
            .replace("플로팅", "플러팅")
            .replace("이즈핏", "이지핏")
            .replace("땡큐요엠핑크", "요염핑")
        )

    @classmethod
    def _tokens(cls, value: str | None) -> list[str]:
        text = clean_text(value)
        if text is None:
            return []
        return [cls._key(token) for token in re.findall(r"[0-9A-Za-z가-힣]+", text) if cls._key(token)]


def _clean_options(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    options = [text for item in value if (text := clean_text(item))]
    return options or None


def _join_texts(value: object) -> str:
    if not isinstance(value, list):
        return ""
    return " ".join(text for item in value if (text := clean_text(item)))


def _canonical_groups(products: object) -> dict[str, list[object]]:
    groups: dict[str, list[object]] = {}
    if not isinstance(products, list):
        return groups
    for item in products:
        if not isinstance(item, dict):
            continue
        canonical_id = clean_text(item.get("canonical_product_id") or item.get("canonical_id"))
        if not canonical_id:
            continue
        groups.setdefault(canonical_id, []).append(item)
    return groups


def _record_from_item(item: object) -> ProductSourceRecord:
    if not isinstance(item, dict):
        return ProductSourceRecord(source="oliveyoung")
    return ProductSourceRecord(
        canonical_product_id=clean_text(item.get("canonical_product_id") or item.get("canonical_id")),
        source_brand_name=clean_text(item.get("brand_ko") or item.get("brand_en")),
        source_brand_name_en=clean_text(item.get("brand_en")),
        product_name_ko=clean_text(item.get("product_name_ko")),
        product_name_en=clean_text(item.get("product_name_en")),
        product_name_display_ko=clean_text(item.get("product_name_display_ko")),
        product_name_display_en=clean_text(item.get("product_name_display_en")),
        category=clean_text(item.get("category")),
        regular_price=item.get("price"),
        original_price=item.get("original_price"),
        sale_price=item.get("sale_price"),
        discount_rate=item.get("discount_rate"),
        rating=item.get("rating"),
        review_count=item.get("review_count"),
        currency=clean_text(item.get("currency")) or "KRW",
        shade=clean_text(item.get("shade")),
        description=clean_text(item.get("description")),
        options=_clean_options(item.get("options")),
        search_keywords=_clean_options(item.get("keywords")),
        sold_out=item.get("sold_out"),
        image_url=clean_text(item.get("image_url")),
        source=clean_text(item.get("source")) or "oliveyoung",
        source_url=clean_text(item.get("source_url")),
        source_product_id=clean_text(item.get("goods_no")),
        updated_at=clean_text(item.get("updated_at")),
    )


def _record_key(record: ProductSourceRecord) -> str:
    if record.source_product_id:
        return f"{record.source}:{record.source_product_id}"
    if record.source_url:
        return f"{record.source}:{record.source_url}"
    return ":".join(
        value
        for value in [
            record.source,
            record.canonical_product_id,
            record.source_brand_name,
            record.product_name_ko,
        ]
        if value
    )
