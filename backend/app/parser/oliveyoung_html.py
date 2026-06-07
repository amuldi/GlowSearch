from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.models.product import ProductSourceRecord
from app.normalizer.text import clean_text, normalize_image_url, parse_krw_display_price, parse_krw_price


GOODS_NO_RE = re.compile(r"goodsNo=([A-Z0-9]+)")
MOVE_GOODS_RE = re.compile(r"moveGoodsDetail\(['\"]([A-Z0-9]+)['\"]")
PRODUCT_OBJECT_RE = re.compile(
    r"\{[^{}]*(?:goodsNo|goodsNm|goodsName|prdNm|productName|prdtName)[^{}]*\}",
    flags=re.DOTALL,
)
JS_OBJECT_KEY_RE = re.compile(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:")
JS_SINGLE_QUOTED_RE = re.compile(r"'([^'\\]*(?:\\.[^'\\]*)*)'")
SHADE_RE = re.compile(
    r"(?:#?\d{1,3}\s*(?:호|번|\.|-)?\s*[가-힣A-Za-z0-9][^,\n/|]{0,36}|"
    r"[가-힣A-Za-z0-9]+\s*(?:핑크|레드|코랄|베이지|브라운|누드|로즈|오렌지|라벤더|아이보리|블랙|화이트|그레이))"
)

SEARCH_ITEM_SELECTORS = (
    "ul.cate_prd_list > li",
    "ul.prd_list > li",
    "li[data-ref-goodsno]",
    "li[data-goods-no]",
    "div.prd_info",
)
BRAND_SELECTORS = (
    ".tx_brand",
    ".prd_brand",
    "[data-qa-name='text-brand-name']",
    "[class*='brand']",
)
NAME_SELECTORS = (
    "[data-qa-name='text-product-title']",
    "[class*='title-area'] h3",
    ".tx_name",
    ".prd_name .tx_name",
    ".prd_name",
    "[class*='goods-name']",
    "[class*='product-name']",
)
OFFICIAL_PRICE_SELECTORS = (
    "[data-qa-name='text-product-original-price']",
    "[class*='original-price']",
    ".prd_price .tx_org",
    ".price .tx_org",
    "[class*='price'] [class*='org']",
)
CURRENT_PRICE_SELECTORS = (
    "[data-qa-name='text-product-discount-price']",
    "[data-qa-name='text-product-price']",
    "[class*='price-area'] [class*='price__']",
    ".prd_price .tx_cur",
    ".prd_price",
    ".price",
    "[class*='price']",
)
OPTION_SELECTORS = (
    "select option",
    ".prd_option_box li",
    ".prd_option_box button",
    ".option_box li",
    ".option_box button",
    "[class*='option'] li",
    "[class*='option'] button",
)
CATEGORY_SELECTORS = (
    ".loc_history",
    ".breadcrumb",
    "[class*='breadcrumb']",
    "[class*='category']",
)
RATING_SELECTORS = (
    "[class*='rating']",
    "[class*='score']",
    ".prd_point_area",
)
REVIEW_COUNT_SELECTORS = (
    "[class*='review']",
    ".review_point",
    ".goods_reputation",
)


def parse_search_results(html: str, *, base_url: str, limit: int) -> list[ProductSourceRecord]:
    soup = BeautifulSoup(html, "html.parser")
    records = _parse_structured_product_json(soup, base_url=base_url)
    records.extend(_parse_embedded_product_literals(soup, base_url=base_url))

    candidates: list[Tag] = []
    for selector in SEARCH_ITEM_SELECTORS:
        candidates.extend(tag for tag in soup.select(selector) if isinstance(tag, Tag))

    for node in candidates:
        record = _parse_product_node(node, base_url=base_url)
        if record and (record.product_name_ko or record.source_product_id):
            records.append(record)

    return _dedupe(records)[:limit]


def parse_detail_page(html: str, *, base_url: str, source_url: str | None = None) -> ProductSourceRecord:
    soup = BeautifulSoup(html, "html.parser")
    structured = _parse_structured_product_json(soup, base_url=base_url)
    base = structured[0] if structured else ProductSourceRecord(source="oliveyoung", source_url=source_url)

    brand = base.source_brand_name or _first_text(soup, BRAND_SELECTORS)
    title = base.product_name_ko or _detail_title(soup)
    image = base.image_url or _meta_content(soup, "og:image") or _first_image(soup, base_url)
    original_price, sale_price = _detail_prices(soup)
    original_price = base.original_price or original_price or base.regular_price
    sale_price = base.sale_price or sale_price
    sale_price = _sale_price_only_if_discounted(original_price, sale_price)
    price = sale_price if sale_price is not None else original_price
    shade = base.shade or _extract_shade(soup)
    options = base.options or _extract_options(soup)
    goods_no = base.source_product_id or _extract_goods_no(source_url or "") or _extract_goods_no(str(soup))

    return ProductSourceRecord(
        source_brand_name=brand,
        product_name_ko=title,
        category=base.category or _extract_category(soup),
        regular_price=price,
        original_price=original_price,
        sale_price=sale_price,
        discount_rate=base.discount_rate,
        rating=base.rating or _extract_rating(soup),
        review_count=base.review_count or _extract_review_count(soup),
        shade=shade,
        description=base.description or _meta_content(soup, "og:description"),
        options=options,
        sold_out=base.sold_out if base.sold_out is not None else _is_sold_out(soup),
        image_url=image,
        source="oliveyoung",
        source_url=source_url or base.source_url,
        source_product_id=goods_no,
        updated_at=base.updated_at,
    )


def _parse_product_node(node: Tag, *, base_url: str) -> ProductSourceRecord | None:
    brand = _first_text(node, BRAND_SELECTORS) or _first_attr(
        node,
        "data-brand-name",
        "data-brand-nm",
        "data-brnd-name",
        "data-brnd-nm",
        "data-onl-brnd-nm",
    )
    name = _first_text(node, NAME_SELECTORS) or _first_attr(
        node,
        "data-goods-name",
        "data-goods-nm",
        "data-prd-name",
        "data-prdt-name",
        "data-product-name",
        "title",
        "aria-label",
    )

    original_price, sale_price = _node_prices(node)
    attr_original_price = parse_krw_price(
        _first_attr(
            node,
            "data-normal-price",
            "data-regular-price",
            "data-org-price",
            "data-nrml-amt",
        )
    )
    attr_sale_price = parse_krw_price(
        _first_attr(
            node,
            "data-sale-price",
            "data-price-to-pay",
            "data-current-price",
            "data-discount-price",
            "data-price",
        )
    )
    original_price = original_price or attr_original_price
    sale_price = sale_price or attr_sale_price
    sale_price = _sale_price_only_if_discounted(original_price, sale_price)
    price = sale_price if sale_price is not None else original_price
    image = _first_image(node, base_url) or normalize_image_url(
        _first_attr(
            node,
            "data-image-url",
            "data-img-url",
            "data-img-path",
            "data-thumb-url",
            "data-thumbnail",
        ),
        base_url,
    )
    source_url = _first_product_url(node, base_url)
    goods_no = (
        _extract_goods_no(source_url or "")
        or _first_attr(
            node,
            "data-ref-goodsno",
            "data-ref-goods-no",
            "data-goods-no",
            "data-goodsno",
            "data-prd-no",
            "data-prdt-no",
        )
        or _extract_goods_no(str(node))
    )
    if source_url is None and goods_no:
        source_url = f"{base_url}/store/goods/getGoodsDetail.do?goodsNo={goods_no}"

    if not any([brand, name, price, image, goods_no]):
        return None

    return ProductSourceRecord(
        source_brand_name=brand,
        product_name_ko=name,
        category=clean_text(
            _first_attr(node, "data-category", "data-category-name", "data-disp-cat-nm")
        ),
        regular_price=price,
        original_price=original_price,
        sale_price=sale_price,
        shade=None,
        sold_out=_is_sold_out(node),
        image_url=image,
        source="oliveyoung",
        source_url=source_url,
        source_product_id=goods_no,
    )


def _parse_structured_product_json(soup: BeautifulSoup, *, base_url: str) -> list[ProductSourceRecord]:
    records: list[ProductSourceRecord] = []
    for script in soup.select("script[type='application/ld+json'], script#__NEXT_DATA__"):
        text = script.string or script.get_text()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        for item in _walk_json(payload):
            record = _record_from_mapping(item, base_url=base_url)
            if record:
                records.append(record)
    return records


def _parse_embedded_product_literals(
    soup: BeautifulSoup,
    *,
    base_url: str,
) -> list[ProductSourceRecord]:
    records: list[ProductSourceRecord] = []
    for script in soup.select("script"):
        text = script.string or script.get_text()
        if not text or not _has_product_marker(text):
            continue
        for match in PRODUCT_OBJECT_RE.finditer(text):
            payload = _load_js_object(match.group(0))
            if not isinstance(payload, dict):
                continue
            record = _record_from_mapping(payload, base_url=base_url)
            if record:
                records.append(record)
    return records


def _has_product_marker(text: str) -> bool:
    return any(marker in text for marker in ("goodsNo", "goodsNm", "goodsName", "prdtName"))


def _load_js_object(text: str) -> dict | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    normalized = JS_OBJECT_KEY_RE.sub(r'\1"\2":', text)
    normalized = JS_SINGLE_QUOTED_RE.sub(
        lambda match: json.dumps(match.group(1)),
        normalized,
    )
    normalized = re.sub(r",\s*([}\]])", r"\1", normalized)
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _record_from_mapping(item: dict, *, base_url: str) -> ProductSourceRecord | None:
    name = _pick(
        item,
        "name",
        "productName",
        "goodsNm",
        "goodsName",
        "prdNm",
        "prdtName",
        "dispGoodsNm",
        "goodsFullNm",
        "onlineGoodsNm",
    )
    brand_raw = _pick(
        item,
        "brand",
        "brandName",
        "brandNm",
        "brndNm",
        "onlBrndNm",
        "maker",
    )
    if isinstance(brand_raw, dict):
        brand = _pick(brand_raw, "name", "brandName", "brandNm", "brndNm")
    else:
        brand = brand_raw

    image_raw = _pick(
        item,
        "image",
        "imageUrl",
        "imgUrl",
        "thumbnail",
        "goodsImg",
        "goodsImgUrl",
        "mainImgUrl",
        "imgPathNm",
        "thumbImgUrl",
    )
    if isinstance(image_raw, list):
        image_raw = next((value for value in image_raw if isinstance(value, str)), None)

    offers = item.get("offers") if isinstance(item.get("offers"), dict) else {}
    original_price = parse_krw_price(
        _pick(
            item,
            "regularPrice",
            "normalPrice",
            "originalPrice",
            "nrmlAmt",
            "stdPrc",
            "orgPrice",
            "listPrice",
            "goodsPrc",
        )
    )
    sale_price = (
        parse_krw_price(
            _pick(
                item,
                "priceToPay",
                "salePrice",
                "discountPrice",
                "discountedPrice",
                "currentPrice",
                "finalPrice",
                "price",
            )
        )
        or parse_krw_price(_pick(offers, "price", "lowPrice"))
    )
    if original_price is None:
        original_price = parse_krw_price(_pick(offers, "highPrice"))
    sale_price = _sale_price_only_if_discounted(original_price, sale_price)
    price = sale_price if sale_price is not None else original_price
    source_url = _pick(item, "url", "link", "goodsUrl", "goodsDetailUrl", "productUrl")
    source_url = urljoin(base_url, source_url) if isinstance(source_url, str) else None
    goods_no = _pick(
        item,
        "goodsNo",
        "goodsNumber",
        "goodsId",
        "productId",
        "prdtNo",
        "prdNo",
        "id",
    )
    if not goods_no:
        goods_no = _extract_goods_no(source_url or "")
    if source_url is None and goods_no:
        source_url = f"{base_url}/store/goods/getGoodsDetail.do?goodsNo={goods_no}"

    if not any([name, brand, image_raw, price, goods_no]):
        return None

    return ProductSourceRecord(
        source_brand_name=clean_text(brand),
        product_name_ko=clean_text(name),
        category=clean_text(
            _pick(
                item,
                "category",
                "categoryName",
                "categoryFullName",
                "dispCatNm",
                "displayCategory",
            )
        ),
        regular_price=price,
        original_price=original_price,
        sale_price=sale_price,
        discount_rate=_parse_int(_pick(item, "discountRate", "dcRate", "discount_rate")),
        rating=_parse_float(_pick(item, "ratingValue", "rating", "avgRating", "reviewScore")),
        review_count=_parse_int(
            _pick(item, "reviewCount", "reviewsCount", "reviewCnt", "ratingCount")
        ),
        shade=clean_text(_pick(item, "shade", "color", "optionName")),
        description=clean_text(_pick(item, "description", "summary", "goodsDesc")),
        options=_parse_options(_pick(item, "options", "optionNames", "variants")),
        sold_out=_parse_sold_out(item),
        image_url=normalize_image_url(clean_text(image_raw), base_url),
        source="oliveyoung",
        source_url=source_url,
        source_product_id=clean_text(goods_no),
        updated_at=clean_text(_pick(item, "updatedAt", "updated_at", "lastUpdatedAt")),
    )


def _walk_json(value: object) -> Iterator[dict]:
    if isinstance(value, dict):
        if _looks_like_product(value):
            yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _looks_like_product(item: dict) -> bool:
    keys = {str(key) for key in item.keys()}
    has_name = bool(
        keys
        & {
            "name",
            "productName",
            "goodsNm",
            "goodsName",
            "prdNm",
            "prdtName",
            "dispGoodsNm",
            "goodsFullNm",
            "onlineGoodsNm",
        }
    )
    has_product_id = bool(
        keys & {"goodsNo", "goodsNumber", "goodsId", "productId", "prdtNo", "prdNo", "id"}
    )
    has_image = bool(
        keys
        & {
            "image",
            "imageUrl",
            "imgUrl",
            "thumbnail",
            "goodsImg",
            "goodsImgUrl",
            "mainImgUrl",
            "imgPathNm",
            "thumbImgUrl",
        }
    )
    return has_name and (has_product_id or has_image)


def _pick(mapping: dict, *keys: str) -> object | None:
    for key in keys:
        if key in mapping and mapping[key] not in ("", None):
            return mapping[key]
    return None


def _first_text(node: Tag | BeautifulSoup, selectors: Iterable[str]) -> str | None:
    for selector in selectors:
        found = node.select_one(selector)
        if found:
            text = clean_text(found.get_text(" ", strip=True))
            if text:
                return text
    return None


def _first_attr(node: Tag, *attrs: str) -> str | None:
    for attr in attrs:
        value = clean_text(node.get(attr))
        if value:
            return value
    for child in node.select("*"):
        for attr in attrs:
            value = clean_text(child.get(attr))
            if value:
                return value
    return None


def _meta_content(soup: BeautifulSoup, property_name: str) -> str | None:
    node = soup.select_one(f"meta[property='{property_name}'], meta[name='{property_name}']")
    if not node:
        return None
    return clean_text(node.get("content"))


def _detail_title(soup: BeautifulSoup) -> str | None:
    title = _first_text(
        soup,
        (
            "[data-qa-name='text-product-title']",
            "[class*='title-area'] h3",
            ".prd_detail_box .prd_name",
            "p.prd_name",
            "h3",
            "h1",
        ),
    )
    if title:
        return title
    meta_title = _meta_content(soup, "og:title")
    if meta_title:
        return clean_text(meta_title.split("|")[0])
    return None


def _detail_prices(soup: BeautifulSoup) -> tuple[int | None, int | None]:
    price_meta = _meta_content(soup, "product:price:amount")
    original_price, sale_price = _node_prices(soup)
    if price_meta:
        meta_price = parse_krw_display_price(price_meta)
        sale_price = sale_price or meta_price
    return original_price, _sale_price_only_if_discounted(original_price, sale_price)


def _node_price(node: Tag | BeautifulSoup) -> int | None:
    original_price, sale_price = _node_prices(node)
    return original_price or sale_price


def _node_prices(node: Tag | BeautifulSoup) -> tuple[int | None, int | None]:
    original_price = None
    for selector in OFFICIAL_PRICE_SELECTORS:
        found = node.select_one(selector)
        if found:
            price = parse_krw_price(found.get_text(" ", strip=True))
            if price is not None:
                original_price = price
                break

    sale_price = None
    for selector in CURRENT_PRICE_SELECTORS:
        found = node.select_one(selector)
        if found:
            price = parse_krw_display_price(found.get_text(" ", strip=True))
            if price is not None:
                sale_price = price
                break
    return original_price, _sale_price_only_if_discounted(original_price, sale_price)


def _sale_price_only_if_discounted(
    original_price: int | None,
    sale_price: int | None,
) -> int | None:
    if sale_price is None:
        return None
    if original_price is None:
        return sale_price
    return sale_price if sale_price < original_price else None


def _parse_int(value: object | None) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        digits = re.sub(r"[^0-9]", "", value)
        return int(digits) if digits else None
    return None


def _parse_float(value: object | None) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", "."))
        except ValueError:
            return None
    return None


def _parse_options(value: object | None) -> list[str] | None:
    if isinstance(value, str):
        option = clean_text(value)
        return [option] if option else None
    if not isinstance(value, list):
        return None
    options: list[str] = []
    for item in value:
        option = clean_text(item) if isinstance(item, str) else None
        if isinstance(item, dict):
            option = clean_text(_pick(item, "name", "optionName", "title", "color"))
        if option and option not in options:
            options.append(option)
    return options or None


def _parse_sold_out(item: dict) -> bool | None:
    sold_out = _pick(item, "soldOut", "sold_out", "outOfStock")
    if isinstance(sold_out, bool):
        return sold_out
    availability = clean_text(_pick(item, "availability", "stockStatus", "status"))
    if availability:
        key = availability.casefold()
        if any(token in key for token in ("sold_out", "out_of_stock", "품절")):
            return True
        if any(token in key for token in ("in_stock", "available", "판매중")):
            return False
    return None


def _first_image(node: Tag | BeautifulSoup, base_url: str) -> str | None:
    for image in node.select("img"):
        src = (
            image.get("src")
            or image.get("data-src")
            or image.get("data-original")
            or image.get("data-lazy")
            or image.get("data-image-url")
            or image.get("data-img-url")
            or image.get("data-img-path")
        )
        normalized = normalize_image_url(clean_text(src), base_url)
        if normalized:
            return normalized
    return None


def _first_product_url(node: Tag, base_url: str) -> str | None:
    for anchor in node.select("a[href]"):
        href = clean_text(anchor.get("href"))
        if not href:
            continue
        goods_no = _extract_goods_no(href)
        if goods_no:
            if "getGoodsDetail.do" in href:
                return urljoin(base_url, href)
            return f"{base_url}/store/goods/getGoodsDetail.do?goodsNo={goods_no}"
        if "getGoodsDetail.do" in href:
            return urljoin(base_url, href)
    goods_no = _extract_goods_no(str(node))
    if goods_no:
        return f"{base_url}/store/goods/getGoodsDetail.do?goodsNo={goods_no}"
    return None


def _extract_goods_no(value: str) -> str | None:
    match = GOODS_NO_RE.search(value)
    if match:
        return match.group(1)
    match = MOVE_GOODS_RE.search(value)
    if match:
        return match.group(1)
    return None


def _extract_shade(soup: BeautifulSoup) -> str | None:
    candidates: list[str] = []
    for selector in OPTION_SELECTORS:
        for node in soup.select(selector):
            text = clean_text(node.get_text(" ", strip=True))
            if not text or _is_option_noise(text):
                continue
            for match in SHADE_RE.findall(text):
                shade = clean_text(match)
                if shade and not _is_option_noise(shade):
                    candidates.append(shade)

    unique: list[str] = []
    seen: set[str] = set()
    for shade in candidates:
        key = shade.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(shade)
    if not unique:
        return None
    return ", ".join(unique[:12])


def _extract_options(soup: BeautifulSoup) -> list[str] | None:
    options: list[str] = []
    seen: set[str] = set()
    for selector in OPTION_SELECTORS:
        for node in soup.select(selector):
            text = clean_text(node.get_text(" ", strip=True))
            if not text or _is_option_noise(text):
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            options.append(text)
    return options[:30] or None


def _extract_category(soup: BeautifulSoup) -> str | None:
    for selector in CATEGORY_SELECTORS:
        node = soup.select_one(selector)
        if not node:
            continue
        text = clean_text(node.get_text(" > ", strip=True))
        if text and not _is_option_noise(text):
            return text
    return None


def _extract_rating(soup: BeautifulSoup) -> float | None:
    for selector in RATING_SELECTORS:
        node = soup.select_one(selector)
        if not node:
            continue
        rating = _parse_rating_text(node.get_text(" ", strip=True))
        if rating is not None:
            return rating
    return None


def _extract_review_count(soup: BeautifulSoup) -> int | None:
    for selector in REVIEW_COUNT_SELECTORS:
        node = soup.select_one(selector)
        if not node:
            continue
        review_count = _parse_review_count_text(node.get_text(" ", strip=True))
        if review_count is not None:
            return review_count
    return None


def _parse_rating_text(value: str) -> float | None:
    match = re.search(r"([0-5](?:[.,]\d)?)\s*(?:점|/)", value)
    if not match:
        return None
    return _parse_float(match.group(1))


def _parse_review_count_text(value: str) -> int | None:
    if "리뷰" not in value and "review" not in value.casefold():
        return None
    match = re.search(r"([\d,]+)\s*(?:건|개)?", value)
    if not match:
        return None
    return _parse_int(match.group(1))


def _is_sold_out(node: Tag | BeautifulSoup) -> bool | None:
    text = clean_text(node.get_text(" ", strip=True))
    if not text:
        return None
    if any(token in text for token in ("품절", "일시품절", "구매불가")):
        return True
    return None


def _is_option_noise(text: str) -> bool:
    noise = (
        "상품을 선택",
        "품절",
        "선택",
        "옵션",
        "구매불가",
        "재입고",
        "장바구니",
        "바로구매",
    )
    return any(item in text for item in noise)


def _dedupe(records: list[ProductSourceRecord]) -> list[ProductSourceRecord]:
    deduped: list[ProductSourceRecord] = []
    seen: set[str] = set()
    for record in records:
        key = record.source_product_id or f"{record.source_brand_name}:{record.product_name_ko}"
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped
