from __future__ import annotations

# ruff: noqa: E402

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.cache.ttl import AsyncTTLCache
from app.core.config import Settings
from app.data_collector.base import SearchCriteria
from app.data_collector.local_catalog import LocalVerifiedCatalogCollector
from app.indexing.store import SQLiteProductIndexStore
from app.normalizer.brand import BrandResolver
from app.normalizer.product import ProductNormalizer
from app.service.search_service import SearchService, _CollectedResult


SMOKE_QUERIES = (
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest GlowSearch deterministic query coverage.")
    parser.add_argument(
        "--mode",
        choices=["index-only", "app-local"],
        default="app-local",
        help="index-only는 SQLite index만, app-local은 SQLite index + verified catalog를 사용합니다.",
    )
    parser.add_argument("--limit", type=int, default=4, help="검색어별 결과 limit.")
    parser.add_argument("--db-path", type=Path, default=None, help="SQLite index path override.")
    parser.add_argument("--fail-under", type=float, default=None, help="전체 통과율 하한.")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    settings = Settings()
    if args.db_path is not None:
        settings = settings.model_copy(update={"product_index_path": args.db_path})

    store = SQLiteProductIndexStore(settings.product_index_path)
    resolver = BrandResolver(settings.brand_registry_path)
    service = SearchService(
        collectors=(
            []
            if args.mode == "index-only"
            else [LocalVerifiedCatalogCollector(settings.verified_catalog_path)]
        ),
        normalizer=ProductNormalizer(resolver, settings.oliveyoung_base_url),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=0),
        product_index=store,
        index_background_refresh_enabled=False,
        allowed_result_source_prefixes=tuple(settings.result_source_prefixes),
    )

    verified_products = _verified_products(settings.verified_catalog_path)
    groups = [
        await _run_group(service, "smoke_representative", SMOKE_QUERIES, args.limit),
        await _run_group(
            service,
            "default_seed_category_brand_queries",
            _dedupe(
                [
                    *settings.product_index_seed_queries,
                    *settings.product_index_category_queries,
                    *settings.product_index_brand_queries,
                ]
            ),
            args.limit,
        ),
        await _run_group(
            service,
            "brand_registry_warmup_aliases",
            _dedupe(resolver.warmup_aliases(200)),
            args.limit,
        ),
        await _run_group(
            service,
            "verified_product_names",
            _dedupe(product.get("product_name_ko") for product in verified_products),
            args.limit,
        ),
        await _run_group(
            service,
            "verified_product_keywords",
            _dedupe(
                keyword
                for product in verified_products
                for keyword in (product.get("keywords") or [])
            ),
            args.limit,
        ),
    ]
    stats = await store.stats()
    await service.close()

    total = sum(group["total"] for group in groups)
    failed = sum(group["failed"] for group in groups)
    pass_rate = round(((total - failed) / total) * 100, 1) if total else 0.0
    payload = {
        "mode": args.mode,
        "index_stats": stats,
        "total": total,
        "passed": total - failed,
        "failed": failed,
        "pass_rate": pass_rate,
        "groups": groups,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.fail_under is not None and pass_rate < args.fail_under:
        return 1
    return 0


async def _run_group(
    service: SearchService,
    name: str,
    queries: tuple[str, ...] | list[str],
    limit: int,
) -> dict[str, object]:
    rows = []
    for query in queries:
        response = await service.search(query, SearchCriteria(limit=max(limit, 1)))
        rows.append(
            {
                "query": query,
                "count": response.count,
                "first": response.results[0].product_name_ko if response.results else None,
            }
        )
    failed = [row for row in rows if row["count"] == 0]
    passed = len(rows) - len(failed)
    return {
        "name": name,
        "total": len(rows),
        "passed": passed,
        "failed": len(failed),
        "pass_rate": round((passed / len(rows)) * 100, 1) if rows else 0.0,
        "failed_queries": [row["query"] for row in failed],
    }


def _verified_products(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    products = payload.get("products", []) if isinstance(payload, dict) else []
    return [product for product in products if isinstance(product, dict)]


def _dedupe(values) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip() if value else ""
        key = text.casefold().replace(" ", "")
        if not text or key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
