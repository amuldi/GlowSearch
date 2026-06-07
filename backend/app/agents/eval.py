from __future__ import annotations

from dataclasses import dataclass
from statistics import median, quantiles


@dataclass(frozen=True)
class SearchEvalSample:
    query: str
    latency_ms: float
    result_count: int
    source_errors: int


class EvalAgent:
    """Aggregate lightweight search quality and reliability metrics."""

    def summarize(self, samples: list[SearchEvalSample]) -> dict[str, float]:
        if not samples:
            return {
                "sample_count": 0,
                "p50_latency_ms": 0,
                "p95_latency_ms": 0,
                "avg_results": 0,
                "source_failure_rate": 0,
            }

        latencies = sorted(sample.latency_ms for sample in samples)
        p95 = quantiles(latencies, n=20)[18] if len(latencies) >= 20 else latencies[-1]
        return {
            "sample_count": float(len(samples)),
            "p50_latency_ms": median(latencies),
            "p95_latency_ms": p95,
            "avg_results": sum(sample.result_count for sample in samples) / len(samples),
            "source_failure_rate": (
                sum(1 for sample in samples if sample.source_errors > 0) / len(samples)
            ),
        }
