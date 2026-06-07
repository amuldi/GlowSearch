from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from statistics import quantiles
from time import perf_counter

import httpx


DEFAULT_QUERIES = (
    "젤",
    "틴트",
    "쿠션",
    "선크림",
    "정샘물",
    "비긴스",
)


@dataclass(frozen=True)
class Sample:
    query: str
    elapsed_ms: float
    status_code: int
    result_count: int
    source_error_count: int
    error: str | None = None


async def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark GlowSearch /search latency.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--query", action="append", dest="queries")
    args = parser.parse_args()

    queries = tuple(args.queries or DEFAULT_QUERIES)
    samples: list[Sample] = []
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for _ in range(max(args.repeat, 1)):
            batch = await asyncio.gather(
                *(_measure(client, args.base_url, query, args.limit) for query in queries)
            )
            samples.extend(batch)

    latencies = [sample.elapsed_ms for sample in samples]
    failures = [sample for sample in samples if sample.status_code >= 400]
    source_error_total = sum(sample.source_error_count for sample in samples)
    result_total = sum(sample.result_count for sample in samples)
    print(f"base_url={args.base_url}")
    print(f"samples={len(samples)} failures={len(failures)} source_errors={source_error_total}")
    print(f"result_count_total={result_total}")
    print(f"latency_ms_p50={_percentile(latencies, 50)}")
    print(f"latency_ms_p95={_percentile(latencies, 95)}")
    for sample in samples:
        print(
            "sample "
            f"query={sample.query!r} status={sample.status_code} "
            f"elapsed_ms={sample.elapsed_ms:.2f} count={sample.result_count} "
            f"source_errors={sample.source_error_count}"
            + (f" error={sample.error!r}" if sample.error else "")
        )


async def _measure(client: httpx.AsyncClient, base_url: str, query: str, limit: int) -> Sample:
    started_at = perf_counter()
    try:
        response = await client.get(
            f"{base_url.rstrip('/')}/search",
            params={"q": query, "limit": limit},
        )
    except httpx.HTTPError as exc:
        return Sample(
            query=query,
            elapsed_ms=(perf_counter() - started_at) * 1000,
            status_code=0,
            result_count=0,
            source_error_count=0,
            error=f"{type(exc).__name__}: {exc}",
        )
    elapsed_ms = (perf_counter() - started_at) * 1000
    result_count = 0
    source_error_count = 0
    if response.headers.get("content-type", "").startswith("application/json"):
        payload = response.json()
        result_count = len(payload.get("results", [])) if isinstance(payload, dict) else 0
        source_error_count = (
            len(payload.get("source_errors", [])) if isinstance(payload, dict) else 0
        )
    return Sample(
        query=query,
        elapsed_ms=elapsed_ms,
        status_code=response.status_code,
        result_count=result_count,
        source_error_count=source_error_count,
    )


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 2)
    if percentile == 50:
        sorted_values = sorted(values)
        index = (len(sorted_values) - 1) / 2
        lower = int(index)
        upper = min(lower + 1, len(sorted_values) - 1)
        return round((sorted_values[lower] + sorted_values[upper]) / 2, 2)
    if percentile == 95:
        return round(quantiles(values, n=20, method="inclusive")[18], 2)
    return None


if __name__ == "__main__":
    asyncio.run(main())
