from __future__ import annotations

import asyncio

from app.data_collector.base import ProductCollector, SourceUnavailableError
from app.models.product import ProductSourceRecord


class ProductIngestionAgent:
    """Fetch source records from adapters under strict per-source budgets."""

    def __init__(
        self,
        collectors: list[ProductCollector],
        *,
        default_timeout_seconds: float,
        timeout_overrides: dict[str, float] | None = None,
    ):
        self._collectors = collectors
        self._default_timeout_seconds = default_timeout_seconds
        self._timeout_overrides = timeout_overrides or {}

    async def ingest(self, keyword: str, limit: int) -> tuple[list[ProductSourceRecord], list[str]]:
        if not keyword.strip() or limit <= 0:
            return [], []

        async def run(collector: ProductCollector) -> tuple[list[ProductSourceRecord], str | None]:
            timeout = self._timeout_overrides.get(collector.name, self._default_timeout_seconds)
            try:
                return await asyncio.wait_for(collector.search(keyword, limit), timeout=timeout), None
            except TimeoutError:
                return [], f"{collector.name}: request timed out"
            except SourceUnavailableError as exc:
                return [], f"{collector.name}: {exc}"

        collected = await asyncio.gather(*(run(collector) for collector in self._collectors))
        records: list[ProductSourceRecord] = []
        errors: list[str] = []
        for source_records, error in collected:
            records.extend(source_records)
            if error:
                errors.append(error)
        return records, errors
