from __future__ import annotations

import re
from collections.abc import Iterable

from app.normalizer.text import clean_text


TEXT_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("브러쉬", "브러시"),
    ("brush", "브러시"),
    ("eyeliner", "아이라이너"),
    ("eye shadow", "아이섀도"),
    ("eye-shadow", "아이섀도"),
    ("쉐딩", "섀딩"),
    ("셰딩", "섀딩"),
    ("gray", "그레이"),
    ("grey", "그레이"),
    ("sunscreen", "선크림"),
    ("sun cream", "선크림"),
    ("sun-cream", "선크림"),
    ("sun block", "선크림"),
    ("sunblock", "선크림"),
    ("body lotion", "바디로션"),
    ("body-lotion", "바디로션"),
    ("skin lotion", "스킨로션"),
    ("skin-lotion", "스킨로션"),
    ("lotion", "로션"),
    ("foundation", "파운데이션"),
    ("foundations", "파운데이션"),
    ("lip tint", "립틴트"),
    ("lip-tint", "립틴트"),
    ("gloss", "글로스"),
    ("lip gloss", "립글로스"),
    ("lip-gloss", "립글로스"),
    ("vitamin c", "비타민씨"),
    ("vitamin-c", "비타민씨"),
)

RELATED_QUERY_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "젤": (
        "클렌징젤",
        "필링젤",
        "수딩젤",
        "젤크림",
    ),
    "틴트": (
        "립틴트",
        "글로스",
        "립글로스",
        "글로우 틴트",
    ),
    "립틴트": (
        "틴트",
        "글로스",
        "립글로스",
    ),
    "글로스": (
        "립글로스",
        "립틴트",
        "글로우 틴트",
    ),
    "쿠션": (
        "파운데이션",
        "메쉬 쿠션",
        "커버 쿠션",
        "선쿠션",
    ),
    "파운데이션": (
        "쿠션",
        "베이스",
        "파데",
    ),
    "선크림": (
        "선스크린",
        "선세럼",
        "선스틱",
        "톤업 선크림",
        "수분 선크림",
    ),
    "선스크린": (
        "선크림",
        "선세럼",
        "선스틱",
    ),
    "로션": (
        "바디로션",
        "스킨로션",
        "보습 로션",
        "수분 로션",
    ),
    "바디로션": (
        "로션",
        "보습 로션",
        "수분 로션",
    ),
    "정샘물": (
        "비긴스 바이 정샘물",
        "정샘물 쿠션",
        "정샘물 립",
        "정샘물 브러쉬",
    ),
    "비긴스": (
        "비긴스 바이 정샘물",
        "비긴스 바이 정샘물 세럼",
        "비긴스 바이 정샘물 선크림",
    ),
}


def canonical_text(value: str | None) -> str:
    text = clean_text(value)
    if text is None:
        return ""
    normalized = text.casefold()
    for source, target in TEXT_REPLACEMENTS:
        normalized = normalized.replace(source, target)
    return normalized


def search_key(value: str | None) -> str:
    return re.sub(r"[\s\-_./|+&'():\[\],]+", "", canonical_text(value))


def related_query_expansions(value: str | None) -> tuple[str, ...]:
    return RELATED_QUERY_EXPANSIONS.get(search_key(value), ())


def dedupe_queries(values: Iterable[str | None]) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_text(value)
        key = search_key(text)
        if not text or not key or key in seen:
            continue
        seen.add(key)
        queries.append(text)
    return queries
