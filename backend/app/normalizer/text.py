from __future__ import annotations

import re
from urllib.parse import urljoin


HANGUL_RE = re.compile(r"[가-힣]")
LATIN_RE = re.compile(r"[A-Za-z]")
PRICE_RE = re.compile(r"(\d[\d,]*)")


def clean_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def parse_krw_price(value: object | None) -> int | None:
    text = clean_text(value)
    if text is None:
        return None
    if "~" in text or "부터" in text:
        return None
    match = PRICE_RE.search(text)
    if not match:
        return None
    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_krw_display_price(value: object | None) -> int | None:
    text = clean_text(value)
    if text is None:
        return None
    match = PRICE_RE.search(text)
    if not match:
        return None
    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return None


def normalize_image_url(value: str | None, base_url: str) -> str | None:
    text = clean_text(value)
    if text is None:
        return None
    if text.startswith("//"):
        return f"https:{text}"
    return urljoin(base_url, text)


def has_hangul(value: str | None) -> bool:
    return bool(value and HANGUL_RE.search(value))


def has_latin(value: str | None) -> bool:
    return bool(value and LATIN_RE.search(value))
