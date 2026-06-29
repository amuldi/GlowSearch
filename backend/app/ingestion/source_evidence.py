from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from html import unescape
from html.parser import HTMLParser

from app.normalizer.text import clean_text, has_hangul, has_latin


@dataclass(frozen=True)
class ProductNameEvidence:
    source: str
    name: str
    language: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ProductImageEvidence:
    source: str
    url: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ProductPriceEvidence:
    source: str
    price: str
    currency: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


def extract_product_name_evidence(html: str) -> list[ProductNameEvidence]:
    parser = _EvidenceHTMLParser()
    parser.feed(html)
    evidence: list[ProductNameEvidence] = []
    evidence.extend(_json_ld_product_names(parser.json_ld_payloads))
    evidence.extend(_meta_name_evidence(parser.meta_values))
    if parser.title:
        evidence.append(_evidence("title", parser.title))
    return _dedupe_evidence(evidence)


def extract_product_image_evidence(html: str) -> list[ProductImageEvidence]:
    parser = _EvidenceHTMLParser()
    parser.feed(html)
    evidence: list[ProductImageEvidence] = []
    evidence.extend(_json_ld_product_images(parser.json_ld_payloads))
    evidence.extend(_meta_image_evidence(parser.image_values))
    return _dedupe_image_evidence(evidence)


def extract_product_price_evidence(html: str) -> list[ProductPriceEvidence]:
    parser = _EvidenceHTMLParser()
    parser.feed(html)
    evidence: list[ProductPriceEvidence] = []
    evidence.extend(_json_ld_product_prices(parser.json_ld_payloads))
    evidence.extend(_meta_price_evidence(parser.price_values, parser.currency_values))
    return _dedupe_price_evidence(evidence)


def product_name_en_candidate(
    evidence: list[ProductNameEvidence],
    *,
    rejected_names: set[str] | None = None,
) -> ProductNameEvidence | None:
    for item in evidence:
        if item.language == "latin" and not _is_low_confidence_latin_name(
            item.name,
            rejected_names=rejected_names or set(),
        ):
            return item
    return None


def product_name_en_rejection_reason(
    evidence: list[ProductNameEvidence],
    *,
    rejected_names: set[str] | None = None,
) -> str:
    if product_name_en_candidate(evidence, rejected_names=rejected_names) is not None:
        return ""
    if not evidence:
        return "no_evidence"
    languages = {item.language for item in evidence if item.language != "unknown"}
    if "latin" in languages:
        return "latin_evidence_rejected_low_confidence"
    if languages == {"mixed"}:
        return "mixed_language_without_latin_product_name"
    if languages == {"ko"}:
        return "korean_only_evidence"
    if languages <= {"ko", "mixed"}:
        return "korean_or_mixed_evidence_only"
    return "no_latin_product_name_evidence"


def classify_name_language(value: str | None) -> str:
    text = clean_text(value)
    if not text:
        return "unknown"
    includes_hangul = has_hangul(text)
    includes_latin = has_latin(text)
    if includes_hangul and includes_latin:
        return "mixed"
    if includes_hangul:
        return "ko"
    if includes_latin:
        return "latin"
    return "unknown"


class _EvidenceHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.json_ld_payloads: list[str] = []
        self.meta_values: list[tuple[str, str]] = []
        self.image_values: list[tuple[str, str]] = []
        self.price_values: list[tuple[str, str]] = []
        self.currency_values: list[tuple[str, str]] = []
        self.title: str | None = None
        self._in_json_ld = False
        self._json_ld_chunks: list[str] = []
        self._in_title = False
        self._title_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {name.lower(): value or "" for name, value in attrs}
        if tag.lower() == "script" and attrs_map.get("type", "").lower() == "application/ld+json":
            self._in_json_ld = True
            self._json_ld_chunks = []
            return
        if tag.lower() == "title":
            self._in_title = True
            self._title_chunks = []
            return
        if tag.lower() != "meta":
            return
        key = (
            attrs_map.get("property")
            or attrs_map.get("name")
            or attrs_map.get("itemprop")
            or ""
        ).casefold()
        content = clean_text(attrs_map.get("content"))
        if not content:
            return
        if key in {"og:title", "twitter:title", "title", "product:name", "name"}:
            self.meta_values.append((key, content))
        if key in {"og:image", "twitter:image", "image", "product:image"}:
            self.image_values.append((key, content))
        if key in {"product:price:amount", "og:price:amount", "price", "product:price"}:
            self.price_values.append((key, content))
        if key in {"product:price:currency", "og:price:currency", "pricecurrency"}:
            self.currency_values.append((key, content))

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._in_json_ld:
            payload = "".join(self._json_ld_chunks).strip()
            if payload:
                self.json_ld_payloads.append(payload)
            self._in_json_ld = False
            self._json_ld_chunks = []
            return
        if tag.lower() == "title" and self._in_title:
            self.title = clean_text("".join(self._title_chunks))
            self._in_title = False
            self._title_chunks = []

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._json_ld_chunks.append(data)
        if self._in_title:
            self._title_chunks.append(data)


def _json_ld_product_names(payloads: list[str]) -> list[ProductNameEvidence]:
    evidence: list[ProductNameEvidence] = []
    for payload in payloads:
        parsed = _parse_json_ld(payload)
        if parsed is None:
            continue
        for product in _iter_json_ld_products(parsed):
            name = clean_text(product.get("name") if isinstance(product, dict) else None)
            if name:
                evidence.append(_evidence("json_ld_product_name", name))
    return evidence


def _json_ld_product_images(payloads: list[str]) -> list[ProductImageEvidence]:
    evidence: list[ProductImageEvidence] = []
    for payload in payloads:
        parsed = _parse_json_ld(payload)
        if parsed is None:
            continue
        for product in _iter_json_ld_products(parsed):
            for url in _iter_image_urls(product.get("image") if isinstance(product, dict) else None):
                evidence.append(ProductImageEvidence(source="json_ld_product_image", url=url))
    return evidence


def _json_ld_product_prices(payloads: list[str]) -> list[ProductPriceEvidence]:
    evidence: list[ProductPriceEvidence] = []
    for payload in payloads:
        parsed = _parse_json_ld(payload)
        if parsed is None:
            continue
        for product in _iter_json_ld_products(parsed):
            if not isinstance(product, dict):
                continue
            offers = product.get("offers")
            for offer in _iter_offer_dicts(offers):
                price = clean_text(offer.get("price"))
                if price:
                    evidence.append(
                        ProductPriceEvidence(
                            source="json_ld_offer_price",
                            price=price,
                            currency=clean_text(offer.get("priceCurrency")),
                        )
                    )
    return evidence


def _parse_json_ld(payload: str) -> object | None:
    text = payload.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    compact = re.sub(r"\s+", " ", text)
    try:
        return json.loads(compact)
    except json.JSONDecodeError:
        return None


def _iter_json_ld_products(value: object) -> list[dict[str, object]]:
    products: list[dict[str, object]] = []
    if isinstance(value, list):
        for item in value:
            products.extend(_iter_json_ld_products(item))
        return products
    if not isinstance(value, dict):
        return products
    type_value = value.get("@type")
    if _is_product_type(type_value):
        products.append(value)
    graph = value.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            products.extend(_iter_json_ld_products(item))
    return products


def _is_product_type(value: object) -> bool:
    if isinstance(value, str):
        return value.casefold() == "product"
    if isinstance(value, list):
        return any(_is_product_type(item) for item in value)
    return False


def _meta_name_evidence(values: list[tuple[str, str]]) -> list[ProductNameEvidence]:
    return [_evidence(f"meta:{key}", value) for key, value in values]


def _meta_image_evidence(values: list[tuple[str, str]]) -> list[ProductImageEvidence]:
    return [
        ProductImageEvidence(source=f"meta:{key}", url=value)
        for key, value in values
        if clean_text(value)
    ]


def _meta_price_evidence(
    values: list[tuple[str, str]],
    currency_values: list[tuple[str, str]],
) -> list[ProductPriceEvidence]:
    currency = clean_text(currency_values[0][1]) if currency_values else None
    return [
        ProductPriceEvidence(source=f"meta:{key}", price=value, currency=currency)
        for key, value in values
        if clean_text(value)
    ]


def _evidence(source: str, name: str) -> ProductNameEvidence:
    text = unescape(clean_text(name) or "")
    return ProductNameEvidence(
        source=source,
        name=text,
        language=classify_name_language(text),
    )


def _dedupe_evidence(values: list[ProductNameEvidence]) -> list[ProductNameEvidence]:
    deduped: list[ProductNameEvidence] = []
    seen: set[tuple[str, str]] = set()
    for item in values:
        if not item.name:
            continue
        key = (item.source, item.name.casefold())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _dedupe_image_evidence(values: list[ProductImageEvidence]) -> list[ProductImageEvidence]:
    deduped: list[ProductImageEvidence] = []
    seen: set[str] = set()
    for item in values:
        url = clean_text(item.url)
        if not url:
            continue
        key = url
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ProductImageEvidence(source=item.source, url=url))
    return deduped


def _dedupe_price_evidence(values: list[ProductPriceEvidence]) -> list[ProductPriceEvidence]:
    deduped: list[ProductPriceEvidence] = []
    seen: set[tuple[str, str | None]] = set()
    for item in values:
        price = clean_text(item.price)
        if not price:
            continue
        currency = clean_text(item.currency)
        key = (price, currency)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ProductPriceEvidence(source=item.source, price=price, currency=currency))
    return deduped


def _iter_image_urls(value: object) -> list[str]:
    if isinstance(value, str):
        text = clean_text(value)
        return [text] if text else []
    if isinstance(value, list):
        urls: list[str] = []
        for item in value:
            urls.extend(_iter_image_urls(item))
        return urls
    if isinstance(value, dict):
        return _iter_image_urls(value.get("url") or value.get("contentUrl"))
    return []


def _iter_offer_dicts(value: object) -> list[dict[str, object]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        offers: list[dict[str, object]] = []
        for item in value:
            offers.extend(_iter_offer_dicts(item))
        return offers
    return []


def _is_low_confidence_latin_name(name: str, *, rejected_names: set[str]) -> bool:
    text = clean_text(name)
    if not text:
        return True
    key = _name_key(text)
    rejected_keys = {_name_key(value) for value in rejected_names if clean_text(value)}
    if key in rejected_keys:
        return True
    lowered = text.casefold()
    if any(
        marker in lowered
        for marker in [
            "store is unavailable",
            "something went wrong",
            "official shop",
            "official store",
            "homepage",
            "another me",
        ]
    ):
        return True
    tokens = re.findall(r"[A-Za-z0-9™®']+", text)
    if len(tokens) < 2:
        return True
    if len(tokens) <= 2 and any(key.startswith(rejected_key) for rejected_key in rejected_keys):
        return True
    return False


def _name_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())
