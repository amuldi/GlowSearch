from __future__ import annotations

import re

from app.models.product import ProductSearchResult, ProductSourceRecord
from app.normalizer.product import ProductNormalizer
from app.normalizer.text import clean_text


class NormalizationAgent:
    """Normalize raw source records and dedupe products without inventing fields."""

    def __init__(self, normalizer: ProductNormalizer):
        self._normalizer = normalizer

    def normalize(self, records: list[ProductSourceRecord]) -> list[ProductSearchResult]:
        return [self._normalizer.normalize(record) for record in records]

    def normalize_complete_deduped(
        self,
        records: list[ProductSourceRecord],
    ) -> list[ProductSearchResult]:
        return [
            product
            for product in self.dedupe(self.normalize(records))
            if product.brand_en and product.product_name_ko
        ]

    @classmethod
    def dedupe(cls, products: list[ProductSearchResult]) -> list[ProductSearchResult]:
        deduped: list[ProductSearchResult] = []
        seen: set[str] = set()
        for product in products:
            brand_key = cls._key(product.brand_en)
            name_key = cls._key(product.product_name_ko)
            if not brand_key or not name_key:
                deduped.append(product)
                continue
            key = f"{brand_key}:{name_key}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(product)
        return deduped

    @staticmethod
    def _key(value: str | None) -> str:
        text = clean_text(value)
        if text is None:
            return ""
        return re.sub(r"[\s\-_./|+&'():\[\],]+", "", text).casefold()
