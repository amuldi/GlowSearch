from __future__ import annotations

import re
from collections.abc import Iterable

from app.normalizer.text import clean_text


TEXT_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("브러쉬", "브러시"),
    ("brush", "브러시"),
    ("eyeliner", "아이라이너"),
    ("eye liner", "아이라이너"),
    ("eye shadow", "아이섀도"),
    ("eye-shadow", "아이섀도"),
    ("eyeshadow", "아이섀도"),
    ("쉐딩", "섀딩"),
    ("셰딩", "섀딩"),
    ("gray", "그레이"),
    ("grey", "그레이"),
    ("sunscreen", "선크림"),
    ("sun cream", "선크림"),
    ("sun-cream", "선크림"),
    ("sun block", "선크림"),
    ("sunblock", "선크림"),
    ("sun serum", "선세럼"),
    ("sun stick", "선스틱"),
    ("body lotion", "바디로션"),
    ("body-lotion", "바디로션"),
    ("body wash", "바디워시"),
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
    ("lip balm", "립밤"),
    ("lipstick", "립스틱"),
    ("lip stick", "립스틱"),
    ("vitamin c", "비타민씨"),
    ("vitamin-c", "비타민씨"),
    # 스킨케어 영문 → 한글
    ("serum", "세럼"),
    ("ampoule", "앰플"),
    ("ampule", "앰플"),
    ("essence", "에센스"),
    ("toner", "토너"),
    ("moisturizer", "크림"),
    ("eye cream", "아이크림"),
    ("night cream", "나이트크림"),
    ("sleeping pack", "슬리핑팩"),
    ("sheet mask", "마스크팩"),
    ("mask pack", "마스크팩"),
    ("face mask", "마스크팩"),
    ("foam cleanser", "폼클렌저"),
    ("face wash", "폼클렌저"),
    ("cleansing oil", "클렌징오일"),
    ("cleansing balm", "클렌징밤"),
    ("cleansing milk", "클렌징밀크"),
    ("cleanser", "클렌저"),
    ("cleansing", "클렌징"),
    ("scrub", "스크럽"),
    ("exfoliant", "필링젤"),
    ("peeling gel", "필링젤"),
    ("mist", "미스트"),
    ("facial oil", "페이스오일"),
    ("face oil", "페이스오일"),
    # 메이크업 영문 → 한글
    ("bb cream", "비비크림"),
    ("cc cream", "CC크림"),
    ("cushion", "쿠션"),
    ("primer", "프라이머"),
    ("concealer", "컨실러"),
    ("contour", "컨투어링"),
    ("blusher", "블러셔"),
    ("blush", "블러셔"),
    ("highlighter", "하이라이터"),
    ("mascara", "마스카라"),
    ("eyebrow", "눈썹"),
    ("eye brow", "눈썹"),
    ("brow pencil", "브로우펜슬"),
    ("brow mascara", "브로우마스카라"),
    ("setting powder", "세팅파우더"),
    ("loose powder", "루스파우더"),
    ("setting spray", "세팅스프레이"),
    ("lip liner", "립라이너"),
    ("lip color", "립스틱"),
    ("lipcolor", "립스틱"),
)

