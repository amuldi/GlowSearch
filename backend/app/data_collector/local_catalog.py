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
            keyword_tokens = self._tokens(keyword)
            if keyword_key not in haystack and not all(token in haystack for token in keyword_tokens):
                continue
            records.append(
                ProductSourceRecord(
                    source_brand_name=clean_text(item.get("brand_ko") or item.get("brand_en")),
                    product_name_ko=clean_text(item.get("product_name_ko")),
                    regular_price=item.get("price"),
                    currency=clean_text(item.get("currency")) or "KRW",
                    shade=clean_text(item.get("shade")),
                    image_url=clean_text(item.get("image_url")),
                    source=clean_text(item.get("source")) or "oliveyoung",
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
        text = text.casefold()
        text = (
            text.replace("브러쉬", "브러시")
            .replace("brush", "브러시")
            .replace("eyeliner", "아이라이너")
            .replace("eye shadow", "아이섀도")
            .replace("glowy", "글로이")
            .replace("tear", "티어")
            .replace("gray", "그레이")
            .replace("grey", "그레이")
            .replace("쉐딩", "섀딩")
            .replace("셰딩", "섀딩")
            .replace("비타민씨", "비타")
            .replace("여백살롱", "여백카롱")
            .replace("및서재", "밑서재")
            .replace("플로팅", "플러팅")
            .replace("이즈핏", "이지핏")
            .replace("땡큐요엠핑크", "요염핑")
        )
        return re.sub(r"[\s\-_./|+&'():\[\],]+", "", text)

    @classmethod
    def _tokens(cls, value: str | None) -> list[str]:
        text = clean_text(value)
        if text is None:
            return []
        return [cls._key(token) for token in re.findall(r"[0-9A-Za-z가-힣]+", text) if cls._key(token)]
