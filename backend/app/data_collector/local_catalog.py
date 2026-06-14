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

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        keyword_key = self._key(keyword)
        if not keyword_key or not self._catalog_path.exists():
            return []

        payload = json.loads(self._catalog_path.read_text(encoding="utf-8"))
        records: list[ProductSourceRecord] = []
        for item in payload.get("products", []):
            haystack = self._key(
                " ".join(
                    str(value)
                    for value in [
                        item.get("brand_ko"),
                        item.get("brand_en"),
                        item.get("product_name_ko"),
                        item.get("product_name_en"),
                        item.get("category"),
                        item.get("description"),
                        " ".join(item.get("options", [])),
                        " ".join(item.get("keywords", [])),
                    ]
                    if value
                )
            )
            keyword_tokens = self._tokens(keyword)
            if keyword_key not in haystack and not all(token in haystack for token in keyword_tokens):
                continue
            records.append(
                ProductSourceRecord(
                    canonical_product_id=clean_text(
                        item.get("canonical_product_id") or item.get("canonical_id")
                    ),
                    source_brand_name=clean_text(item.get("brand_ko") or item.get("brand_en")),
                    source_brand_name_en=clean_text(item.get("brand_en")),
                    product_name_ko=clean_text(item.get("product_name_ko")),
                    product_name_en=clean_text(item.get("product_name_en")),
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
                    sold_out=item.get("sold_out"),
                    image_url=clean_text(item.get("image_url")),
                    source=clean_text(item.get("source")) or "oliveyoung",
                    source_url=clean_text(item.get("source_url")),
                    source_product_id=clean_text(item.get("goods_no")),
                    updated_at=clean_text(item.get("updated_at")),
                )
            )
            if len(records) >= limit:
                break
        return records

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