RELATED_QUERY_EXPANSIONS: dict[str, tuple[str, ...]] = {
    # 립 메이크업
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
        "립스틱",
    ),
    "립스틱": (
        "립틴트",
        "립글로스",
        "립밤",
        "립컬러",
    ),
    "립밤": (
        "립케어",
        "립트리트먼트",
    ),
    "글로스": (
        "립글로스",
        "립틴트",
        "글로우 틴트",
    ),
    # 베이스 메이크업
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
        "비비크림",
    ),
    "비비크림": (
        "BB크림",
        "파운데이션",
        "쿠션",
    ),
    "BB크림": (
        "비비크림",
        "파운데이션",
        "쿠션",
    ),
    "CC크림": (
        "씨씨크림",
        "비비크림",
        "파운데이션",
    ),
    "프라이머": (
        "메이크업 베이스",
        "베이스 프라이머",
        "선 프라이머",
    ),
    # 아이 메이크업
    "마스카라": (
        "볼륨 마스카라",
        "컬링 마스카라",
        "롱래쉬 마스카라",
    ),
    "아이라이너": (
        "젤 아이라이너",
        "펜슬 아이라이너",
        "리퀴드 아이라이너",
    ),
    "아이섀도": (
        "아이섀도우",
        "아이 팔레트",
        "섀도우 팔레트",
    ),
    "아이섀도우": (
        "아이섀도",
        "아이 팔레트",
    ),
    "눈썹": (
        "브로우 펜슬",
        "브로우마스카라",
        "아이브로우",
    ),
    "브로우": (
        "눈썹",
        "브로우 펜슬",
        "브로우마스카라",
    ),
    # 치크/하이라이터/섀딩
    "블러셔": (
        "블러시",
        "볼터치",
        "치크",
    ),
    "블러시": (
        "블러셔",
        "볼터치",
        "치크",
    ),
    "볼터치": (
        "블러셔",
        "블러시",
        "치크",
    ),
    "하이라이터": (
        "하이라이트",
        "글로우 하이라이터",
        "일루미네이터",
    ),
    "섀딩": (
        "컨투어",
        "컨투어링",
        "쉐딩",
    ),
    "컨실러": (
        "컨씰러",
        "커버 컨실러",
    ),
    # 선케어
    "선크림": (
        "선스크린",
        "선세럼",
        "선스틱",
        "톤업 선크림",
        "수분 선크림",
        "자외선차단제",
    ),
    "선스크린": (
        "선크림",
        "선세럼",
        "선스틱",
    ),
    "선스틱": (
        "선크림",
        "선스크린",
        "선세럼",
    ),
    "선세럼": (
        "선크림",
        "선스크린",
    ),
    "자외선차단제": (
        "선크림",
        "선스틱",
        "선세럼",
        "선스크린",
    ),
    # 스킨케어 - 세럼/에센스/앰플
    "세럼": (
        "앰플",
        "에센스",
        "부스터 세럼",
    ),
    "에센스": (
        "세럼",
        "앰플",
    ),
    "앰플": (
        "세럼",
        "에센스",
    ),
    # 스킨케어 - 토너/스킨
    "토너": (
        "스킨",
        "화장수",
        "수분 토너",
        "미스트 토너",
    ),
    "스킨": (
        "토너",
        "화장수",
    ),
    # 스킨케어 - 크림
    "크림": (
        "수분크림",
        "젤크림",
        "영양크림",
        "보습크림",
    ),
    "수분크림": (
        "크림",
        "보습크림",
        "젤크림",
    ),
    "아이크림": (
        "눈크림",
        "눈가 크림",
    ),
    "슬리핑팩": (
        "수면팩",
        "나이트크림",
        "슬립 마스크",
    ),
    # 스킨케어 - 클렌징
    "클렌저": (
        "폼클렌저",
        "클렌징폼",
        "젤클렌저",
        "클렌징오일",
        "클렌징밤",
    ),
    "클렌징": (
        "클렌저",
        "폼클렌저",
        "클렌징오일",
        "클렌징밤",
    ),
    "폼클렌저": (
        "클렌저",
        "클렌징폼",
        "젤클렌저",
    ),
    # 스킨케어 - 마스크/필링
    "마스크팩": (
        "시트마스크",
        "마스크 시트",
        "클레이마스크",
        "패드",
    ),
    "시트마스크": (
        "마스크팩",
        "마스크 시트",
    ),
    "필링젤": (
        "각질케어",
        "스크럽",
        "필링",
    ),
    # 미스트/오일
    "미스트": (
        "스킨미스트",
        "페이스미스트",
        "토너미스트",
    ),
    "오일": (
        "페이스오일",
        "바디오일",
        "클렌징오일",
    ),
    # 로션
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
        "바디크림",
    ),
    # 브랜드 확장
    "정샘물": (
        "비긴스 바이 정샘물",
        "정샘물 쿠션",
        "정샘물 립",
        "정샘물 브러쉬",
    ),
    "클리오": (
        "킬커버",
        "클리오 쿠션",
        "클리오 틴트",
        "클리오 마스카라",
    ),
    "clio": (
        "킬커버",
        "클리오 쿠션",
        "클리오 틴트",
        "클리오 마스카라",
    ),
    "비긴스": (
        "비긴스 바이 정샘물",
        "비긴스 바이 정샘물 세럼",
        "비긴스 바이 정샘물 선크림",
    ),
}

SUGGESTION_TERMS: tuple[str, ...] = (
    "투쿨포스쿨",
    "TOO COOL FOR SCHOOL",
    "클리오",
    "CLIO",
    "킬커버",
    "투크",
    "투에이엔",
    "투슬래시포",
    "투크 블러셔",
    "립타투",
    "타투",
    "눈썹타투",
    "두피타투",
    "아토앤오투",
    "틴트",
    "립틴트",
    "립글로스",
    "쿠션",
    "파운데이션",
    "선크림",
    "선스틱",
    "클렌징젤",
    "필링젤",
    "수딩젤",
    "젤크림",
    "로션",
    "바디로션",
)


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
