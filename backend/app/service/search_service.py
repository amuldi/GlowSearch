from __future__ import annotations

import inspect
import re
import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, replace

from app.cache.ttl import AsyncTTLCache
from app.data_collector.base import ProductCollector, SearchCriteria, SourceUnavailableError
from app.models.product import ProductSearchResult, ProductSourceRecord, SearchResponse
from app.normalizer.brand import BrandMatch
from app.normalizer.product import ProductNormalizer
from app.normalizer.text import clean_text


@dataclass
class _CollectedResult:
    records: list[ProductSourceRecord]
    errors: list[str]


class SearchService:
    _BATCH_CONCURRENCY = 4

    def __init__(
        self,
        collectors: list[ProductCollector],
        normalizer: ProductNormalizer,
        cache: AsyncTTLCache[_CollectedResult],
    ):
        self._collectors = collectors
        self._normalizer = normalizer
        self._cache = cache

    async def search(self, query: str, criteria: SearchCriteria) -> SearchResponse:
        cleaned_query = query.strip()
        if not cleaned_query:
            return SearchResponse(query=query, count=0, results=[])

        batch_queries = self._split_batch_queries(cleaned_query)
        if len(batch_queries) > 1:
            return await self._search_batch(cleaned_query, batch_queries, criteria)
        return await self._search_one(batch_queries[0], criteria)

    async def _search_batch(
        self,
        original_query: str,
        queries: list[str],
        criteria: SearchCriteria,
    ) -> SearchResponse:
        limited_queries = queries[: criteria.limit]
        per_query_criteria = replace(criteria, limit=1)
        semaphore = asyncio.Semaphore(self._BATCH_CONCURRENCY)
        allow_browser_retry = len(limited_queries) <= 5

        async def run_query(query: str) -> SearchResponse:
            async with semaphore:
                return await self._search_one(
                    query,
                    per_query_criteria,
                    require_relevant=True,
                    allow_browser_retry=allow_browser_retry,
                    allow_browser_fallback=False,
                )

        responses = await asyncio.gather(*(run_query(query) for query in limited_queries))
        results = [response.results[0] for response in responses if response.results]
        errors = self._dedupe_errors(
            error for response in responses for error in response.source_errors
        )
        return SearchResponse(
            query=original_query,
            count=len(results),
            results=results,
            source_errors=errors,
        )

    async def _search_one(
        self,
        query: str,
        criteria: SearchCriteria,
        *,
        require_relevant: bool = False,
        allow_browser_retry: bool = False,
        allow_browser_fallback: bool = True,
    ) -> SearchResponse:
        cleaned_query = query.strip()
        if not cleaned_query:
            return SearchResponse(query=query, count=0, results=[])

        brand_match = None if criteria.brand else self._normalizer.match_brand_in_text(cleaned_query)
        effective_criteria = self._effective_criteria(criteria, brand_match)
        collect_limit = self._collect_limit(effective_criteria)
        collect_queries = self._collect_queries(cleaned_query, effective_criteria, brand_match)
        cache_key = f"{'|'.join(query.casefold() for query in collect_queries)}:{collect_limit}"
        collected = await self._cache.get(cache_key)
        if collected is None:
            collected = await self._collect(
                collect_queries,
                collect_limit,
                allow_browser_fallback=allow_browser_fallback,
            )
            await self._cache.set(cache_key, collected)

        results, top_score = self._build_results(
            collected.records,
            cleaned_query,
            effective_criteria,
            brand_match,
        )
        if require_relevant and allow_browser_retry and top_score <= 0 and collected.records:
            browser_collected = await self._collect_browser(collect_queries, collect_limit)
            browser_results, browser_top_score = self._build_results(
                browser_collected.records,
                cleaned_query,
                effective_criteria,
                brand_match,
            )
            if browser_top_score > 0:
                return SearchResponse(
                    query=cleaned_query,
                    count=len(browser_results),
                    results=browser_results,
                    source_errors=[],
                )

        results = [] if require_relevant and top_score <= 0 else results
        return SearchResponse(
            query=cleaned_query,
            count=len(results),
            results=results,
            source_errors=collected.errors,
        )

    def _build_results(
        self,
        records: list[ProductSourceRecord],
        cleaned_query: str,
        criteria: SearchCriteria,
        brand_match: BrandMatch | None,
    ) -> tuple[list[ProductSearchResult], int]:
        normalized = [self._normalizer.normalize(record) for record in records]
        complete_results = self._only_core_complete(normalized)
        filtered = self._apply_filters(complete_results, criteria)
        relevant, top_score = self._rank_query_matches(
            filtered,
            self._product_query(cleaned_query, brand_match),
        )
        return relevant[: criteria.limit], top_score

    @staticmethod
    def _split_batch_queries(query: str) -> list[str]:
        queries: list[str] = []
        seen: set[str] = set()
        for raw_line in query.splitlines():
            line = re.sub(r"^\s*(?:[-*•]+|\d+[.)])\s*", "", raw_line).strip()
            text = clean_text(line)
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            queries.append(text)
        return queries or [query.strip()]

    async def _collect(
        self,
        queries: list[str],
        limit: int,
        *,
        allow_browser_fallback: bool = True,
    ) -> _CollectedResult:
        errors: list[str] = []
        records: list[ProductSourceRecord] = []
        has_successful_source = False
        fast_collectors = [
            collector for collector in self._collectors if collector.name != "oliveyoung:browser"
        ]

        for query in queries:
            for collector in fast_collectors:
                try:
                    source_records = await collector.search(query, limit)
                except SourceUnavailableError as exc:
                    errors.append(f"{collector.name}: {exc}")
                    continue
                has_successful_source = True
                if source_records:
                    records = self._dedupe_records([*records, *source_records])

        if records:
            return _CollectedResult(records=records[: max(limit, 1) * 2], errors=[])

        if allow_browser_fallback:
            browser_collected = await self._collect_browser(queries, limit)
            errors.extend(browser_collected.errors)
            if browser_collected.records:
                has_successful_source = True
                records = self._dedupe_records([*records, *browser_collected.records])

        if records:
            return _CollectedResult(records=records[: max(limit, 1) * 2], errors=[])
        if has_successful_source:
            return _CollectedResult(records=[], errors=[])
        return _CollectedResult(records=[], errors=errors)

    async def _collect_browser(self, queries: list[str], limit: int) -> _CollectedResult:
        errors: list[str] = []
        records: list[ProductSourceRecord] = []
        browser_collectors = [
            collector for collector in self._collectors if collector.name == "oliveyoung:browser"
        ]
        for collector in browser_collectors:
            try:
                source_records = await collector.search(queries[0], limit)
            except SourceUnavailableError as exc:
                errors.append(f"{collector.name}: {exc}")
                continue
            if source_records:
                records = self._dedupe_records([*records, *source_records])
        return _CollectedResult(records=records, errors=errors)

    @classmethod
    def _collect_queries(
        cls,
        query: str,
        criteria: SearchCriteria,
        brand_match: BrandMatch | None = None,
    ) -> list[str]:
        brand = clean_text(criteria.brand)
        brand_search_term = clean_text(brand_match.matched_alias if brand_match else brand)
        product_query = cls._product_query(query, brand_match)
        candidates = []
        if brand_search_term:
            candidates.append(f"{brand_search_term} {product_query}")
            compact_product_query = cls._compact_product_query(product_query)
            if compact_product_query and compact_product_query != product_query:
                candidates.append(f"{brand_search_term} {compact_product_query}")
        candidates.append(query)
        candidates.append(product_query)
        compact_product_query = cls._compact_product_query(product_query)
        if compact_product_query and compact_product_query != product_query:
            candidates.append(compact_product_query)
        if brand_search_term:
            candidates.append(brand_search_term)

        queries: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            text = clean_text(candidate)
            key = cls._key(text)
            if not text or not key or key in seen:
                continue
            seen.add(key)
            queries.append(text)
        return queries or [query]

    @staticmethod
    def _effective_criteria(
        criteria: SearchCriteria,
        brand_match: BrandMatch | None,
    ) -> SearchCriteria:
        if criteria.brand or brand_match is None:
            return criteria
        return replace(criteria, brand=brand_match.official_en)

    @staticmethod
    def _query_without_brand(query: str, matched_alias: str) -> str:
        stripped = re.sub(re.escape(matched_alias), " ", query, count=1, flags=re.IGNORECASE)
        return clean_text(stripped) or query

    @classmethod
    def _product_query(cls, query: str, brand_match: BrandMatch | None) -> str:
        if brand_match is None:
            return query
        return cls._query_without_brand(query, brand_match.matched_alias)

    @classmethod
    def _dedupe_records(cls, records: list[ProductSourceRecord]) -> list[ProductSourceRecord]:
        deduped: list[ProductSourceRecord] = []
        seen: set[str] = set()
        for record in records:
            key = cls._record_key(record)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(record)
        return deduped

    @classmethod
    def _record_key(cls, record: ProductSourceRecord) -> str:
        brand_key = cls._key(record.source_brand_name)
        name_key = cls._key(record.product_name_ko)
        if brand_key and name_key:
            return f"product:{brand_key}:{name_key}"
        if record.source_product_id:
            return f"{record.source}:{record.source_product_id}"
        return f"{record.source}:{cls._key(record.source_url)}"

    @staticmethod
    def _only_core_complete(results: list[ProductSearchResult]) -> list[ProductSearchResult]:
        return [
            product
            for product in results
            if product.brand_en and product.product_name_ko and product.price is not None
        ]

    @classmethod
    def _rank_query_matches(
        cls,
        results: list[ProductSearchResult],
        product_query: str,
    ) -> tuple[list[ProductSearchResult], int]:
        query_key = cls._key(product_query)
        if not query_key:
            return results, 0
        scored = [
            (cls._match_score(product, product_query, index), product)
            for index, product in enumerate(results)
        ]
        ranked = sorted(scored, key=lambda item: item[0], reverse=True)
        if not ranked or ranked[0][0][0] <= 0:
            return results, 0
        return [product for score, product in ranked if score[0] > 0], ranked[0][0][0]

    @classmethod
    def _match_score(
        cls,
        product: ProductSearchResult,
        product_query: str,
        index: int,
    ) -> tuple[int, int]:
        query_key = cls._key(product_query)
        haystack_key = cls._key(" ".join(
            value
            for value in [product.brand_en, product.product_name_ko, product.shade]
            if value
        ))
        if not query_key or not haystack_key:
            return (0, -index)

        category_tokens = cls._category_tokens(product_query)
        if category_tokens and not all(token in haystack_key for token in category_tokens):
            return (0, -index)
        distinctive_tokens = cls._distinctive_tokens(product_query)
        if distinctive_tokens and not any(token in haystack_key for token in distinctive_tokens):
            return (0, -index)

        score = 100 if query_key in haystack_key else 0
        for token in cls._tokens(product_query):
            token_key = cls._key(token)
            if len(token_key) >= 2 and token_key in haystack_key:
                score += 10
        return (score, -index)

    @staticmethod
    def _tokens(value: str) -> list[str]:
        text = clean_text(value)
        if text is None:
            return []
        return re.findall(r"[0-9A-Za-z가-힣]+", text)

    @classmethod
    def _category_tokens(cls, value: str) -> list[str]:
        category_words = (
            "패드",
            "컨실러",
            "섀딩",
            "브러시",
            "팔레트",
            "틴트",
            "라이너",
            "밤",
            "크림",
            "스프레이",
            "토너",
            "세럼",
        )
        key = cls._key(value)
        return [cls._key(word) for word in category_words if cls._key(word) in key]

    @classmethod
    def _distinctive_tokens(cls, value: str) -> list[str]:
        category_tokens = set(cls._category_tokens(value))
        tokens: list[str] = []
        for token in cls._tokens(value):
            token_key = cls._key(token)
            if (
                len(token_key) < 2
                or token_key in category_tokens
                or token_key.isdigit()
                or cls._is_color_token(token_key)
            ):
                continue
            tokens.append(token_key)
        return tokens

    @classmethod
    def _compact_product_query(cls, value: str) -> str:
        category_tokens = set(cls._category_tokens(value))
        keep: list[str] = []
        for token in cls._tokens(value):
            token_key = cls._key(token)
            if (
                len(token_key) < 2
                or cls._is_color_token(token_key)
                or token_key in {"호", "번", "no", "m"}
            ):
                continue
            if token_key in category_tokens or not token_key.isdigit():
                keep.append(token)
        return clean_text(" ".join(keep)) or ""

    @staticmethod
    def _is_color_token(token_key: str) -> bool:
        color_words = (
            "베이지",
            "브라운",
            "초코",
            "그레이",
            "쿨",
            "웜",
            "피치",
            "핑크",
            "로즈",
            "레드",
            "코랄",
            "오렌지",
            "스톤",
            "클리어",
            "누드",
            "블랙",
            "화이트",
            "gray",
            "grey",
            "brown",
            "pink",
            "peach",
        )
        return any(word in token_key for word in color_words)

    @staticmethod
    def _collect_limit(criteria: SearchCriteria) -> int:
        has_filters = any(
            [
                criteria.brand,
                criteria.min_price is not None,
                criteria.max_price is not None,
                criteria.has_shade is not None,
            ]
        )
        if not has_filters:
            return criteria.limit
        return max(criteria.limit, 48)

    async def close(self) -> None:
        for collector in self._collectors:
            close = getattr(collector, "close", None)
            if close is None:
                continue
            result = close()
            if inspect.isawaitable(result):
                await result
        normalizer_close = getattr(self._normalizer, "close", None)
        if normalizer_close is not None:
            result = normalizer_close()
            if inspect.isawaitable(result):
                await result

    def _apply_filters(
        self,
        results: list[ProductSearchResult],
        criteria: SearchCriteria,
    ) -> list[ProductSearchResult]:
        filtered = results
        if criteria.brand:
            raw_needle = criteria.brand.casefold()
            normalized_brand = self._normalizer.normalize_brand_filter(criteria.brand)
            normalized_needle = normalized_brand.casefold() if normalized_brand else None
            filtered = [
                product
                for product in filtered
                if self._matches_brand_filter(product, raw_needle, normalized_needle)
            ]
        if criteria.min_price is not None:
            filtered = [
                product
                for product in filtered
                if product.price is not None
                and (product.currency or "KRW") == "KRW"
                and product.price >= criteria.min_price
            ]
        if criteria.max_price is not None:
            filtered = [
                product
                for product in filtered
                if product.price is not None
                and (product.currency or "KRW") == "KRW"
                and product.price <= criteria.max_price
            ]
        if criteria.has_shade is not None:
            filtered = [
                product
                for product in filtered
                if bool(product.shade) is criteria.has_shade
            ]
        return filtered

    @classmethod
    def _matches_brand_filter(
        cls,
        product: ProductSearchResult,
        raw_needle: str,
        normalized_needle: str | None,
    ) -> bool:
        brand = product.brand_en.casefold() if product.brand_en else ""
        name = product.product_name_ko.casefold() if product.product_name_ko else ""
        brand_key = cls._key(product.brand_en)
        name_key = cls._key(product.product_name_ko)
        raw_key = cls._key(raw_needle)
        normalized_key = cls._key(normalized_needle)
        return bool(
            (normalized_needle and normalized_needle in brand)
            or (normalized_key and normalized_key in brand_key)
            or raw_needle in brand
            or (raw_key and raw_key in brand_key)
            or raw_needle in name
            or (raw_key and raw_key in name_key)
        )

    @staticmethod
    def _key(value: str | None) -> str:
        text = clean_text(value)
        if text is None:
            return ""
        text = text.casefold()
        text = (
            text.replace("브러쉬", "브러시")
            .replace("brush", "브러시")
            .replace("eyeliner", "아이라이너")
            .replace("eye shadow", "아이섀도")
            .replace("glowy", "글로이")
            .replace("tear", "티어")
            .replace("gray", "그레이")
            .replace("grey", "그레이")
            .replace("쉐딩", "섀딩")
            .replace("셰딩", "섀딩")
            .replace("비타민씨", "비타")
            .replace("여백살롱", "여백카롱")
            .replace("및서재", "밑서재")
            .replace("플로팅", "플러팅")
            .replace("이즈핏", "이지핏")
            .replace("땡큐요엠핑크", "요염핑")
        )
        return re.sub(r"[\s\-_./|+&'():\[\],]+", "", text)

    @staticmethod
    def _dedupe_errors(errors: Iterable[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for error in errors:
            if error in seen:
                continue
            seen.add(error)
            deduped.append(error)
        return deduped
