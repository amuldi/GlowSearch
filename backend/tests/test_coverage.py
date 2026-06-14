import pytest

from app.core.config import Settings
from app.indexing.store import SQLiteProductIndexStore
from app.ingestion.coverage import (
    CoverageQueryOptions,
    build_coverage_queries,
    coverage_pair_queries,
    dedupe_queries,
)


def test_dedupe_queries_normalizes_spacing_and_case() -> None:
    assert dedupe_queries([" 틴트 ", "틴 트", "TINT", "tint", ""]) == ["틴트", "TINT"]


def test_coverage_pair_queries_are_bounded_and_deduped() -> None:
    pairs = coverage_pair_queries(
        ["뮤드", "뮤드", "롬앤"],
        ["틴트", " 립틴트 "],
        3,
    )

    assert pairs == ["뮤드 틴트", "뮤드 립틴트", "롬앤 틴트"]


@pytest.mark.asyncio
async def test_build_coverage_queries_combines_seeds_pairs_extra_queries_and_gaps(tmp_path) -> None:
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    await store.record_search_gap("없는 상품", result_count=0, reason="empty_result")
    settings = Settings(
        product_index_seed_queries=["선크림"],
        product_index_category_queries=["틴트"],
        product_index_brand_queries=["뮤드"],
    )

    queries = await build_coverage_queries(
        settings,
        store,
        CoverageQueryOptions(
            custom_queries=["직접입력"],
            extra_seed_queries=["레지스트리브랜드"],
            coverage_pairs=2,
            include_gaps=True,
        ),
    )
    await store.close()

    assert queries == [
        "직접입력",
        "선크림",
        "틴트",
        "뮤드",
        "레지스트리브랜드",
        "뮤드 틴트",
        "없는 상품",
    ]


@pytest.mark.asyncio
async def test_build_coverage_queries_respects_max_queries(tmp_path) -> None:
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    settings = Settings(
        product_index_seed_queries=["선크림"],
        product_index_category_queries=["틴트"],
        product_index_brand_queries=["뮤드"],
    )

    queries = await build_coverage_queries(
        settings,
        store,
        CoverageQueryOptions(coverage_pairs=10, include_gaps=False, max_queries=3),
    )
    await store.close()

    assert queries == ["선크림", "틴트", "뮤드"]
