import pytest

from app.cache.ttl import AsyncTTLCache
from app.data_collector.base import SearchCriteria
from app.indexing.agents import ProductIngestionAgent
from app.indexing.store import SQLiteProductIndexStore
from app.models.product import ProductSourceRecord
from app.normalizer.brand import BrandResolver
from app.normalizer.product import ProductNormalizer
from app.service.search_service import SearchService, _CollectedResult


class NetworkCollector:
    name = "network"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        self.calls.append(keyword)
        return [
            ProductSourceRecord(
                source_brand_name="BRTC",
                product_name_ko="BRTC 실시간 제품",
                regular_price=24000,
                source="oliveyoung",
                source_product_id="live-1",
            )
        ]


@pytest.mark.asyncio
async def test_product_index_keeps_official_query_rank_and_fallback_text(tmp_path) -> None:
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    records = [
        ProductSourceRecord(
            source_brand_name="뮤드",
            product_name_ko="뮤드 첫번째 상품",
            regular_price=14000,
            source="oliveyoung",
            source_product_id="A",
        ),
        ProductSourceRecord(
            source_brand_name="뮤드",
            product_name_ko="뮤드 마스카라",
            regular_price=15000,
            source="oliveyoung",
            source_product_id="B",
        ),
    ]

    await store.upsert_search_results("뮤드", records)

    ranked = await store.search("뮤드", 10)
    fallback = await store.search("마스카라", 10)
    await store.close()

    assert [record.source_product_id for record in ranked] == ["A", "B"]
    assert [record.source_product_id for record in fallback] == ["B"]


@pytest.mark.asyncio
async def test_search_service_returns_warm_index_before_network(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"mude","aliases":["뮤드"],"sources":[]}]}',
        encoding="utf-8",
    )
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    await store.upsert_search_results(
        "뮤드",
        [
            ProductSourceRecord(
                source_brand_name="뮤드",
                product_name_ko="뮤드 인덱스 상품",
                regular_price=17000,
                source="oliveyoung",
                source_product_id="indexed-1",
            )
        ],
    )
    network = NetworkCollector()
    service = SearchService(
        collectors=[network],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        product_index=store,
        index_min_results=1,
        index_background_refresh_enabled=False,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    response = await service.search("뮤드", SearchCriteria(limit=1))
    await service.close()

    assert response.count == 1
    assert response.results[0].product_name_ko == "뮤드 인덱스 상품"
    assert network.calls == []


@pytest.mark.asyncio
async def test_search_service_ingests_live_results_into_index(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    service = SearchService(
        collectors=[NetworkCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        product_index=store,
        ingestion_agent=ProductIngestionAgent(store),
        index_min_results=1,
        index_background_refresh_enabled=False,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    response = await service.search("실시간 제품", SearchCriteria(limit=10))
    await service.drain_background_tasks()
    indexed = await store.search("실시간 제품", 10)
    await service.close()

    assert response.count == 1
    assert [record.source_product_id for record in indexed] == ["live-1"]
