import json
from pathlib import Path

import pytest

from app.indexing.store import SQLiteProductIndexStore
from app.models.product import ProductSourceRecord
from app.normalizer.brand import BrandResolver
from app.normalizer.product import ProductNormalizer
from app.search_engine.intent import SearchIntentExpander
from app.search_engine.query import SearchQuery
from app.search_engine.related import RelatedKeywordService
from app.search_engine.sqlite_provider import SQLiteSearchProvider
from app.search_engine.synonyms import SearchSynonymExpander
from app.service.source_policy import SourcePolicy


PROJECT_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@pytest.mark.asyncio
async def test_sqlite_provider_ranks_expanded_terms_and_allows_verified_sources(tmp_path) -> None:
    store = SQLiteProductIndexStore(tmp_path / "index.sqlite3")
    provider = _provider(store, allowed_prefixes=("oliveyoung", "hwahae"))
    await store.upsert_search_results(
        "투쿨 쉐딩",
        [
            ProductSourceRecord(
                source_brand_name="too cool for school",
                product_name_ko="믹스 블러링 볼륨 쉐딩",
                category="메이크업 > 쉐딩",
                regular_price=16000,
                rating=4.7,
                review_count=1200,
                source="hwahae",
                source_product_id="shade-1",
            ),
            ProductSourceRecord(
                source_brand_name="롬앤",
                product_name_ko="롬앤 글래스팅 컬러 글로스",
                category="메이크업 > 립글로스",
                regular_price=13000,
                source="oliveyoung",
                source_product_id="lip-1",
            ),
        ],
    )

    page = await provider.search(
        SearchQuery(text="투쿨 쉐딩", expanded_terms=["too cool for school"], limit=5)
    )

    assert page.count == 1
    assert page.provider == "sqlite"
    assert page.results[0].name == "믹스 블러링 볼륨 쉐딩"
    assert page.results[0].source == "hwahae"
    assert page.results[0].score is not None
    await store.close()


@pytest.mark.asyncio
async def test_sqlite_provider_autocomplete_and_shade_filter(tmp_path) -> None:
    store = SQLiteProductIndexStore(tmp_path / "index.sqlite3")
    provider = _provider(store)
    await store.upsert_search_results(
        "롬앤",
        [
            ProductSourceRecord(
                source_brand_name="롬앤",
                product_name_ko="롬앤 글래스팅 컬러 글로스",
                category="메이크업 > 립글로스",
                regular_price=13000,
                shade="01 피오니",
                source="oliveyoung",
                source_product_id="lip-shade",
            ),
            ProductSourceRecord(
                source_brand_name="롬앤",
                product_name_ko="롬앤 클렌징 폼",
                category="클렌징",
                regular_price=9000,
                source="oliveyoung",
                source_product_id="cleanser-no-shade",
            ),
        ],
    )

    suggestions = await provider.autocomplete("롬", 5)
    page = await provider.search(SearchQuery(text="롬앤", has_shade=True, limit=5))

    assert "롬앤" in suggestions
    assert [result.name for result in page.results] == ["롬앤 글래스팅 컬러 글로스"]
    await store.close()


def test_related_keywords_merge_synonyms_intents_and_legacy_expansions(tmp_path) -> None:
    synonyms_path = tmp_path / "synonyms.json"
    intents_path = tmp_path / "intents.json"
    synonyms_path.write_text(
        json.dumps({"여드름": ["트러블", "진정"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    intents_path.write_text(
        json.dumps(
            {
                "acne": {
                    "labels": ["여드름"],
                    "terms": ["시카", "어성초", "트러블"],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    service = RelatedKeywordService(
        SearchSynonymExpander(synonyms_path),
        SearchIntentExpander(intents_path),
    )

    related = service.related("여드름", limit=6)

    assert related[:4] == ["트러블", "진정", "시카", "어성초"]
    assert "여드름" not in related


def _provider(
    store: SQLiteProductIndexStore,
    *,
    allowed_prefixes: tuple[str, ...] = ("oliveyoung",),
) -> SQLiteSearchProvider:
    resolver = BrandResolver(PROJECT_DATA_DIR / "brand_registry.json")
    normalizer = ProductNormalizer(resolver, "https://www.oliveyoung.co.kr")
    return SQLiteSearchProvider(
        store,
        normalizer,
        source_policy=SourcePolicy(allowed_prefixes=allowed_prefixes),
    )
