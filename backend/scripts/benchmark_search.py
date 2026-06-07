from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agents.eval import EvalAgent, SearchEvalSample  # noqa: E402
from app.data_collector.base import SearchCriteria  # noqa: E402
from app.service.factory import get_search_service  # noqa: E402


DEFAULT_QUERIES = [
    "틴트",
    "sunscreen",
    "롬앤 글래스팅 틴트",
    "serum",
    "1234567890123",
]


async def run_benchmark(queries: list[str], iterations: int, limit: int) -> dict[str, object]:
    service = get_search_service()
    samples: list[SearchEvalSample] = []
    source_counts: Counter[str] = Counter()
    source_errors: Counter[str] = Counter()

    try:
        for _ in range(iterations):
            for query in queries:
                started = time.perf_counter()
                response = await service.search(query, SearchCriteria(limit=limit))
                elapsed_ms = (time.perf_counter() - started) * 1000
                samples.append(
                    SearchEvalSample(
                        query=query,
                        latency_ms=elapsed_ms,
                        result_count=response.count,
                        source_errors=len(response.source_errors),
                    )
                )
                source_counts.update(result.source for result in response.results)
                source_errors.update(error.split(":", 1)[0] for error in response.source_errors)
    finally:
        await service.close()

    summary = EvalAgent().summarize(samples)
    return {
        "summary": summary,
        "source_result_counts": dict(source_counts),
        "source_error_counts": dict(source_errors),
        "queries": queries,
        "iterations": iterations,
        "limit": limit,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark GlowSearch backend search latency.")
    parser.add_argument("--query", action="append", dest="queries", help="Query to benchmark.")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--limit", type=int, default=24)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    queries = args.queries or DEFAULT_QUERIES
    result = asyncio.run(run_benchmark(queries, args.iterations, args.limit))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
