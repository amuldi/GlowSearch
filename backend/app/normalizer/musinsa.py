from __future__ import annotations

import re
from typing import Any

import httpx

from app.normalizer.text import clean_text, has_hangul, has_latin


class MusinsaBrandResolver:
    def __init__(
        self,
        *,
        api_base_url: str = "https://api.musinsa.com/api2/dp",
        timeout_seconds: float = 2.5,
        user_agent: str | None = None,
        client: httpx.Client | None = None,
    ):
        self._api_base_url = api_base_url.rstrip("/")
        self._client = client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={
                "Accept": "application/json",
                "User-Agent": user_agent
                or (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/121.0.0.0 Safari/537.36"
                ),
            },
        )
        self._owns_client = client is None
        self._cache: dict[str, str | None] = {}

    def resolve(self, source_brand_name: str | None, *fallback_texts: str | None) -> str | None:
        for query in self._queries(source_brand_name, *fallback_texts):
            resolved = self._resolve_query(query)
            if resolved:
                return resolved
        return None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _resolve_query(self, query: str) -> str | None:
        key = self._key(query)
        if not key:
            return None
        if key in self._cache:
            return self._cache[key]

        resolved: str | None = None
        try:
            response = self._client.get(
                f"{self._api_base_url}/v1/plp/brand",
                params={
                    "caller": "SEARCH",
                    "gf": "A",
                    "keyword": query,
                    "page": 1,
                    "size": 10,
                    "sortCode": "POPULAR",
                },
            )
            response.raise_for_status()
            resolved = self._pick_brand_name(response.json(), query)
        except (httpx.HTTPError, ValueError, TypeError):
            resolved = None

        self._cache[key] = resolved
        return resolved

    def _pick_brand_name(self, payload: dict[str, Any], query: str) -> str | None:
        items = payload.get("data", {}).get("list", [])
        if not isinstance(items, list) or not items:
            return None

        exact_matches = [
            item
            for item in items
            if isinstance(item, dict) and self._is_exact_brand_match(item, query)
        ]
        if exact_matches:
            return self._english_name(exact_matches[0])

        if len(items) == 1 and isinstance(items[0], dict):
            item = items[0]
            brand_name = clean_text(item.get("brandName"))
            if brand_name and self._contains_brand_match(brand_name, query):
                return self._english_name(item)

        return None

    def _is_exact_brand_match(self, item: dict[str, Any], query: str) -> bool:
        query_key = self._key(query)
        values = (
            clean_text(item.get("brandName")),
            clean_text(item.get("brandNameEng")),
            clean_text(item.get("brand")),
        )
        return any(self._key(value) == query_key for value in values if value)

    def _contains_brand_match(self, brand_name: str, query: str) -> bool:
        brand_key = self._key(brand_name)
        query_key = self._key(query)
        return bool(brand_key and query_key and (brand_key in query_key or query_key in brand_key))

    def _english_name(self, item: dict[str, Any]) -> str | None:
        for key in ("brandNameEng", "brand"):
            value = clean_text(item.get(key))
            if self._is_usable_english_brand(value):
                return value
        return None

    def _queries(self, source_brand_name: str | None, *fallback_texts: str | None) -> list[str]:
        candidates = [clean_text(source_brand_name)]
        candidates.extend(self._brand_prefix(text) for text in fallback_texts)

        queries: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if not candidate or self._is_noise(candidate):
                continue
            key = self._key(candidate)
            if key and key not in seen:
                seen.add(key)
                queries.append(candidate)
        return queries

    def _brand_prefix(self, value: str | None) -> str | None:
        text = clean_text(value)
        if text is None:
            return None
        text = re.sub(r"^\s*(?:\[[^\]]+\]\s*)+", "", text)
        text = re.split(r"[\s|/]+", text, maxsplit=1)[0]
        return clean_text(text)

    def _is_usable_english_brand(self, value: str | None) -> bool:
        if value is None or has_hangul(value) or not has_latin(value):
            return False
        if len(value) > 60 or value.casefold() in {"brand", "musinsa", "sale"}:
            return False
        return True

    def _is_noise(self, value: str) -> bool:
        normalized = self._key(value)
        return normalized in {"브랜드", "브랜드미확인", "가격미확인", "상품", "기획", "단품"}

    @staticmethod
    def _key(value: str | None) -> str:
        text = clean_text(value)
        if text is None:
            return ""
        return re.sub(r"[\s\-_./:&'’+]+", "", text).casefold()
