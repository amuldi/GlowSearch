from __future__ import annotations

import inspect
import re
import asyncio
from time import perf_counter
from collections.abc import Iterable
from dataclasses import dataclass, replace

from app.cache.ttl import AsyncTTLCache
from app.data_collector.base import ProductCollector, SearchCriteria, SourceUnavailableError
from app.indexing.agents import ProductIngestionAgent, SourceDiscoveryAgent
from app.indexing.store import ProductIndexStore
from app.models.product import ProductSearchResult, ProductSourceRecord, SearchResponse
from app.normalizer.brand import BrandMatch
from app.normalizer.product import ProductNormalizer
from app.normalizer.text import clean_text
from app.observability.metrics import SearchMetrics, Timer
from app.search.synonyms import related_query_expansions, search_key
from app.service.source_policy import SourcePolicy


@dataclass
class _CollectedResult:
    records: list[ProductSourceRecord]
    errors: list[str]
    has_official_records: bool = False


class SearchService:
    _BATCH_CONCURRENCY = 4
    _INDEX_READ_TIMEOUT_SECONDS = 0.35

    def __init__(
        self,
        collectors: list[ProductCollector],
        normalizer: ProductNormalizer,
        cache: AsyncTTLCache[_CollectedResult],
        *,
        product_index: ProductIndexStore | None = None,
        ingestion_agent: ProductIngestionAgent | None = None,
        source_discovery_agent: SourceDiscoveryAgent | None = None,
        index_min_results: int = 8,
        index_background_refresh_enabled: bool = True,
        index_warmup_limit: int = 48,
        index_warmup_concurrency: int = 2,
        prefer_live_official_results: bool = False,
        preserve_official_order: bool = True,
        source_time_budget_seconds: float = 3.0,
        live_collect_deadline_seconds: float = 3.2,
        live_first_result_grace_seconds: float = 0.8,
        background_collect_deadline_seconds: float = 18.0,
        source_time_budgets: dict[str, float] | None = None,
        allowed_result_source_prefixes: tuple[str, ...] | None = None,
        source_policy: SourcePolicy | None = None,
        metrics: SearchMetrics | None = None,
    ):
        self._collectors = collectors
        self._normalizer = normalizer
        self._cache = cache
        self._product_index = product_index
        self._ingestion_agent = ingestion_agent
        self._source_discovery_agent = source_discovery_agent
        self._index_min_results = max(index_min_results, 1)
        self._index_background_refresh_enabled = index_background_refresh_enabled
        self._index_warmup_limit = max(index_warmup_limit, 1)
        self._index_warmup_concurrency = max(index_warmup_concurrency, 1)
        self._prefer_live_official_results = prefer_live_official_results
        self._preserve_official_order = preserve_official_order
        self._source_time_budget_seconds = source_time_budget_seconds
        self._live_collect_deadline_seconds = live_collect_deadline_seconds
        self._live_first_result_grace_seconds = live_first_result_grace_seconds
        self._background_collect_deadline_seconds = background_collect_deadline_seconds
        self._source_time_budgets = source_time_budgets or {}
        self._source_policy = source_policy or SourcePolicy(
            allowed_prefixes=allowed_result_source_prefixes
        )
        self._metrics = metrics or SearchMetrics()
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._last_index_error: str | None = None

    async def search(self, query: str, criteria: SearchCriteria) -> SearchResponse:
        started_at = perf_counter()
        response: SearchResponse | None = None
        failed = False
        try:
            response = await self._search(query, criteria)
            return response
        except Exception:
            failed = True
            raise
        finally:
            self._metrics.record_search(
                elapsed_ms=(perf_counter() - started_at) * 1000,
                result_count=response.count if response is not None else 0,
                failed=failed,
            )

    async def _search(self, query: str, criteria: SearchCriteria) -> SearchResponse:
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
        product_query = self._product_query(cleaned_query, brand_match)
        collect_limit = self._collect_limit(effective_criteria, product_query)
        collect_queries = self._collect_queries(cleaned_query, effective_criteria, brand_match)
        has_related_expansions = bool(self._related_query_expansions(product_query or cleaned_query))
        is_broad_single_query = brand_match is None and self._is_single_related_query(
            product_query or cleaned_query
        )
        cache_key = f"{'|'.join(query.casefold() for query in collect_queries)}:{collect_limit}"
        fallback_results: list[ProductSearchResult] = []

        cached_collected = None if self._prefer_live_official_results else await self._cache.get(cache_key)
        if not self._prefer_live_official_results:
            self._metrics.record_cache_lookup(cached_collected is not None)
        if cached_collected is not None:
            cached_results, cached_top_score = self._build_results(
                cached_collected.records,
                cleaned_query,
                effective_criteria,
                brand_match,
                preserve_order=(
                    (cached_collected.has_official_records and self._preserve_official_order)
                    or self._prefer_live_official_results
                ),
            )
            cached_has_enough_results = (
                not (has_related_expansions or is_broad_single_query)
                or len(cached_results) >= self._broad_related_return_threshold(criteria.limit)
                or not cached_collected.records
            )
            if (
                cached_top_score > 0
                or cached_collected.has_official_records
                or not cached_collected.records
            ) and cached_has_enough_results:
                self._schedule_index_refresh(cleaned_query, collect_queries, collect_limit)
                return SearchResponse(
                    query=cleaned_query,
                    count=len(cached_results),
                    results=[] if require_relevant and cached_top_score <= 0 else cached_results,
                    source_errors=cached_collected.errors,
                )
            if cached_top_score > 0 or (
                cached_collected.has_official_records and cached_results
            ):
                fallback_results = cached_results

        try:
            indexed_collected = await asyncio.wait_for(
                self._collect_index([cleaned_query, *collect_queries], collect_limit),
                timeout=self._INDEX_READ_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            indexed_collected = _CollectedResult(records=[], errors=[])
        indexed_results, indexed_top_score = self._build_results(
            indexed_collected.records,
            cleaned_query,
            effective_criteria,
            brand_match,
            preserve_order=True,
        )
        self._metrics.record_index_lookup(bool(indexed_collected.records))
        if (
            indexed_top_score > 0
            or (indexed_collected.has_official_records and indexed_results)
        ) and len(indexed_results) > len(fallback_results):
            fallback_results = indexed_results
        index_threshold = min(criteria.limit, self._index_min_results)
        index_has_enough_results = (
            len(indexed_results) >= self._broad_related_return_threshold(criteria.limit)
            if has_related_expansions or is_broad_single_query
            else len(indexed_results) >= index_threshold or len(indexed_results) > 0
        )
        if (
            not self._prefer_live_official_results
            and (indexed_top_score > 0 or indexed_collected.has_official_records)
            and index_has_enough_results
            and not require_relevant
        ):
            await self._cache.set(cache_key, indexed_collected)
            self._schedule_index_refresh(cleaned_query, collect_queries, collect_limit)
            return SearchResponse(
                query=cleaned_query,
                count=len(indexed_results),
                results=indexed_results,
                source_errors=[],
            )

        collected = None
        collected_from_live = False
        if collected is None:
            if self._can_use_verified_shortcut(cleaned_query, require_relevant):
                verified_collected = await self._collect_verified_cache(collect_queries, collect_limit)
                verified_results, verified_top_score = self._build_results(
                    verified_collected.records,
                    cleaned_query,
                    effective_criteria,
                    brand_match,
                    preserve_order=True,
                )
                if verified_top_score > 0:
                    if not self._prefer_live_official_results:
                        await self._cache.set(cache_key, verified_collected)
                    return SearchResponse(
                        query=cleaned_query,
                        count=len(verified_results),
                        results=verified_results,
                        source_errors=[],
                    )

            collected = await self._collect(
                collect_queries,
                collect_limit,
                allow_browser_fallback=allow_browser_fallback,
            )
            collected_from_live = True
            if not self._prefer_live_official_results:
                await self._cache.set(cache_key, collected)

        if collected_from_live:
            self._schedule_ingest([cleaned_query, *collect_queries], collected.records)

        result_records = collected.records
        if indexed_collected.records and not collected.has_official_records:
            result_records = self._dedupe_records([*result_records, *indexed_collected.records])

        results, top_score = self._build_results(
            result_records,
            cleaned_query,
            effective_criteria,
            brand_match,
            preserve_order=(
                (collected.has_official_records and self._preserve_official_order)
                or self._prefer_live_official_results
            ),
        )
        if top_score <= 0 and fallback_results and not require_relevant:
            return SearchResponse(
                query=cleaned_query,
                count=len(fallback_results[: criteria.limit]),
                results=fallback_results[: criteria.limit],
                source_errors=collected.errors,
            )
        if require_relevant and allow_browser_retry and top_score <= 0 and collected.records:
            browser_collected = await self._collect_browser(collect_queries, collect_limit)
            browser_results, browser_top_score = self._build_results(
                browser_collected.records,
                cleaned_query,
                effective_criteria,
                brand_match,
                preserve_order=browser_collected.has_official_records,
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

    async def _collect_index(self, queries: list[str], limit: int) -> _CollectedResult:
        if self._product_index is None:
            return _CollectedResult(records=[], errors=[])
        records: list[ProductSourceRecord] = []
        seen_queries: set[str] = set()
        for query in queries:
            text = clean_text(query)
            key = self._key(text)
            if not text or not key or key in seen_queries:
                continue
            seen_queries.add(key)
            index_records = await self._product_index.search(text, limit)
            if index_records:
                records = self._dedupe_records([*records, *index_records])
            if len(records) >= limit:
                break
        return _CollectedResult(
            records=records[:limit],
            errors=[],
            has_official_records=self._has_oliveyoung_records(records),
        )

    def _build_results(
        self,
        records: list[ProductSourceRecord],
        cleaned_query: str,
        criteria: SearchCriteria,
        brand_match: BrandMatch | None,
        *,
        preserve_order: bool = False,
    ) -> tuple[list[ProductSearchResult], int]:
        normalized = self._dedupe_results(
            [self._with_source_metadata(self._normalizer.normalize(record)) for record in records]
        )
        normalized = self._filter_allowed_sources(normalized)
        complete_results = self._only_core_complete(normalized)
        filtered = self._apply_filters(complete_results, criteria)
        product_query = self._product_query(cleaned_query, brand_match)
        if preserve_order:
            relevant, top_score = self._query_matches_in_source_order(filtered, product_query)
        else:
            relevant, top_score = self._rank_query_matches(filtered, product_query)
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
        deadline_seconds: float | None = None,
    ) -> _CollectedResult:
        errors: list[str] = []
        official_primary_records: list[ProductSourceRecord] = []
        official_fallback_records: list[ProductSourceRecord] = []
        supplemental_records: list[ProductSourceRecord] = []
        has_successful_source = False
        fast_collectors = [
            collector for collector in self._collectors if collector.name != "oliveyoung:browser"
        ]

        primary_query = queries[0] if queries else ""
        jobs = [
            (collector, query)
            for query in queries
            for collector in fast_collectors
        ]
        tasks: dict[
            asyncio.Task[tuple[list[ProductSourceRecord], str | None, bool]],
            tuple[ProductCollector, str, int],
        ] = {
            asyncio.create_task(self._collect_from_source(collector, query, limit)): (
                collector,
                query,
                job_index,
            )
            for job_index, (collector, query) in enumerate(jobs)
        }
        pending = set(tasks)
        collection_deadline_seconds = (
            self._live_collect_deadline_seconds
            if deadline_seconds is None
            else deadline_seconds
        )
        deadline_at = perf_counter() + max(collection_deadline_seconds, 0.1)
        first_result_at: float | None = None
        try:
            while pending:
                now = perf_counter()
                remaining_seconds = deadline_at - now
                if first_result_at is not None:
                    grace_remaining_seconds = (
                        first_result_at + max(self._live_first_result_grace_seconds, 0) - now
                    )
                    if grace_remaining_seconds <= 0:
                        self._record_pending_source_timeouts(pending, tasks)
                        break
                    remaining_seconds = min(remaining_seconds, grace_remaining_seconds)
                if remaining_seconds <= 0:
                    self._record_pending_source_timeouts(pending, tasks)
                    break
                done, pending = await asyncio.wait(
                    pending,
                    timeout=remaining_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    self._record_pending_source_timeouts(pending, tasks)
                    break
                for task in sorted(
                    done,
                    key=lambda task: (
                        self._collector_result_priority(
                            tasks[task][0],
                            tasks[task][1],
                            primary_query,
                        ),
                        tasks[task][2],
                    ),
                ):
                    collector, query, _job_index = tasks[task]
                    source_records, error, source_succeeded = task.result()
                    has_successful_source = has_successful_source or source_succeeded
                    if error:
                        errors.append(error)
                    if source_records:
                        first_result_at = first_result_at or perf_counter()
                        if (
                            self._is_oliveyoung_collector(collector)
                            and query == primary_query
                        ):
                            ordered_records = (
                                [*source_records, *official_primary_records]
                                if collector.name == "oliveyoung"
                                else [*official_primary_records, *source_records]
                            )
                            official_primary_records = self._dedupe_records(
                                ordered_records
                            )
                            if self._should_wait_for_primary_html_result(
                                collector,
                                query,
                                primary_query,
                                len(official_primary_records),
                                limit,
                                pending,
                                tasks,
                            ):
                                continue
                            return _CollectedResult(
                                records=official_primary_records[: max(limit, 1) * 2],
                                errors=[],
                                has_official_records=True,
                            )
                        if self._is_oliveyoung_collector(collector):
                            official_fallback_records = self._dedupe_records(
                                [*official_fallback_records, *source_records]
                            )
                            broad_records = self._dedupe_records(
                                [*official_primary_records, *official_fallback_records]
                            )
                            if (
                                self._is_single_related_query(primary_query)
                                and len(broad_records)
                                >= self._broad_related_return_threshold(limit)
                                and not self._has_pending_primary_oliveyoung_task(
                                    pending,
                                    tasks,
                                    primary_query,
                                )
                            ):
                                return _CollectedResult(
                                    records=broad_records[: max(limit, 1) * 2],
                                    errors=[],
                                    has_official_records=True,
                                )
                        else:
                            supplemental_records = self._dedupe_records(
                                [*supplemental_records, *source_records]
                            )
        finally:
            for task in pending:
                task.cancel()
                task.add_done_callback(self._consume_cancelled_task)

        if official_primary_records:
            records = self._dedupe_records(
                [*official_primary_records, *official_fallback_records, *supplemental_records]
            )
            return _CollectedResult(
                records=records[: max(limit, 1) * 2],
                errors=[],
                has_official_records=True,
            )

        records = self._dedupe_records([*official_fallback_records, *supplemental_records])
        has_browser_records = False

        if allow_browser_fallback and self._needs_browser_supplement(records, limit):
            browser_collected = await self._collect_browser(queries, limit)
            errors.extend(browser_collected.errors)
            if browser_collected.records:
                has_successful_source = True
                has_browser_records = True
                records = self._dedupe_records([*browser_collected.records, *records])

        if records:
            return _CollectedResult(
                records=records[: max(limit, 1) * 2],
                errors=[],
                has_official_records=bool(official_fallback_records or has_browser_records),
            )
        if has_successful_source:
            return _CollectedResult(records=[], errors=[])
        return _CollectedResult(records=[], errors=self._dedupe_errors(errors))

    async def _collect_from_source(
        self,
        collector: ProductCollector,
        query: str,
        limit: int,
    ) -> tuple[list[ProductSourceRecord], str | None, bool]:
        try:
            timer = Timer.start()
            source_records = await asyncio.wait_for(
                collector.search(query, limit),
                timeout=self._collector_timeout(collector),
            )
        except TimeoutError:
            error = f"{collector.name}: request timed out"
            self._metrics.record_source_failure(collector.name, error, timeout=True)
            return [], error, False
        except SourceUnavailableError as exc:
            error = f"{collector.name}: {exc}"
            self._metrics.record_source_failure(collector.name, error)
            return [], error, False
        self._metrics.record_source_success(
            collector.name,
            elapsed_ms=timer.elapsed_ms(),
            result_count=len(source_records),
        )
        return source_records, None, True

    def _collector_timeout(self, collector: ProductCollector) -> float:
        return self._source_time_budgets.get(collector.name, self._source_time_budget_seconds)

    def _record_pending_source_timeouts(
        self,
        pending: set[asyncio.Task[tuple[list[ProductSourceRecord], str | None, bool]]],
        tasks: dict[
            asyncio.Task[tuple[list[ProductSourceRecord], str | None, bool]],
            tuple[ProductCollector, str, int],
        ],
    ) -> None:
        seen_collectors: set[str] = set()
        for task in pending:
            collector, _query, _index = tasks[task]
            if collector.name in seen_collectors:
                continue
            seen_collectors.add(collector.name)
            self._metrics.record_source_failure(
                collector.name,
                f"{collector.name}: live collection deadline exceeded",
                timeout=True,
            )

    @staticmethod
    def _consume_cancelled_task(task: asyncio.Task[object]) -> None:
        try:
            task.exception()
        except (asyncio.CancelledError, Exception):
            return

    @staticmethod
    def _is_oliveyoung_collector(collector: ProductCollector) -> bool:
        return collector.name == "oliveyoung" or collector.name.startswith("oliveyoung:")

    @staticmethod
    def _has_oliveyoung_records(records: list[ProductSourceRecord]) -> bool:
        return any(
            record.source == "oliveyoung" or record.source.startswith("oliveyoung:")
            for record in records
        )

    @classmethod
    def _should_wait_for_primary_html_result(
        cls,
        collector: ProductCollector,
        query: str,
        primary_query: str,
        record_count: int,
        limit: int,
        pending: set[asyncio.Task[tuple[list[ProductSourceRecord], str | None, bool]]],
        tasks: dict[
            asyncio.Task[tuple[list[ProductSourceRecord], str | None, bool]],
            tuple[ProductCollector, str, int],
        ],
    ) -> bool:
        if (
            collector.name == "oliveyoung"
            or not cls._is_oliveyoung_collector(collector)
            or query != primary_query
            or record_count >= limit
            or not cls._is_single_related_query(query)
        ):
            return False
        if any(task_query != primary_query for _collector, task_query, _index in tasks.values()):
            return True
        return any(
            tasks[task][0].name == "oliveyoung" and tasks[task][1] == primary_query
            for task in pending
        )

    @classmethod
    def _has_pending_primary_oliveyoung_task(
        cls,
        pending: set[asyncio.Task[tuple[list[ProductSourceRecord], str | None, bool]]],
        tasks: dict[
            asyncio.Task[tuple[list[ProductSourceRecord], str | None, bool]],
            tuple[ProductCollector, str, int],
        ],
        primary_query: str,
    ) -> bool:
        return any(
            task in pending
            and task_query == primary_query
            and cls._is_oliveyoung_collector(collector)
            for task, (collector, task_query, _index) in tasks.items()
        )

    @classmethod
    def _is_single_related_query(cls, query: str) -> bool:
        return len(cls._tokens(query)) == 1 and bool(cls._key(query))

    @staticmethod
    def _broad_related_return_threshold(limit: int) -> int:
        return max(1, min(limit, 24))

    @classmethod
    def _collector_result_priority(
        cls,
        collector: ProductCollector,
        query: str,
        primary_query: str,
    ) -> int:
        is_primary_query = query == primary_query
        if is_primary_query and collector.name == "oliveyoung":
            return 0
        if is_primary_query and cls._is_oliveyoung_collector(collector):
            return 1
        if collector.name == "oliveyoung":
            return 2
        if cls._is_oliveyoung_collector(collector):
            return 3
        return 4

    async def _collect_verified_cache(self, queries: list[str], limit: int) -> _CollectedResult:
        records: list[ProductSourceRecord] = []
        verified_collectors = [
            collector for collector in self._collectors if collector.name == "oliveyoung:verified-cache"
        ]
        for query in queries:
            for collector in verified_collectors:
                try:
                    source_records = await collector.search(query, limit)
                except SourceUnavailableError:
                    continue
                if source_records:
                    records = self._dedupe_records([*records, *source_records])
        return _CollectedResult(records=records[: max(limit, 1) * 2], errors=[])

    async def _collect_browser(self, queries: list[str], limit: int) -> _CollectedResult:
        errors: list[str] = []
        records: list[ProductSourceRecord] = []
        browser_collectors = [
            collector for collector in self._collectors if collector.name == "oliveyoung:browser"
        ]
        for query in queries:
            for collector in browser_collectors:
                source_records, error, _source_succeeded = await self._collect_from_source(
                    collector,
                    query,
                    limit,
                )
                if error:
                    errors.append(error)
                if source_records:
                    records = self._dedupe_records([*records, *source_records])
            if len(records) >= limit:
                break
        return _CollectedResult(
            records=records,
            errors=errors,
            has_official_records=bool(records),
        )

    def _schedule_ingest(self, queries: Iterable[str], records: list[ProductSourceRecord]) -> None:
        if self._ingestion_agent is None or not records:
            return
        task = asyncio.create_task(self._ingest_safely(tuple(queries), records))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _schedule_index_refresh(
        self,
        original_query: str,
        collect_queries: list[str],
        limit: int,
    ) -> None:
        if not self._index_background_refresh_enabled or self._ingestion_agent is None:
            return
        task = asyncio.create_task(
            self._refresh_index_safely(original_query, tuple(collect_queries), limit)
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _ingest_safely(
        self,
        queries: Iterable[str],
        records: list[ProductSourceRecord],
    ) -> None:
        if self._ingestion_agent is None:
            return
        try:
            await self._ingestion_agent.ingest_search_results(queries, records)
            self._last_index_error = None
        except Exception as exc:
            self._last_index_error = f"{type(exc).__name__}: {exc}"
            self._metrics.record_background_index_error(self._last_index_error)
            return

    async def _refresh_index_safely(
        self,
        original_query: str,
        collect_queries: Iterable[str],
        limit: int,
    ) -> None:
        if self._ingestion_agent is None:
            return
        try:
            queries = [query for query in collect_queries if clean_text(query)]
            collected = await self._collect(
                queries,
                limit,
                allow_browser_fallback=False,
                deadline_seconds=self._background_collect_deadline_seconds,
            )
            await self._ingestion_agent.ingest_search_results(
                [original_query, *queries],
                collected.records,
            )
            self._last_index_error = None
        except Exception as exc:
            self._last_index_error = f"{type(exc).__name__}: {exc}"
            self._metrics.record_background_index_error(self._last_index_error)
            return

    async def warm_index(
        self,
        queries: Iterable[str] | None = None,
        *,
        limit: int | None = None,
    ) -> int:
        seeds = self._warm_seed_queries(queries)
        if not seeds:
            return 0
        await self._warm_index_queries(seeds, limit or self._index_warmup_limit)
        return len(seeds)

    def schedule_warm_index(
        self,
        queries: Iterable[str] | None = None,
        *,
        limit: int | None = None,
    ) -> int:
        seeds = self._warm_seed_queries(queries)
        if not seeds:
            return 0
        task = asyncio.create_task(
            self._warm_index_queries_safely(seeds, limit or self._index_warmup_limit)
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return len(seeds)

    async def index_stats(self) -> dict[str, int | str | None]:
        if self._product_index is None:
            return {
                "product_count": 0,
                "query_count": 0,
                "last_refreshed_at": None,
                "background_task_count": len(self._background_tasks),
                "last_index_error": self._last_index_error,
            }
        stats = await self._product_index.stats()
        stats["background_task_count"] = len(self._background_tasks)
        stats["last_index_error"] = self._last_index_error
        return stats

    def diagnostics(self) -> dict[str, object]:
        return {
            "metrics": self._metrics.snapshot(),
            "source_policy": self._source_policy.snapshot(),
            "background_task_count": len(self._background_tasks),
            "last_index_error": self._last_index_error,
        }

    def _warm_seed_queries(self, queries: Iterable[str] | None = None) -> list[str]:
        if self._source_discovery_agent is None or self._ingestion_agent is None:
            return []
        if queries is None:
            return self._source_discovery_agent.seed_queries()
        return SourceDiscoveryAgent._dedupe(queries)

    async def _warm_index_queries_safely(self, seeds: list[str], limit: int) -> None:
        try:
            await self._warm_index_queries(seeds, limit)
            self._last_index_error = None
        except Exception as exc:
            self._last_index_error = f"{type(exc).__name__}: {exc}"
            return

    async def _warm_index_queries(self, seeds: list[str], limit: int) -> None:
        if self._ingestion_agent is None:
            return
        warm_limit = max(limit, 1)
        semaphore = asyncio.Semaphore(self._index_warmup_concurrency)

        async def warm_query(query: str) -> None:
            async with semaphore:
                collected = await self._collect(
                    [query],
                    warm_limit,
                    allow_browser_fallback=False,
                    deadline_seconds=self._background_collect_deadline_seconds,
                )
                await self._ingestion_agent.ingest_search_results([query], collected.records)

        await asyncio.gather(*(warm_query(query) for query in seeds))

    async def drain_background_tasks(self) -> None:
        if not self._background_tasks:
            return
        await asyncio.gather(*list(self._background_tasks), return_exceptions=True)

    @staticmethod
    def _needs_browser_supplement(records: list[ProductSourceRecord], _limit: int) -> bool:
        return not records

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
            if product_query:
                candidates.append(f"{brand_search_term} {product_query}")
                compact_product_query = cls._compact_product_query(product_query)
                if compact_product_query and compact_product_query != product_query:
                    candidates.append(f"{brand_search_term} {compact_product_query}")
            else:
                candidates.append(brand_search_term)
        if brand_match is None:
            candidates.append(query)
        if product_query:
            candidates.append(product_query)
        compact_product_query = cls._compact_product_query(product_query)
        if compact_product_query and compact_product_query != product_query:
            candidates.append(compact_product_query)
        candidates.extend(cls._related_query_expansions(product_query or query))
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

    @classmethod
    def _related_query_expansions(cls, value: str) -> tuple[str, ...]:
        return related_query_expansions(value)

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
        return clean_text(stripped) or ""

    @classmethod
    def _product_query(cls, query: str, brand_match: BrandMatch | None) -> str:
        if brand_match is None:
            return query
        return cls._query_without_brand(
            query,
            brand_match.matched_text or brand_match.matched_alias,
        )

    @classmethod
    def _dedupe_records(cls, records: list[ProductSourceRecord]) -> list[ProductSourceRecord]:
        deduped: list[ProductSourceRecord] = []
        seen: dict[str, int] = {}
        for record in records:
            key = cls._record_key(record)
            if key in seen:
                index = seen[key]
                deduped[index] = cls._merge_records(deduped[index], record)
                continue
            seen[key] = len(deduped)
            deduped.append(record)
        return deduped

    @staticmethod
    def _merge_records(
        existing: ProductSourceRecord,
        incoming: ProductSourceRecord,
    ) -> ProductSourceRecord:
        return existing.model_copy(
            update={
                "category": incoming.category or existing.category,
                "source_brand_name": incoming.source_brand_name or existing.source_brand_name,
                "product_name_ko": existing.product_name_ko or incoming.product_name_ko,
                "regular_price": (
                    incoming.regular_price
                    if incoming.regular_price is not None
                    and (
                        existing.regular_price is None
                        or incoming.original_price is not None
                        or incoming.sale_price is not None
                    )
                    else existing.regular_price
                ),
                "original_price": (
                    incoming.original_price
                    if incoming.original_price is not None
                    else existing.original_price
                ),
                "sale_price": (
                    incoming.sale_price
                    if incoming.sale_price is not None
                    else existing.sale_price
                ),
                "discount_rate": (
                    incoming.discount_rate
                    if incoming.discount_rate is not None
                    else existing.discount_rate
                ),
                "currency": incoming.currency or existing.currency,
                "shade": existing.shade or incoming.shade,
                "image_url": incoming.image_url or existing.image_url,
                "rating": incoming.rating if incoming.rating is not None else existing.rating,
                "review_count": (
                    incoming.review_count
                    if incoming.review_count is not None
                    else existing.review_count
                ),
                "description": incoming.description or existing.description,
                "options": incoming.options or existing.options,
                "sold_out": (
                    incoming.sold_out if incoming.sold_out is not None else existing.sold_out
                ),
                "source_url": existing.source_url or incoming.source_url,
                "source_product_id": existing.source_product_id or incoming.source_product_id,
                "updated_at": incoming.updated_at or existing.updated_at,
            }
        )

    @classmethod
    def _record_key(cls, record: ProductSourceRecord) -> str:
        if record.source_product_id and (
            record.source == "oliveyoung" or record.source.startswith("oliveyoung:")
        ):
            return f"oliveyoung:{record.source_product_id}"
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
            if product.product_name_ko and (product.brand_ko or product.brand_en)
        ]

    @classmethod
    def _dedupe_results(cls, results: list[ProductSearchResult]) -> list[ProductSearchResult]:
        deduped: list[ProductSearchResult] = []
        seen: set[str] = set()
        for product in results:
            brand_key = cls._key(product.brand_en)
            name_key = cls._key(product.product_name_ko)
            if not brand_key or not name_key:
                deduped.append(product)
                continue
            key = f"{brand_key}:{name_key}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(product)
        return deduped

    def _filter_allowed_sources(
        self,
        results: list[ProductSearchResult],
    ) -> list[ProductSearchResult]:
        return [
            product
            for product in results
            if self._source_policy.allows(product.source)
        ]

    def _with_source_metadata(self, product: ProductSearchResult) -> ProductSearchResult:
        return product.model_copy(
            update={
                "source_label": self._source_policy.label(product.source),
                "source_priority": self._source_policy.priority(product.source),
            }
        )

    @classmethod
    def _rank_query_matches(
        cls,
        results: list[ProductSearchResult],
        product_query: str,
    ) -> tuple[list[ProductSearchResult], int]:
        query_key = cls._key(product_query)
        if not query_key:
            return results, 1
        scored = [
            (cls._match_score(product, product_query, index), product)
            for index, product in enumerate(results)
        ]
        ranked = sorted(scored, key=lambda item: item[0], reverse=True)
        if not ranked or ranked[0][0][0] <= 0:
            return results, 0
        return [product for score, product in ranked if score[0] > 0], ranked[0][0][0]

    @classmethod
    def _query_matches_in_source_order(
        cls,
        results: list[ProductSearchResult],
        product_query: str,
    ) -> tuple[list[ProductSearchResult], int]:
        query_key = cls._key(product_query)
        if not query_key:
            return results, 1
        scored = [
            (cls._match_score(product, product_query, index)[0], product)
            for index, product in enumerate(results)
        ]
        top_score = max((score for score, _product in scored), default=0)
        if top_score <= 0:
            return results, 0
        return [product for score, product in scored if score > 0], top_score

    @classmethod
    def _match_score(
        cls,
        product: ProductSearchResult,
        product_query: str,
        index: int,
    ) -> tuple[int, int, int]:
        query_key = cls._key(product_query)
        haystack_key = cls._key(
            " ".join(
                value
                for value in [
                    product.brand_ko,
                    product.brand_en,
                    product.product_name_ko,
                    product.category,
                    product.shade,
                    product.description,
                    " ".join(product.options or []),
                ]
                if value
            )
        )
        if not query_key or not haystack_key:
            return (0, 0, -index)

        category_tokens = cls._category_tokens(product_query)
        if category_tokens and not all(token in haystack_key for token in category_tokens):
            return (0, 0, -index)
        distinctive_tokens = cls._distinctive_tokens(product_query)
        if distinctive_tokens and not any(token in haystack_key for token in distinctive_tokens):
            return (0, 0, -index)

        score = 100 if query_key in haystack_key else 0
        for token in cls._tokens(product_query):
            token_key = cls._key(token)
            if len(token_key) >= 2 and token_key in haystack_key:
                score += 10
        source_priority = product.source_priority if product.source_priority is not None else 1000
        return (score, -source_priority, -index)

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
            "젤",
            "오일",
            "크림",
            "로션",
            "스프레이",
            "토너",
            "세럼",
            "앰플",
            "에센스",
            "클렌저",
            "클렌징",
            "샴푸",
            "트리트먼트",
            "마스크",
            "팩",
            "쿠션",
            "네일",
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

    @classmethod
    def _can_use_verified_shortcut(cls, query: str, require_relevant: bool) -> bool:
        return require_relevant

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
    def _collect_limit(criteria: SearchCriteria, product_query: str = "") -> int:
        has_filters = any(
            [
                criteria.min_price is not None,
                criteria.max_price is not None,
                criteria.has_shade is not None,
            ]
        )
        needs_extra_matches = bool(criteria.brand and product_query)
        if not has_filters and not needs_extra_matches:
            return criteria.limit
        return max(criteria.limit, 48)

    async def close(self) -> None:
        for task in list(self._background_tasks):
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*list(self._background_tasks), return_exceptions=True)
            self._background_tasks.clear()
        if self._product_index is not None:
            await self._product_index.close()
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
        brand_ko = product.brand_ko.casefold() if product.brand_ko else ""
        name = product.product_name_ko.casefold() if product.product_name_ko else ""
        brand_key = cls._key(product.brand_en)
        brand_ko_key = cls._key(product.brand_ko)
        name_key = cls._key(product.product_name_ko)
        raw_key = cls._key(raw_needle)
        normalized_key = cls._key(normalized_needle)
        return bool(
            (normalized_needle and normalized_needle in brand)
            or (normalized_key and normalized_key in brand_key)
            or (normalized_needle and normalized_needle in brand_ko)
            or (normalized_key and normalized_key in brand_ko_key)
            or raw_needle in brand
            or (raw_key and raw_key in brand_key)
            or raw_needle in brand_ko
            or (raw_key and raw_key in brand_ko_key)
            or raw_needle in name
            or (raw_key and raw_key in name_key)
        )

    @staticmethod
    def _key(value: str | None) -> str:
        text = search_key(value)
        text = (
            text.replace("glowy", "글로이")
            .replace("tear", "티어")
            .replace("비타민씨", "비타")
            .replace("여백살롱", "여백카롱")
            .replace("및서재", "밑서재")
            .replace("플로팅", "플러팅")
            .replace("이즈핏", "이지핏")
            .replace("땡큐요엠핑크", "요염핑")
        )
        return text

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
