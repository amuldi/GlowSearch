import re

from app.models.product import ProductOffer, ProductSearchResult, ProductSourceRecord
from app.normalizer.brand import BrandAlias, BrandMatch, BrandResolver
from app.normalizer.text import clean_text, has_hangul, has_latin, normalize_image_url


class ProductNormalizer:
    def __init__(self, brand_resolver: BrandResolver, base_url: str):
        self._brand_resolver = brand_resolver
        self._base_url = base_url

    def normalize(self, record: ProductSourceRecord) -> ProductSearchResult:
        brand_ko = self._brand_ko(record)
        brand_en = self._brand_en(record)
        product_name_ko = clean_text(record.product_name_ko)
        product_name_en = self._product_name_en(record)
        original_price = record.original_price or record.regular_price
        sale_price = record.sale_price
        display_price = sale_price if sale_price is not None else original_price
        quality_score = self._quality_score(
            brand_ko=brand_ko,
            brand_en=brand_en,
            product_name_ko=product_name_ko,
            product_name_en=product_name_en,
            price=display_price,
            image_url=record.image_url,
            rating=record.rating,
            review_count=record.review_count,
            source=record.source,
            source_url=record.source_url,
            source_product_id=record.source_product_id,
        )
        enrichment_missing_fields = self._enrichment_missing_fields(
            brand_en=brand_en,
            product_name_en=product_name_en,
            price=display_price,
            image_url=record.image_url,
        )
        return ProductSearchResult(
            canonical_product_id=clean_text(record.canonical_product_id),
            brand_ko=brand_ko,
            brand_en=brand_en,
            product_name_ko=product_name_ko,
            product_name_en=product_name_en,
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
            source_product_id=clean_text(record.source_product_id),
            source=record.source,
            quality_score=quality_score,
            enrichment_missing_fields=enrichment_missing_fields,
            offers=self._offers(record, display_price=display_price, original_price=original_price),
            updated_at=record.updated_at,
        )

    def normalize_brand_filter(self, brand: str) -> str | None:
        return self._brand_resolver.resolve(brand)

    def match_brand_in_text(self, text: str) -> BrandMatch | None:
        return self._brand_resolver.match_text(text)

    def brand_aliases(self, official_en: str | None) -> list[str]:
        return self._brand_resolver.aliases_for(official_en)

    def query_aliases(self, value: str | None, limit: int | None = None) -> list[str]:
        return self._brand_resolver.aliases_for_query(value, limit)

    def index_aliases(self) -> list[BrandAlias]:
        return self._brand_resolver.index_aliases()

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

    def _brand_en(self, record: ProductSourceRecord) -> str | None:
        source_brand_en = clean_text(record.source_brand_name_en)
        if source_brand_en:
            return source_brand_en
        return self._brand_resolver.resolve(
            record.source_brand_name,
            record.product_name_ko,
        )

    @staticmethod
    def _product_name_en(record: ProductSourceRecord) -> str | None:
        source_product_name_en = clean_text(record.product_name_en)
        if source_product_name_en:
            return source_product_name_en
        product_name = clean_text(record.product_name_ko)
        if product_name and has_latin(product_name) and not has_hangul(product_name):
            return product_name
        return None

    def _offers(
        self,
        record: ProductSourceRecord,
        *,
        display_price: int | None,
        original_price: int | None,
    ) -> list[ProductOffer]:
        source_url = normalize_image_url(record.source_url, self._base_url)
        if not source_url:
            return []
        return [
            ProductOffer(
                source=record.source,
                source_url=source_url,
                source_product_id=clean_text(record.source_product_id),
                price=display_price,
                original_price=original_price,
                sale_price=record.sale_price,
                currency=clean_text(record.currency) or "KRW",
                image_url=normalize_image_url(record.image_url, self._base_url),
                sold_out=record.sold_out,
                updated_at=record.updated_at,
            )
        ]

    @staticmethod
    def _quality_score(
        *,
        brand_ko: str | None,
        brand_en: str | None,
        product_name_ko: str | None,
        product_name_en: str | None,
        price: int | None,
        image_url: str | None,
        rating: float | None,
        review_count: int | None,
        source: str | None,
        source_url: str | None,
        source_product_id: str | None,
    ) -> int:
        score = 0
        if product_name_ko:
            score += 30
        if source:
            score += 20
        if source_url or source_product_id:
            score += 20
        if brand_ko:
            score += 10
        if brand_en:
            score += 8
        if product_name_en:
            score += 8
        if price is not None:
            score += 5
        if image_url:
            score += 5
        if rating is not None or review_count is not None:
            score += 4
        return score

    @staticmethod
    def _enrichment_missing_fields(
        *,
        brand_en: str | None,
        product_name_en: str | None,
        price: int | None,
        image_url: str | None,
    ) -> list[str]:
        missing: list[str] = []
        if not brand_en:
            missing.append("brand_en")
        if not product_name_en:
            missing.append("product_name_en")
        if price is None:
            missing.append("price")
        if not image_url:
            missing.append("image_url")
        return missing

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
