import re

from app.models.product import PriceValue, ProductOffer, ProductSearchResult, ProductSourceRecord
from app.normalizer.brand import BrandAlias, BrandMatch, BrandResolver
from app.normalizer.text import clean_text, has_hangul, has_latin, normalize_image_url


_SOURCE_BRAND_NOISE = {
    "(NEW",
    "NEW",
    "뿌리는",
}

# 한글 제품명에서 영문 제품 타입을 추출하기 위한 사전 (길이 내림차순으로 정렬해야 앞부분이 먼저 매칭됨)
_KO_TERM_EN: tuple[tuple[str, str], ...] = (
    # 스킨케어
    ("슬리핑팩", "Sleeping Pack"),
    ("수분크림", "Moisturizer"),
    ("젤크림", "Gel Cream"),
    ("아이크림", "Eye Cream"),
    ("클렌징오일", "Cleansing Oil"),
    ("클렌징밤", "Cleansing Balm"),
    ("클렌징밀크", "Cleansing Milk"),
    ("클렌징워터", "Micellar Water"),
    ("폼클렌저", "Foam Cleanser"),
    ("클렌징폼", "Cleansing Foam"),
    ("클렌저", "Cleanser"),
    ("클렌징", "Cleansing"),
    ("마스크팩", "Sheet Mask"),
    ("시트마스크", "Sheet Mask"),
    ("필링젤", "Peeling Gel"),
    ("나이트크림", "Night Cream"),
    ("에센스", "Essence"),
    ("앰플", "Ampoule"),
    ("세럼", "Serum"),
    ("토너", "Toner"),
    ("스킨", "Toner"),
    ("미스트", "Mist"),
    ("크림", "Cream"),
    ("로션", "Lotion"),
    ("오일", "Oil"),
    ("스크럽", "Scrub"),
    # 선케어
    ("자외선차단제", "Sunscreen"),
    ("선쿠션", "Sun Cushion"),
    ("선세럼", "Sun Serum"),
    ("선스틱", "Sun Stick"),
    ("선스크린", "Sunscreen"),
    ("선크림", "Sunscreen"),
    # 베이스 메이크업
    ("비비크림", "BB Cream"),
    ("씨씨크림", "CC Cream"),
    ("파운데이션", "Foundation"),
    ("쿠션", "Cushion Foundation"),
    ("프라이머", "Primer"),
    ("컨실러", "Concealer"),
    ("컨씰러", "Concealer"),
    ("세팅파우더", "Setting Powder"),
    ("루스파우더", "Loose Powder"),
    ("파우더", "Powder"),
    # 치크/하이라이터
    ("하이라이터", "Highlighter"),
    ("블러셔", "Blush"),
    ("블러시", "Blush"),
    ("볼터치", "Blush"),
    ("치크", "Blush"),
    ("섀딩", "Contour"),
    # 아이 메이크업
    ("아이섀도우", "Eyeshadow"),
    ("아이섀도", "Eyeshadow"),
    ("아이라이너", "Eyeliner"),
    ("마스카라", "Mascara"),
    ("브로우마스카라", "Brow Mascara"),
    ("브로우펜슬", "Brow Pencil"),
    ("아이브로우", "Eyebrow"),
    ("눈썹", "Eyebrow"),
    # 립 메이크업
    ("립글로스", "Lip Gloss"),
    ("립틴트", "Lip Tint"),
    ("립스틱", "Lipstick"),
    ("립밤", "Lip Balm"),
    ("립라이너", "Lip Liner"),
    # 바디
    ("바디로션", "Body Lotion"),
    ("바디크림", "Body Cream"),
    ("바디워시", "Body Wash"),
    ("바디오일", "Body Oil"),
)


