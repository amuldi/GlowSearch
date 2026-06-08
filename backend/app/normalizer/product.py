import re

from app.models.product import ProductSearchResult, ProductSourceRecord
from app.normalizer.brand import BrandMatch, BrandResolver
from app.normalizer.text import clean_text, has_hangul, normalize_image_url


class ProductNormalizer:
    def __init__(self, brand_resolver: BrandResolver, base_url: str):
        self._brand_resolver = brand_resolver
        self._base_url = base_url

    def normalize(self, record: ProductSourceRecord) -> ProductSearchResult:
        brand_ko = self._brand_ko(record)
        original_price = record.original_price or record.regular_price
        sale_price = record.sale_price
        display_price = sale_price if sale_price is not None else original_price
        return ProductSearchResult(
            brand_ko=brand_ko,
            brand_en=self._brand_resolver.resolve(
                record.source_brand_name,
                record.product_name_ko,
            ),
            product_name_ko=clean_text(record.product_name_ko),
            category=clean_text(record.category),
            price=display_price,
            original_price=original_price,
            sale_price=sale_price,
            discount_rate=record.discount_rate,
            rating=record.rating,
            review_count=record.review_count,
            currency=clean_text(record.currency) or "KRW",
            shade=clean_text(record.shade),
            image_url=normalize_image_url(record.image_url, self._base_url),
            description=clean_text(record.description),
            options=_clean_options(record.options),
            sold_out=record.sold_out,
            source_url=normalize_image_url(record.source_url, self._base_url),
            source=record.source,
            updated_at=record.updated_at,
        )

    def normalize_brand_filter(self, brand: str) -> str | None:
        return self._brand_resolver.resolve(brand)

    def match_brand_in_text(self, text: str) -> BrandMatch | None:
        return self._brand_resolver.match_text(text)

    def brand_aliases(self, official_en: str | None) -> list[str]:
        return self._brand_resolver.aliases_for(official_en)

    def suggestion_aliases(self) -> list[str]:
        return self._brand_resolver.suggestion_aliases()

    def close(self) -> None:
        self._brand_resolver.close()

    def _brand_ko(self, record: ProductSourceRecord) -> str | None:
        source_brand = clean_text(record.source_brand_name)
        product_brand_match = self._brand_resolver.match_text(record.product_name_ko)
        if source_brand and has_hangul(source_brand):
            if (
                product_brand_match
                and has_hangul(product_brand_match.matched_alias)
                and self._should_use_matched_brand_alias(
                    source_brand,
                    product_brand_match.matched_alias,
                )
            ):
                return product_brand_match.matched_alias
            return source_brand
        if product_brand_match and has_hangul(product_brand_match.matched_alias):
            return product_brand_match.matched_alias
        return None

    @classmethod
    def _should_use_matched_brand_alias(cls, source_brand: str, matched_alias: str) -> bool:
        source_key = cls._brand_key(source_brand)
        alias_key = cls._brand_key(matched_alias)
        if not source_key or not alias_key:
            return False
        if source_key == alias_key:
            return clean_text(source_brand) != clean_text(matched_alias)
        return source_key in alias_key

    @staticmethod
    def _brand_key(value: str | None) -> str:
        text = clean_text(value)
        if text is None:
            return ""
        return re.sub(r"[\s\-_./]+", "", text).casefold()


def _clean_options(options: list[str] | None) -> list[str] | None:
    cleaned = [text for option in options or [] if (text := clean_text(option))]
    return cleaned or None
