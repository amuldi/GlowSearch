import pytest

from app.cache.ttl import AsyncTTLCache
from app.data_collector.base import SearchCriteria
from app.indexing.agents import ProductIngestionAgent, SourceDiscoveryAgent
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


class OfficialCollector:
    name = "oliveyoung"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        self.calls.append(keyword)
        return [
            ProductSourceRecord(
                source_brand_name="뮤드",
                product_name_ko="뮤드 공식 최신 상품",
                regular_price=14000,
                source="oliveyoung",
                source_product_id="official-live-1",
            )
        ][:limit]


class FakeDetailEnricher:
    async def enrich(self, records: list[ProductSourceRecord]) -> list[ProductSourceRecord]:
        return [
            record.model_copy(
                update={
                    "source_brand_name": record.source_brand_name or "뮤드",
                    "product_name_ko": record.product_name_ko or "뮤드 상세 상품명",
                    "regular_price": 12600,
                    "original_price": 17000,
                    "sale_price": 12600,
                    "discount_rate": 25,
                }
            )
            for record in records
        ]


def test_source_discovery_agent_combines_brand_category_and_product_seeds() -> None:
    agent = SourceDiscoveryAgent(
        ["뮤드", "  "],
        category_queries=["틴트", "뮤드"],
        brand_queries=["라운드랩", "틴트"],
    )

    assert agent.seed_queries() == ["뮤드", "틴트", "라운드랩"]
    assert agent.category_queries() == ["틴트", "뮤드"]
    assert agent.brand_queries() == ["라운드랩", "틴트"]


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
async def test_search_service_prefers_live_official_results_over_warm_index(tmp_path) -> None:
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
                product_name_ko="뮤드 인덱스 이전 상품",
                regular_price=17000,
                source="oliveyoung",
                source_product_id="indexed-old-1",
            )
        ],
    )
    official = OfficialCollector()
    service = SearchService(
        collectors=[official],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        product_index=store,
        index_min_results=1,
        index_background_refresh_enabled=False,
        prefer_live_official_results=True,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    response = await service.search("뮤드", SearchCriteria(limit=1))
    await service.close()

    assert response.count == 1
    assert response.results[0].product_name_ko == "뮤드 공식 최신 상품"
    assert official.calls == ["뮤드"]


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


@pytest.mark.asyncio
async def test_product_ingestion_enriches_details_before_indexing(tmp_path) -> None:
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    agent = ProductIngestionAgent(store, detail_enricher=FakeDetailEnricher())

    await agent.ingest_search_results(
        ["뮤드"],
        [
            ProductSourceRecord(
                source="oliveyoung",
                source_product_id="detail-1",
                source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do",
            )
        ],
    )
    indexed = await store.search("뮤드", 10)
    await store.close()

    assert len(indexed) == 1
    assert indexed[0].source_brand_name == "뮤드"
    assert indexed[0].product_name_ko == "뮤드 상세 상품명"
    assert indexed[0].original_price == 17000
    assert indexed[0].sale_price == 12600
