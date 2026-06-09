from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.data_collector.base import ProductCollector, SourceUnavailableError
from app.indexing.agents import ProductIngestionAgent
from app.indexing.store import ProductIndexStore
from app.models.product import ProductSourceRecord
from app.normalizer.text import clean_text
from app.search.synonyms import search_key


@dataclass(frozen=True)
class IngestionSummary:
    query_count: int
    product_count: int
    stored_count: int
    job_count: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    failures: list[str] = field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None


class OliveYoungIngestionPipeline:
    def __init__(
        self,
        *,
        collector: ProductCollector,
        store: ProductIndexStore,
        ingestion_agent: ProductIngestionAgent | None = None,
    ):
        self._collector = collector
        self._store = store
        self._ingestion_agent = ingestion_agent or ProductIngestionAgent(store)

    async def ingest_queries(
        self,
        queries: Iterable[str],
        *,
        limit_per_query: int,
    ) -> IngestionSummary:
        started_at = _now()
        clean_queries = _dedupe_queries(queries)
        failures: list[str] = []
        product_count = 0
        stored_count = 0

        for query in clean_queries:
            try:
                records = await self._collector.search(query, limit_per_query)
            except SourceUnavailableError as exc:
                failures.append(f"{query}: {exc}")
                continue
            except Exception as exc:
                failures.append(f"{query}: {type(exc).__name__}: {exc}")
                continue
            records = _dedupe_records(records)
            product_count += len(records)
            if not records:
                continue
            await self._ingestion_agent.ingest_search_results([query], records)
            stored_count += len(records)

        return IngestionSummary(
            query_count=len(clean_queries),
            product_count=product_count,
            stored_count=stored_count,
            failures=failures,
            started_at=started_at,
            finished_at=_now(),
        )

    async def ingest_catalog_jobs(
        self,
        *,
        max_jobs: int,
        limit_per_query: int,
        kind: str | None = "oliveyoung-search",
    ) -> IngestionSummary:
        started_at = _now()
        jobs = await self._store.claim_catalog_jobs(limit=max(max_jobs, 1), kind=kind)
        failures: list[str] = []
        product_count = 0
        stored_count = 0
        completed_jobs = 0
        failed_jobs = 0

        for job in jobs:
            try:
                records = await self._collector.search(job.query, limit_per_query)
                records = _dedupe_records(records)
                product_count += len(records)
                if records:
                    await self._ingestion_agent.ingest_search_results([job.query], records)
                    stored_count += len(records)
                await self._store.complete_catalog_job(
                    job.id,
                    status="completed",
                    product_count=len(records),
                )
                completed_jobs += 1
            except SourceUnavailableError as exc:
                message = f"{job.query}: {exc}"
                failures.append(message)
                await self._store.complete_catalog_job(
                    job.id,
                    status="failed",
                    error=message,
                )
                failed_jobs += 1
            except Exception as exc:
                message = f"{job.query}: {type(exc).__name__}: {exc}"
                failures.append(message)
                await self._store.complete_catalog_job(
                    job.id,
                    status="failed",
                    error=message,
                )
                failed_jobs += 1

        return IngestionSummary(
            query_count=len(jobs),
            product_count=product_count,
            stored_count=stored_count,
            job_count=len(jobs),
            completed_jobs=completed_jobs,
            failed_jobs=failed_jobs,
            failures=failures,
            started_at=started_at,
            finished_at=_now(),
        )


def _dedupe_queries(queries: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for query in queries:
        text = clean_text(query)
        key = search_key(text)
        if not text or not key or key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped


def _dedupe_records(records: list[ProductSourceRecord]) -> list[ProductSourceRecord]:
    deduped: list[ProductSourceRecord] = []
    seen: set[str] = set()
    for record in records:
        key = _record_key(record)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def _record_key(record: ProductSourceRecord) -> str:
    if record.source_product_id:
        return f"{record.source}:{record.source_product_id}"
    brand_key = search_key(record.source_brand_name)
    name_key = search_key(record.product_name_ko)
    if brand_key and name_key:
        return f"{brand_key}:{name_key}"
    return search_key(record.source_url) or ""


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()