class ProductNormalizer:
    def __init__(self, brand_resolver: BrandResolver, base_url: str):
        self._brand_resolver = brand_resolver
        self._base_url = base_url

    def normalize(self, record: ProductSourceRecord) -> ProductSearchResult:
        brand_ko = self._brand_ko(record)
        brand_en = self._brand_en(record)
        product_name_ko = clean_text(record.product_name_ko)
        product_name_en = self._product_name_en(record)
        brand_aliases = self._display_brand_aliases(brand_ko, brand_en, record)
        product_name_display_ko = clean_text(record.product_name_display_ko) or _display_product_name(
            product_name_ko,
            brand_aliases,
            variant_values=[record.shade],
        )
        _auto_en = _auto_translate_ko_product_name(product_name_display_ko)
        product_name_display_en = (
            clean_text(record.product_name_display_en)
            or _display_product_name(product_name_en, brand_aliases, variant_values=[record.shade])
            # 한글이 전혀 없는 결과만 설정 (혼합 결과는 제외 → 병합 시 공식 영문명 우선)
            or (_auto_en if _auto_en and not has_hangul(_auto_en) else None)
        )
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
            product_name_display_ko=product_name_display_ko,
            product_name_display_en=product_name_display_en,
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
            search_keywords=_clean_options(record.search_keywords),
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
        if source_brand and has_hangul(source_brand) and not _is_source_brand_noise(source_brand):
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

    def _display_brand_aliases(
        self,
        brand_ko: str | None,
        brand_en: str | None,
        record: ProductSourceRecord,
    ) -> list[str]:
        aliases = [
            brand_ko,
            brand_en,
            record.source_brand_name,
            record.source_brand_name_en,
        ]
        return _dedupe_alias_texts(
            [
                *_compact_korean_aliases(aliases),
                *aliases,
                *self._brand_resolver.aliases_for(brand_en),
            ]
        )

    def _offers(
        self,
        record: ProductSourceRecord,
        *,
        display_price: PriceValue | None,
        original_price: PriceValue | None,
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
        price: PriceValue | None,
        image_url: str | None,
        rating: float | None,
        review_count: int | None,
        source: str | None,
        source_url: str | None,
        source_product_id: str | None,
    ) -> int:
        score = 0
        if product_name_ko or product_name_en:
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
        price: PriceValue | None,
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


def _display_product_name(
    name: str | None,
    brand_aliases: list[str],
    *,
    variant_values: list[str | None] | None = None,
) -> str | None:
    text = clean_text(name)
    if not text:
        return None

    variants = _dedupe_texts(variant_values or [])
    previous = None
    while previous != text:
        previous = text
        text = _strip_leading_bracket_tags(text)
        text = _strip_leading_parenthetical_tags(text)
        text = _strip_leading_retail_prefix(text)
        text = _strip_leading_noise_before_brand(text, brand_aliases)
        text = _strip_leading_brand(text, brand_aliases)
        text = _strip_leading_option_count(text)
        text = _strip_leading_delimiters(text)
        text = _normalize_option_count_phrase(text)
        text = _strip_packaging_parentheses(text)
        text = _strip_packaging_brackets(text)
        text = _strip_packaging_suffix(text)
        text = _strip_size_and_variant_suffix(text)
        text = _strip_known_variant_suffix(text, variants)
        text = clean_text(text) or ""

    text = _normalize_residual_grouping_punctuation(text)
    text = _strip_flattened_packaging_suffix(text)
    text = _strip_size_and_variant_suffix(text)
    return clean_text(text) or clean_text(name)


def _strip_leading_bracket_tags(text: str) -> str:
    current = text
    while True:
        stripped = re.sub(r"^\s*[\[\【][^\]\】]+[\]\】]\s*", "", current)
        if stripped == current:
            return current
        current = stripped


def _strip_leading_parenthetical_tags(text: str) -> str:
    return re.sub(r"^\s*[\(\（][^\)\）]+[\)\）]\s*", "", text)


def _strip_leading_retail_prefix(text: str) -> str:
    return re.sub(
        r"^\s*(?:NEW\s*컬러|신규\s*컬러|올영\s*단독|OY\s*단독|신상|NEW)\s+",
        "",
        text,
        count=1,
        flags=re.IGNORECASE,
    )


def _strip_leading_brand(text: str, brand_aliases: list[str]) -> str:
    current = text
    for alias in sorted(brand_aliases, key=len, reverse=True):
        alias_text = clean_text(alias)
        if not alias_text:
            continue
        pattern = rf"^\s*{_brand_alias_pattern(alias_text)}(?:\s*\|\s*|\s+|$)"
        current = re.sub(pattern, "", current, count=1, flags=re.IGNORECASE)
        current = _strip_leading_delimiters(current)
    return current


