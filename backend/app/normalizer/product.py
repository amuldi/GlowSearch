from app.models.product import ProductSearchResult, ProductSourceRecord
from app.normalizer.brand import BrandMatch, BrandResolver
from app.normalizer.text import clean_text, normalize_image_url


class ProductNormalizer:
    def __init__(self, brand_resolver: BrandResolver, base_url: str):
        self._brand_resolver = brand_resolver
        self._base_url = base_url

    def normalize(self, record: ProductSourceRecord) -> ProductSearchResult:
        return ProductSearchResult(
            brand_en=self._brand_resolver.resolve(
                record.source_brand_name,
                record.product_name_ko,
            ),
            product_name_ko=clean_text(record.product_name_ko),
            price=record.regular_price,
            shade=clean_text(record.shade),
            image_url=normalize_image_url(record.image_url, self._base_url),
            source_url=normalize_image_url(record.source_url, self._base_url),
            source=record.source,
        )

    def normalize_brand_filter(self, brand: str) -> str | None:
        return self._brand_resolver.resolve(brand)

    def match_brand_in_text(self, text: str) -> BrandMatch | None:
        return self._brand_resolver.match_text(text)

    def close(self) -> None:
        self._brand_resolver.close()
