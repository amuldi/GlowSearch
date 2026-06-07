from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from statistics import quantiles
from time import perf_counter
from typing import Deque


@dataclass(frozen=True)
class Timer:
    started_at: float

    @classmethod
    def start(cls) -> "Timer":
        return cls(started_at=perf_counter())

    def elapsed_ms(self) -> float:
        return (perf_counter() - self.started_at) * 1000


class SearchMetrics:
    def __init__(self, *, latency_window_size: int = 200):
        self._latencies_ms: Deque[float] = deque(maxlen=max(latency_window_size, 1))
        self._source_latencies_ms: dict[str, Deque[float]] = {}
        self._counters: Counter[str] = Counter()
        self._source_successes: Counter[str] = Counter()
        self._source_failures: Counter[str] = Counter()
        self._source_timeouts: Counter[str] = Counter()
        self._last_background_error: str | None = None
        self._last_source_errors: list[str] = []

    def record_cache_lookup(self, hit: bool) -> None:
        self._counters["cache_hits" if hit else "cache_misses"] += 1

    def record_index_lookup(self, hit: bool) -> None:
        self._counters["index_hits" if hit else "index_misses"] += 1

    def record_source_success(self, source: str, *, elapsed_ms: float, result_count: int) -> None:
        self._source_successes[source] += 1
        self._counters["source_result_count"] += result_count
        self._source_latencies(source).append(elapsed_ms)

    def record_source_failure(self, source: str, error: str, *, timeout: bool = False) -> None:
        self._source_failures[source] += 1
        self._last_source_errors.append(error)
        self._last_source_errors = self._last_source_errors[-20:]
        if timeout:
            self._source_timeouts[source] += 1

    def record_search(self, *, elapsed_ms: float, result_count: int, failed: bool = False) -> None:
        self._latencies_ms.append(elapsed_ms)
        self._counters["search_count"] += 1
        self._counters["search_result_count"] += result_count
        if failed:
            self._counters["search_failures"] += 1

    def record_background_index_error(self, error: str | None) -> None:
        if error:
            self._counters["background_index_errors"] += 1
            self._last_background_error = error

    def snapshot(self) -> dict[str, object]:
        source_names = sorted(
            set(self._source_successes)
            | set(self._source_failures)
            | set(self._source_timeouts)
            | set(self._source_latencies_ms)
        )
        return {
            "search_count": self._counters["search_count"],
            "search_failures": self._counters["search_failures"],
            "cache_hits": self._counters["cache_hits"],
            "cache_misses": self._counters["cache_misses"],
            "index_hits": self._counters["index_hits"],
            "index_misses": self._counters["index_misses"],
            "result_count_total": self._counters["search_result_count"],
            "source_result_count_total": self._counters["source_result_count"],
            "latency_ms": {
                "p50": _percentile(self._latencies_ms, 50),
                "p95": _percentile(self._latencies_ms, 95),
                "sample_count": len(self._latencies_ms),
            },
            "sources": {
                source: {
                    "successes": self._source_successes[source],
                    "failures": self._source_failures[source],
                    "timeouts": self._source_timeouts[source],
                    "latency_ms": {
                        "p50": _percentile(self._source_latencies_ms.get(source, ()), 50),
                        "p95": _percentile(self._source_latencies_ms.get(source, ()), 95),
                        "sample_count": len(self._source_latencies_ms.get(source, ())),
                    },
                }
                for source in source_names
            },
            "background_index_errors": self._counters["background_index_errors"],
            "last_background_error": self._last_background_error,
            "last_source_errors": list(self._last_source_errors),
        }

    def _source_latencies(self, source: str) -> Deque[float]:
        if source not in self._source_latencies_ms:
            self._source_latencies_ms[source] = deque(maxlen=200)
        return self._source_latencies_ms[source]


def _percentile(values: object, percentile: int) -> float | None:
    samples = list(values) if values is not None else []
    if not samples:
        return None
    if len(samples) == 1:
        return round(float(samples[0]), 2)
    if percentile == 50:
        samples = sorted(samples)
        index = (len(samples) - 1) / 2
        lower = int(index)
        upper = min(lower + 1, len(samples) - 1)
        if lower == upper:
            return round(float(samples[lower]), 2)
        return round(float((samples[lower] + samples[upper]) / 2), 2)
    if percentile == 95:
        return round(float(quantiles(samples, n=20, method="inclusive")[18]), 2)
    return None