def _strip_leading_noise_before_brand(text: str, brand_aliases: list[str]) -> str:
    current = text
    for alias in sorted(brand_aliases, key=len, reverse=True):
        alias_text = clean_text(alias)
        if not alias_text:
            continue
        pattern = rf"^\s*(?P<prefix>[^()\[\]{{}}]{{1,24}}?)\s+{_brand_alias_pattern(alias_text)}(?:\s*\|\s*|\s+|$)"
        match = re.search(pattern, current, flags=re.IGNORECASE)
        if not match:
            continue
        prefix = clean_text(match.group("prefix")) or ""
        if not _is_leading_brand_noise(prefix):
            continue
        current = re.sub(pattern, "", current, count=1, flags=re.IGNORECASE)
        current = _strip_leading_delimiters(current)
    return current


def _strip_leading_delimiters(text: str) -> str:
    return re.sub(r"^\s*[\|/·ㆍ:：,\-]+\s*", "", text)


def _brand_alias_pattern(alias: str) -> str:
    if has_hangul(alias) and " " not in alias:
        return r"\s*".join(re.escape(char) for char in alias)
    return re.escape(alias)


def _strip_leading_option_count(text: str) -> str:
    stripped = re.sub(r"^\s*\d+\s*종\s+", "", text)
    return stripped if len(_key(stripped)) >= 4 else text


def _normalize_option_count_phrase(text: str) -> str:
    current = re.sub(r"\s+\d+\s*종\s+키트$", " 키트", text)
    current = re.sub(r"\s+\d+\s*종\s+피부\s*고민별\s*골라담기$", "", current)
    current = re.sub(r"\s+\d+\s*종\s+골라담기$", "", current)
    return current


