from __future__ import annotations

import re

from app.models.editor import EditorParsedLine
from app.normalizer.text import clean_text


HASH_SHADE_RE = re.compile(r"#\s*([0-9A-Za-z가-힣._-]+)")
HO_SHADE_RE = re.compile(r"(?<![0-9A-Za-z가-힣])([0-9]+[A-Za-z0-9]*)\s*호(?![0-9A-Za-z가-힣])")

NON_SHADE_TRAILING_TOKENS = {
    "파우더",
    "하이라이터",
    "아이브로우",
    "브로우",
    "브로우카라",
    "립베이스",
    "틴트",
    "틴트밤",
    "팔레트",
    "쉐딩",
    "섀딩",
    "치크",
    "아라",
    "아이라이너",
    "스키니브로우",
}


def parse_editor_lines(text: str, *, max_lines: int = 100) -> list[EditorParsedLine]:
    lines = [line for raw in text.splitlines() if (line := clean_text(raw))]
    return [parse_editor_line(line) for line in lines[:max_lines]]


def parse_editor_line(raw_text: str) -> EditorParsedLine:
    raw = clean_text(raw_text) or ""
    working = raw
    shade_code: str | None = None
    shade_name: str | None = None

    for match in HASH_SHADE_RE.finditer(raw):
        value = clean_text(match.group(1))
        if not value:
            continue
        if any(char.isdigit() for char in value):
            shade_code = shade_code or value
        else:
            shade_name = shade_name or value
    working = HASH_SHADE_RE.sub(" ", working)

    ho_match = HO_SHADE_RE.search(working)
    if ho_match:
        shade_code = shade_code or f"{ho_match.group(1)}호"
        working = HO_SHADE_RE.sub(" ", working, count=1)

    tokens = [token for token in re.split(r"\s+", working.strip()) if token]
    if not shade_name and len(tokens) >= 3:
        trailing = tokens[-1]
        if _looks_like_implicit_shade(trailing):
            shade_name = trailing
            tokens = tokens[:-1]

    brand_query = tokens[0] if tokens else None
    product_query = " ".join(tokens[1:]) if len(tokens) > 1 else None
    normalized_query = " ".join(tokens) or raw
    shade_query = " ".join(value for value in [shade_code, shade_name] if value) or None

    return EditorParsedLine(
        raw_text=raw,
        brand_query=brand_query,
        product_query=product_query,
        shade_query=shade_query,
        shade_code=shade_code,
        shade_name=shade_name,
        normalized_query=normalized_query,
    )


def _looks_like_implicit_shade(token: str) -> bool:
    text = clean_text(token)
    if not text:
        return False
    if text in NON_SHADE_TRAILING_TOKENS:
        return False
    if len(text) > 12:
        return False
    return True
