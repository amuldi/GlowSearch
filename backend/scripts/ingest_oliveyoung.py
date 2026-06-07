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

    queries = list(args.query)
    if args.use_default_seeds:
        queries.extend(settings.product_index_seed_queries)
        queries.extend(settings.product_index_category_queries)
        queries.extend(settings.product_index_brand_queries)
    if args.max_queries is not None and args.max_queries >= 0:
        queries = queries[: args.max_queries]
    if not queries:
        print("Provide --query or --use-default-seeds.", file=sys.stderr)
        return 2

    store = SQLiteProductIndexStore(settings.product_index_path)
    detail_enricher = OliveYoungDetailEnrichmentAgent(settings) if args.enrich_details else None
    ingestion_agent = ProductIngestionAgent(store, detail_enricher=detail_enricher)
    pipeline = OliveYoungIngestionPipeline(
        collector=OliveYoungPublicApiCollector(settings),
        store=store,
        ingestion_agent=ingestion_agent,
    )
    try:
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
        await store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