def _strip_packaging_parentheses(text: str) -> str:
    current = re.sub(
        r"\s*[\(\（][^\)\）]*(?:기획|단품|더블|세트|증정|택\s*1|컬러|colors?|선택|\+|리필|본품|대용량|한정|/)[^\)\）]*[\)\）]",
        "",
        text,
        flags=re.IGNORECASE,
    )
    current = re.sub(
        r"\s*[\(\（]\s*\d+(?:\.\d+)?\s*(?:g|ml|mL|ML|ea|EA|매|개|개입)\s*(?:[*xX]\s*\d+\s*(?:ea|EA|매|개|개입)?)?\s*[\)\）]",
        "",
        current,
        flags=re.IGNORECASE,
    )
    current = re.sub(
        r"\s*[\(\（][^()\[\]{}]*\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s*[xX]\s*\d+[^()\[\]{}]*[\)\）]",
        "",
        current,
        flags=re.IGNORECASE,
    )
    current = re.sub(
        r"\s*[\(\（][^()\[\]{}]*(?:OY\s*단독|노워시|클렌징\s*밀크|애교살|섀도우|브로우펜슬|브로우마스카라|속눈썹\s*영양제|무향|라벤더향|첫단계\s*진정\s*앰플|컵팩|^\s*온\s*$|호\s*,|26AD|AD|NEW|립밤$)[^()\[\]{}]*[\)\）]\s*$",
        "",
        current,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s*[\(\（]\s*온\s*[\)\）]\s*$", "", current)


def _strip_packaging_brackets(text: str) -> str:
    return re.sub(
        r"\s*[\[\【][^\]\】]*(?:기획|단품|한정|증정|리필|본품|\+|/)[^\]\】]*[\]\】](?:_?올영픽)?",
        "",
        text,
        flags=re.IGNORECASE,
    )


def _strip_packaging_suffix(text: str) -> str:
    current = text
    suffix_patterns = [
        r"\s+\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s+\d+\s*(?:colors?|컬러)\s+SPF\s*\d+.*$",
        r"\s+\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s*(?:SPF\s*\d+\+?(?:\s*/\s*PA\+{1,4}|\s+PA\+{1,4})?|PA\+{1,4}).*$",
        r"\s*SPF\s*\d+\+?\s*,?(?:\s*/\s*PA\+{1,4}|\s+PA\+{1,4}|\s*,\s*PA\+{1,4})?(?:\s+\S.*)?$",
        r"\s*(?:SPF\s*\d+\+?(?:\s*/\s*PA\+{1,4}|\s+PA\+{1,4})?|PA\+{1,4})\s*$",
        r"\s+\d+\s*매\s+\d+\s*종$",
        r"\s+\d+\s*병\s+\d+\s*일분$",
        r"\s+\d+\s*(?:colors?|컬러|종)(?:\s*(?:택\s*1|단품|기획|세트|본품\s*\+\s*리필|본품|리필).*)?\s*\*?$",
        r"(?<=[가-힣A-Za-z])\d+\s*(?:colors?|컬러|종)$",
        r"\s+\d+\s*(?:colors?|컬러)\s+한정(?:\s*기획)?$",
        r"\s+\d+\s*\+\s*\d+\s*기획$",
        r"\s+\d+\s*종\s*1택$",
        r"\s+\d+(?:\.\d+)?\s*(?:g|ml|mL|ML|매|개)\s+\d+\s*\+\s*\d+\s*(?:교차\s*선택|기획|한정\s*기획|한정기획|단독\s*기획|단독기획).*$",
        r"\s+\d+(?:\.\d+)?\s*(?:g|ml|mL|ML|매|개)\s+(?:대용량\s*)?(?:더블\s*기획|더블기획|기획\s*세트|기획세트|단독\s*기획|단독기획)(?:\s+.*)?$",
        r"\s+본품\s*\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s*\+\s*리필\s*\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)$",
        r"\s+\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s*본품\s*\+\s*리필(?:\s+.*)?$",
        r"\s+\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s*\+\s*(?:브러쉬|브러시|퍼프|리필|본품|미니|샘플|증정).*$",
        r"\s+\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s*\+\s*[A-Za-z가-힣0-9\s]+$",
        r"\s+\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s*\+\s*[A-Za-z가-힣0-9-]+$",
        r"\s+\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s*(?:[xX]\s*)?\d+\s*입$",
        r"\s+\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s*[*xX]\s*\d+\s*(?:ea|EA|입)?$",
        r"\s+\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s*\*[A-Za-z가-힣0-9\s*]+$",
        r"(?<=[가-힣A-Za-z])\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s*[*xX]\s*\d+\s*(?:ea|EA|입)?$",
        r"\s+\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s*[xX]\s*\d+\s*$",
        r"\s+\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s*/\s*\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)$",
        r"\s+\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s*\+\s*\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s+[A-Za-z가-힣0-9\s]+$",
        r"\s+\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s+증량$",
        r"\s*\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s*기획$",
        r"\s*\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)(?:\s*\+\s*\d+(?:\.\d+)?\s*(?:g|ml|mL|ML))+$",
        r"\s*\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s*\+\s*$",
        r"\s*\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s*\+\s*\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s*(?:증량|대용량|증정)?$",
        r"\s+\d+(?:\.\d+)?\s*(?:g|ml|mL|ML|매)\s+\d+\s*입$",
        r"\s+\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s+\d+\s*개입\s*(?:한정|단독|기획|/)+.*$",
        r"\s*\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s*\+\s*[A-Za-z가-힣0-9]+\s*증정기획$",
        r"\s*\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s*\+\s*[A-Za-z가-힣0-9]+\s*증정\s*기획(?:_?올영(?:단독)?한정)?$",
        r"\s*\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)(?:\s*\+\s*\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)?)?\s*(?:듀오\s*기획|듀오기획|한정\s*기획|한정기획)$",
        r"\s+\d+(?:\.\d+)?\s*(?:g|ml|mL|매|개)\s+(?:리필\s*기획|리필기획|더블\s*기획|더블기획|기획)(?:\s+\d+\s*종)?$",
        r"\s+(?:중\s*)?택\s*1.*$",
        r"\s+(?:단품|더블|기획|기획팩|기획세트|단독기획|세트|본품|리필|리필기획|증정기획|더블기획|더블기획세트|한정기획|특별한정기획|듀오기획)(?:[/\s].*)?$",
        r"(?<=[가-힣A-Za-z])기획(?:\s*\+\s*\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)?)?$",
        r"\s+블랙/브라운\s*(?:단품|기획).*$",
        r"\s+기획/단품$",
        # 영문 수량/세트 표기
        r"\s+\d+\s*pcs?(?:\s+.*)?$",
        r"\s+\d+\s*pieces?(?:\s+.*)?$",
        r"\s+\d+\s*items?$",
        r"\s+\d+\s*set(?:s)?$",
        r"\s+\d+\s*pack(?:s)?$",
        r"\s*\[\s*\d+\s*pcs?\s*\].*$",
        r"\s*\(\s*\d+\s*pcs?\s*\).*$",
        # 개수 표기 (앞에 공백 없어도 붙는 경우)
        r"(?<=[가-힣A-Za-z])\s*\d+\s*pcs?$",
    ]
    for pattern in suffix_patterns:
        current = re.sub(pattern, "", current, flags=re.IGNORECASE)
    return current


def _normalize_residual_grouping_punctuation(text: str) -> str:
    current = re.sub(r"\s*[\(\（]\s*([^()\[\]{}]+?)\s*[\)\）]\s*", r" \1 ", text)
    current = re.sub(r"\s*[\[\【]\s*([^\[\]\(\){}]+?)\s*[\]\】]\s*", r" \1 ", current)
    return clean_text(current) or text


def _strip_flattened_packaging_suffix(text: str) -> str:
    current = text
    suffix_patterns = [
        r"\s+\d+\s*colors?\s+SPF\s*\d+.*$",
        r"\s+\d+\s*매\s+\d+\s*종(?:\s+.*)?$",
        r"\s+\d+\s*종(?:\s+.*)?$",
        r"\s+\d+\s*병\s+\d+\s*일분$",
        r"\s+\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s*\+\s*\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s+[A-Za-z가-힣0-9\s]+$",
        r"\s+(?:단독기획|더블기획|기획)\s+.*$",
    ]
    for pattern in suffix_patterns:
        current = re.sub(pattern, "", current, flags=re.IGNORECASE)
    return current


def _strip_size_and_variant_suffix(text: str) -> str:
    current = text
    suffix_patterns = [
        r"\s+\d+(?:\.\d+)?\s*(?:g|ml|매|개)\s+\d+\s*(?:colors?|컬러|종)$",
        r"\s*\d+(?:\.\d+)?\s*(?:g|ml|매|개)\s+[A-Za-z가-힣]+/[A-Za-z가-힣]+$",
        r"\s+\d+(?:\.\d+)?\s*(?:g|ml|매|개)$",
        r"(?<=[가-힣A-Za-z])\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)$",
    ]
    for pattern in suffix_patterns:
        current = re.sub(pattern, "", current, flags=re.IGNORECASE)
    return current


def _strip_known_variant_suffix(text: str, variant_values: list[str]) -> str:
    current = text
    for variant in sorted(variant_values, key=len, reverse=True):
        if len(variant) < 2:
            continue
        stripped = re.sub(
            rf"(?:\s+|[\s/#\-_·ㆍ:：,\(\[]+){re.escape(variant)}[\)\]]?\s*$",
            "",
            current,
            count=1,
            flags=re.IGNORECASE,
        )
        if stripped != current and len(_key(stripped)) >= 4:
            current = stripped
    return current


def _auto_translate_ko_product_name(name: str | None) -> str | None:
    """
    한글 제품명에서 알려진 제품 타입 용어를 영문으로 치환해 부분 영문명을 반환.
    긴 용어를 먼저 매칭해 오인식 방지 (예: "크림" 전에 "선크림" 매칭).
    """
    text = clean_text(name)
    if not text or not has_hangul(text):
        return None
    translated = text
    for ko_term, en_term in sorted(_KO_TERM_EN, key=lambda x: len(x[0]), reverse=True):
        if ko_term in translated:
            translated = translated.replace(ko_term, en_term)
            break  # 가장 긴 매칭 하나만 치환
    if translated == text:
        return None
    return clean_text(translated)


def _key(value: str | None) -> str:
    text = clean_text(value)
    if text is None:
        return ""
    return re.sub(r"[\s\-_./&|#·ㆍ:：,\(\)\[\]]+", "", text).casefold()


def _is_source_brand_noise(value: str | None) -> bool:
    text = clean_text(value)
    if not text:
        return False
    if text.casefold() in {item.casefold() for item in _SOURCE_BRAND_NOISE}:
        return True
    return bool(re.search(r"[\[\]【】]", text) or text.startswith("*"))


def _is_leading_brand_noise(value: str | None) -> bool:
    text = clean_text(value)
    if not text:
        return False
    return bool(re.search(r"(?:^|\s)(?:NEW|뿌리는|바르는|올영\s*단독|단독|기획)(?:\s|$)", text, flags=re.IGNORECASE))


def _dedupe_texts(values: list[str | None]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_text(value)
        if not text:
            continue
        key = _key(text)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped


def _dedupe_alias_texts(values: list[str | None]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_text(value)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped


def _compact_korean_aliases(values: list[str | None]) -> list[str]:
    aliases: list[str] = []
    for value in values:
        text = clean_text(value)
        if not text or not has_hangul(text):
            continue
        compact = re.sub(r"\s+", "", text)
        if compact != text and len(_key(compact)) >= 4:
            aliases.append(compact)
    return aliases
