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
from app.ingestion.coverage import CoverageQueryOptions, build_coverage_queries
from app.ingestion.export import write_products_csv
from app.ingestion.oliveyoung_pipeline import OliveYoungIngestionPipeline
from app.normalizer.brand import BrandResolver
from app.normalizer.product import ProductNormalizer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh GlowSearch coverage by enqueueing default, brand/category, "
            "registry alias, and search-gap queries, then processing a bounded job batch."
        )
    )
    parser.add_argument("--query", action="append", default=[], help="추가 검색어. 여러 번 지정 가능.")
    parser.add_argument("--db-path", type=Path, default=None, help="SQLite index 경로 override.")
    parser.add_argument("--max-queries", type=int, default=None, help="등록 후보 query 최대 개수.")
    parser.add_argument("--coverage-pairs", type=int, default=300, help="브랜드+카테고리 조합 query 수.")
    parser.add_argument("--gap-limit", type=int, default=100, help="포함할 search_gaps 최대 개수.")
    parser.add_argument("--max-jobs", type=int, default=50, help="이번 실행에서 처리할 catalog job 수.")
    parser.add_argument("--limit", type=int, default=240, help="query별 수집 개수.")
    parser.add_argument("--job-kind", default="oliveyoung-search", help="catalog job kind.")
    parser.add_argument("--job-priority", type=int, default=40, help="등록할 catalog job 우선순위.")
    parser.add_argument("--job-max-attempts", type=int, default=3, help="catalog job 최대 재시도 수.")
    parser.add_argument(
        "--no-default-seeds",
        action="store_true",
        help="기본 seed/category/brand query 등록을 건너뜁니다.",
    )
    parser.add_argument(
        "--no-gaps",
        action="store_true",
        help="search_gaps 등록을 건너뜁니다.",
    )
    parser.add_argument(
        "--no-run",
        action="store_true",
        help="큐 등록만 하고 catalog job 처리는 하지 않습니다.",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="query 후보만 출력하고 catalog_jobs enqueue나 수집 실행은 하지 않습니다.",
    )
    parser.add_argument(
        "--reset-stale-running-minutes",
        type=int,
        default=0,
        help="지정한 분보다 오래 running 상태인 catalog job을 실행 전 복구합니다. 0이면 비활성화.",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="실행 후 전체 index를 CSV로 export합니다.",
    )
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="큐 등록/실행 없이 현재 index만 CSV로 export하고 상태를 출력합니다.",
    )
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
    settings = _settings_from_args(args)
    store = SQLiteProductIndexStore(settings.product_index_path)
    brand_resolver = BrandResolver(settings.brand_registry_path)
    normalizer = ProductNormalizer(brand_resolver, settings.oliveyoung_base_url)
    store.seed_brand_aliases(brand_resolver.index_aliases())

    try:
        if args.export_only:
            payload: dict[str, object] = {
                "catalog_job_stats": await store.catalog_job_stats(),
                "index_stats": await store.stats(),
            }
            if args.csv is not None:
                exported_count = write_products_csv(
                    await store.all_products(limit=args.csv_limit),
                    args.csv,
                )
                payload["csv_path"] = str(args.csv)
                payload["csv_count"] = exported_count
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        queries = await build_coverage_queries(
            settings,
            store,
            CoverageQueryOptions(
                custom_queries=args.query,
                include_default_seeds=not args.no_default_seeds,
                extra_seed_queries=brand_resolver.warmup_aliases(
                    settings.product_index_brand_registry_warmup_limit
                ) if not args.no_default_seeds else (),
                coverage_pairs=max(args.coverage_pairs, 0),
                include_gaps=not args.no_gaps,
                gap_limit=max(args.gap_limit, 1),
                max_queries=args.max_queries,
            ),
        )
        if args.plan_only:
            print(
                json.dumps(
                    {
                        "candidate_queries": len(queries),
                        "queries": queries,
                        "catalog_job_stats": await store.catalog_job_stats(),
                        "index_stats": await store.stats(),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        reset_count = 0
        if args.reset_stale_running_minutes > 0:
            reset_count = await store.reset_stale_catalog_jobs(
                older_than_minutes=args.reset_stale_running_minutes,
                kind=args.job_kind,
            )

        enqueued_count = await store.enqueue_catalog_jobs(
            queries,
            kind=args.job_kind,
            priority=max(args.job_priority, 0),
            max_attempts=max(args.job_max_attempts, 1),
        )
        payload: dict[str, object] = {
            "candidate_queries": len(queries),
            "reset_stale_running_jobs": reset_count,
            "enqueued_jobs": enqueued_count,
            "catalog_job_stats_before_run": await store.catalog_job_stats(),
        }

        if not args.no_run:
            pipeline = OliveYoungIngestionPipeline(
                collector=OliveYoungPublicApiCollector(settings),
                store=store,
                ingestion_agent=ProductIngestionAgent(
                    store,
                    normalizer=normalizer,
                    detail_enricher=(
                        OliveYoungDetailEnrichmentAgent(settings) if args.enrich_details else None
                    ),
                ),
            )
            payload["run_summary"] = asdict(
                await pipeline.ingest_catalog_jobs(
                    max_jobs=max(args.max_jobs, 1),
                    limit_per_query=max(args.limit, 1),
                    kind=args.job_kind,
                )
            )

        payload["catalog_job_stats_after_run"] = await store.catalog_job_stats()
        payload["index_stats"] = await store.stats()

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


def _settings_from_args(args: argparse.Namespace) -> Settings:
    settings = Settings()
    updates = {}
    if args.db_path is not None:
        updates["product_index_path"] = args.db_path
    if args.rate_limit is not None:
        updates["oliveyoung_public_api_rate_limit_per_second"] = args.rate_limit
    if updates:
        return settings.model_copy(update=updates)
    return settings


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
