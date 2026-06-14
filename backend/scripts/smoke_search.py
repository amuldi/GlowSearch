from __future__ import annotations

# ruff: noqa: E402

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_QUERIES: tuple[str, ...] = (
    "선크림",
    "틴트",
    "쿠션",
    "로션",
    "롬앤",
    "롬엔",
    "too cool",
    "투쿨포스쿨",
    "정샘물",
    "비긴스 바이 정샘물",
    "클리오",
    "킬커버",
)


@dataclass(frozen=True)
class SmokeResult:
    query: str
    count: int
    ok: bool
    first_result: str | None = None
    error: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run representative GlowSearch search smoke checks.")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Backend base URL. 예: http://localhost:8000 또는 배포 URL",
    )
    parser.add_argument("--query", action="append", default=[], help="검색어. 여러 번 지정 가능.")
    parser.add_argument("--limit", type=int, default=4, help="검색어별 요청 limit.")
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="빈 결과를 실패로 처리하지 않습니다. API 응답 가능성만 확인할 때 사용합니다.",
    )
    parser.add_argument("--timeout", type=float, default=8.0, help="요청 timeout seconds.")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    queries = args.query or list(DEFAULT_QUERIES)
    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"),
        timeout=max(args.timeout, 0.1),
    ) as client:
        results = [await _run_one(client, query, args.limit, args.allow_empty) for query in queries]

    payload = {
        "base_url": args.base_url.rstrip("/"),
        "query_count": len(results),
        "passed": sum(1 for result in results if result.ok),
        "failed": sum(1 for result in results if not result.ok),
        "results": [result.__dict__ for result in results],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if all(result.ok for result in results) else 1


async def _run_one(
    client: httpx.AsyncClient,
    query: str,
    limit: int,
    allow_empty: bool,
) -> SmokeResult:
    try:
        response = await client.get(f"/search?{urlencode({'q': query, 'limit': max(limit, 1)})}")
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return SmokeResult(query=query, count=0, ok=False, error=f"{type(exc).__name__}: {exc}")

    results = payload.get("results", []) if isinstance(payload, dict) else []
    count = len(results) if isinstance(results, list) else 0
    first_result = None
    if count:
        first = results[0]
        if isinstance(first, dict):
            first_result = str(first.get("product_name_ko") or first.get("brand_ko") or "")
    return SmokeResult(
        query=query,
        count=count,
        ok=allow_empty or count > 0,
        first_result=first_result,
    )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
