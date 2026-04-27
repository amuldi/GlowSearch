from __future__ import annotations

import json
import re
from pathlib import Path

from app.models.product import ProductSourceRecord
from app.normalizer.text import clean_text


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
                        " ".join(item.get("keywords", [])),
                    ]
                    if value
                )
            )
            if keyword_key not in haystack:
                continue
            records.append(
                ProductSourceRecord(
                    source_brand_name=clean_text(item.get("brand_ko") or item.get("brand_en")),
                    product_name_ko=clean_text(item.get("product_name_ko")),
                    regular_price=item.get("price"),
                    shade=clean_text(item.get("shade")),
                    image_url=clean_text(item.get("image_url")),
                    source="oliveyoung",
                    source_url=clean_text(item.get("source_url")),
                    source_product_id=clean_text(item.get("goods_no")),
                )
            )
            if len(records) >= limit:
                break
        return records

    @staticmethod
    def _key(value: str | None) -> str:
        text = clean_text(value)
        if text is None:
            return ""
        return re.sub(r"[\s\-_./|+&'():\[\],]+", "", text).casefold()
