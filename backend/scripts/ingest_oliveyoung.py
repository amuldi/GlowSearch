from __future__ import annotations

# ruff: noqa: E402

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import Settings
from app.data_collector.oliveyoung_api import OliveYoungPublicApiCollector
from app.indexing.agents import OliveYoungDetailEnrichmentAgent, ProductIngestionAgent
from app.indexing.store import SQLiteProductIndexStore
from app.ingestion.export import write_products_csv
from app.ingestion.oliveyoung_pipeline import OliveYoungIngestionPipeline
from app.normalizer.brand import BrandResolver
from app.normalizer.product import ProductNormalizer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely ingest Olive Young product search results into SQLite."
    )
    parser.add_argument("--query", action="append", default=[], help="검색 seed. 여러 번 지정 가능.")
    parser.add_argument(
        "--use-default-seeds",
        action="store_true",
        help="설정의 seed/category/brand query를 함께 사용합니다.",
    )
    parser.add_argument("--max-queries", type=int, default=None, help="처리할 query 최대 개수.")
    parser.add_argument("--limit", type=int, default=48, help="query별 수집 개수.")
    parser.add_argument(
        "--coverage-pairs",
        type=int,
        default=0,
        help="브랜드+카테고리 조합 query 최대 개수. 검색 누락 보강용이며 기본값은 0입니다.",
    )
    parser.add_argument(
        "--include-gaps",
        action="store_true",
        help="DB에 기록된 search_gaps를 수집 후보에 포함합니다.",
    )
    parser.add_argument("--gap-limit", type=int, default=100, help="포함할 search_gaps 최대 개수.")
    parser.add_argument(
        "--enqueue-catalog",
        action="store_true",
        help="즉시 수집하지 않고 catalog_jobs 큐에 수집 후보를 등록합니다.",
    )
    parser.add_argument(
        "--run-catalog-jobs",
        action="store_true",
        help="catalog_jobs 큐에서 pending 작업을 가져와 수집합니다.",
    )
    parser.add_argument("--max-jobs", type=int, default=50, help="한 번에 처리할 catalog job 수.")
    parser.add_argument(
        "--job-kind",
        default="oliveyoung-search",
        help="catalog job kind. 기본값은 oliveyoung-search입니다.",
    )
    parser.add_argument("--job-priority", type=int, default=100, help="등록할 catalog job 우선순위.")
    parser.add_argument("--job-max-attempts", type=int, default=3, help="catalog job 최대 재시도 수.")
    parser.add_argument("--db-path", type=Path, default=None, help="SQLite index 경로 override.")
    parser.add_argument("--csv", type=Path, default=None, help="수집 후 전체 index를 CSV로 export.")
    parser.add_argument("--csv-limit", type=int, default=None, help="CSV export 최대 row 수.")
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=None,
        help="공개 JSON adapter 초당 요청 수 override. 0이면 제한 해제.",
    )
    parser.add_argument(
        "--enrich-details",
        action="store_true",
        help="공식 상세 페이지 보강을 opt-in으로 실행합니다. 차단 신호가 있으면 우회하지 않습니다.",
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    settings = Settings()
    updates = {}
    if args.db_path is not None:
        updates["product_index_path"] = args.db_path
    if args.rate_limit is not None:
        updates["oliveyoung_public_api_rate_limit_per_second"] = args.rate_limit
    if updates:
        settings = settings.model_copy(update=updates)

    store = SQLiteProductIndexStore(settings.product_index_path)
    brand_resolver = BrandResolver(settings.brand_registry_path)
    normalizer = ProductNormalizer(brand_resolver, settings.oliveyoung_base_url)
    store.seed_brand_aliases(brand_resolver.index_aliases())
    queries = await _collect_queries(args, settings, store)
    if args.max_queries is not None and args.max_queries >= 0:
        queries = queries[: args.max_queries]
    detail_enricher = OliveYoungDetailEnrichmentAgent(settings) if args.enrich_details else None
    ingestion_agent = ProductIngestionAgent(
        store,
        normalizer=normalizer,
        detail_enricher=detail_enricher,
    )
    pipeline = OliveYoungIngestionPipeline(
        collector=OliveYoungPublicApiCollector(settings),
        store=store,
        ingestion_agent=ingestion_agent,
    )
    try:
        if args.enqueue_catalog:
            if not queries:
                print("Provide --query, --use-default-seeds, --coverage-pairs, or --include-gaps.", file=sys.stderr)
                return 2
            enqueued_count = await store.enqueue_catalog_jobs(
                queries,
                kind=args.job_kind,
                priority=args.job_priority,
                max_attempts=args.job_max_attempts,
            )
            payload: dict[str, object] = {
                "enqueued_jobs": enqueued_count,
                "candidate_queries": len(queries),
                "catalog_job_stats": await store.catalog_job_stats(),
            }
            if not args.run_catalog_jobs:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0
        if args.run_catalog_jobs:
            summary = await pipeline.ingest_catalog_jobs(
                max_jobs=max(args.max_jobs, 1),
                limit_per_query=max(args.limit, 1),
                kind=args.job_kind,
            )
            payload = asdict(summary)
            payload["catalog_job_stats"] = await store.catalog_job_stats()
        else:
            if not queries:
                print("Provide --query or --use-default-seeds.", file=sys.stderr)
                return 2
            summary = await pipeline.ingest_queries(queries, limit_per_query=max(args.limit, 1))
            payload = asdict(summary)
        if args.csv is not None:
            exported_count = write_products_csv(
                await store.all_products(limit=args.csv_limit),
                args.csv,
            )
            payload["csv_path"] = str(args.csv)
            payload["csv_count"] = exported_count
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    finally:
        brand_resolver.close()
        await store.close()
    return 0


async def _collect_queries(
    args: argparse.Namespace,
    settings: Settings,
    store: SQLiteProductIndexStore,
) -> list[str]:
    queries = list(args.query)
    if args.use_default_seeds:
        queries.extend(settings.product_index_seed_queries)
        queries.extend(settings.product_index_category_queries)
        queries.extend(settings.product_index_brand_queries)
    if args.coverage_pairs > 0:
        queries.extend(_coverage_pair_queries(settings, args.coverage_pairs))
    if args.include_gaps:
        gaps = await store.recent_search_gaps(limit=max(args.gap_limit, 1))
        queries.extend(str(gap["query"]) for gap in gaps if gap.get("query"))
    return queries


def _coverage_pair_queries(settings: Settings, limit: int) -> list[str]:
    pairs: list[str] = []
    seen: set[str] = set()
    for brand in settings.product_index_brand_queries:
        for category in settings.product_index_category_queries:
            query = f"{brand} {category}".strip()
            key = query.casefold()
            if key in seen:
                continue
            seen.add(key)
            pairs.append(query)
            if len(pairs) >= limit:
                return pairs
    return pairs


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
