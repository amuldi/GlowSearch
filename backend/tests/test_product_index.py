import asyncio
import time

import pytest

from app.cache.ttl import AsyncTTLCache
from app.data_collector.base import SearchCriteria
from app.ingestion.export import write_products_csv
from app.ingestion.oliveyoung_pipeline import OliveYoungIngestionPipeline
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


class SlowProductIndexStore:
    async def search(self, query: str, limit: int) -> list[ProductSourceRecord]:
        await asyncio.sleep(1)
        return []

    async def upsert_search_results(
        self,
        query: str,
        records: list[ProductSourceRecord],
    ) -> None:
        return None

    async def stats(self) -> dict[str, int | str | None]:
        return {"product_count": 0, "query_count": 0, "last_refreshed_at": None}

    async def all_products(self, limit: int | None = None) -> list[ProductSourceRecord]:
        return []

    async def close(self) -> None:
        return None


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


class BroadGelCollector:
    name = "oliveyoung"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        self.calls.append(keyword)
        return [
            ProductSourceRecord(
                source_brand_name="식물나라",
                product_name_ko="식물나라 수분 젤",
                regular_price=12000,
                source="oliveyoung",
                source_product_id="gel-live-1",
            )
        ][:limit]


class FakeIngestionCollector:
    name = "oliveyoung:public-api"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        return [
            ProductSourceRecord(
                source_brand_name="뮤드",
                product_name_ko=f"뮤드 {keyword} 상품",
                category="메이크업 > 립",
                regular_price=17000,
                original_price=21000,
                sale_price=17000,
                discount_rate=19,
                rating=4.7,
                review_count=123,
                shade="02 로즈",
                description="원본 제공 설명",
                options=["01 피치", "02 로즈"],
                sold_out=False,
                image_url="https://image.oliveyoung.co.kr/item.png",
                source="oliveyoung",
                source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A1",
                source_product_id="A1",
                updated_at="2026-06-08T00:00:00+00:00",
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


def test_source_discovery_agent_caps_warmup_seeds() -> None:
    agent = SourceDiscoveryAgent(
        ["뮤드"],
        category_queries=["틴트"],
        brand_queries=["라운드랩", "메디힐"],
        max_seed_queries=2,
    )

    assert agent.seed_queries() == ["뮤드", "틴트"]


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
async def test_product_index_persists_extended_product_fields(tmp_path) -> None:
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    await store.upsert_search_results(
        "로즈 틴트",
        [
            ProductSourceRecord(
                source_brand_name="뮤드",
                product_name_ko="뮤드 로즈 틴트",
                category="메이크업 > 립",
                regular_price=17000,
                original_price=21000,
                sale_price=17000,
                discount_rate=19,
                rating=4.7,
                review_count=123,
                shade="02 로즈",
                description="원본 제공 설명",
                options=["01 피치", "02 로즈"],
                sold_out=False,
                source="oliveyoung",
                source_product_id="A1",
                updated_at="2026-06-08T00:00:00+00:00",
            )
        ],
    )

    records = await store.search("로즈", 10)
    all_records = await store.all_products()
    await store.close()

    assert len(records) == 1
    assert records[0].category == "메이크업 > 립"
    assert records[0].rating == 4.7
    assert records[0].review_count == 123
    assert records[0].description == "원본 제공 설명"
    assert records[0].options == ["01 피치", "02 로즈"]
    assert records[0].sold_out is False
    assert records[0].updated_at == "2026-06-08T00:00:00+00:00"
    assert all_records[0].source_product_id == "A1"


@pytest.mark.asyncio
async def test_ingestion_pipeline_stores_records_and_csv_export(tmp_path) -> None:
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    pipeline = OliveYoungIngestionPipeline(
        collector=FakeIngestionCollector(),
        store=store,
    )

    summary = await pipeline.ingest_queries(["틴트", "틴트", "  "], limit_per_query=10)
    records = await store.search("로즈", 10)
    csv_path = tmp_path / "products.csv"
    exported_count = write_products_csv(await store.all_products(), csv_path)
    await store.close()

    assert summary.query_count == 1
    assert summary.product_count == 1
    assert summary.stored_count == 1
    assert summary.failures == []
    assert records[0].product_name_ko == "뮤드 틴트 상품"
    assert exported_count == 1
    csv_text = csv_path.read_text(encoding="utf-8-sig")
    assert "product_id,product_name,brand_name" in csv_text
    assert "A1,뮤드 틴트 상품,뮤드" in csv_text


@pytest.mark.asyncio
async def test_search_service_returns_warm_index_before_network(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"mude","aliases":["뮤드"],"sources":[]}]}',
        encoding="utf-8",
    )
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    await store.upsert_search_results(
        "뮤드 부분 인덱스",
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
async def test_search_service_returns_partial_warm_index_before_network(tmp_path) -> None:
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
                product_name_ko="뮤드 부분 인덱스 상품",
                regular_price=17000,
                source="oliveyoung",
                source_product_id="indexed-partial-1",
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
        index_min_results=8,
        index_background_refresh_enabled=False,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    response = await service.search("뮤드 부분 인덱스", SearchCriteria(limit=8))
    await service.close()

    assert response.count == 1
    assert response.results[0].product_name_ko == "뮤드 부분 인덱스 상품"
    assert network.calls == []


@pytest.mark.asyncio
async def test_search_service_does_not_stop_at_partial_index_for_broad_single_query(
    tmp_path,
) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    await store.upsert_search_results(
        "젤",
        [
            ProductSourceRecord(
                source_brand_name="식물나라",
                product_name_ko="식물나라 부분 인덱스 젤",
                regular_price=17000,
                source="oliveyoung",
                source_product_id="indexed-partial-1",
            )
        ],
    )
    official = BroadGelCollector()
    service = SearchService(
        collectors=[official],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        product_index=store,
        index_min_results=8,
        index_background_refresh_enabled=False,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    response = await service.search("젤", SearchCriteria(limit=8))
    await service.close()

    assert response.count == 1
    assert response.results[0].product_name_ko == "식물나라 수분 젤"
    assert official.calls[0] == "젤"


@pytest.mark.asyncio
async def test_search_service_skips_slow_index_read_before_network(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    network = NetworkCollector()
    service = SearchService(
        collectors=[network],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        product_index=SlowProductIndexStore(),
        index_background_refresh_enabled=False,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    started_at = time.perf_counter()
    response = await service.search("실시간 제품", SearchCriteria(limit=8))
    elapsed = time.perf_counter() - started_at
    await service.close()

    assert elapsed < 0.8
    assert response.count == 1
    assert network.calls == ["실시간 제품"]


@pytest.mark.asyncio
async def test_search_service_returns_cached_records_before_index_or_network(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"mude","aliases":["뮤드"],"sources":[]}]}',
        encoding="utf-8",
    )
    cache = AsyncTTLCache[_CollectedResult](ttl_seconds=60)
    await cache.set(
        "뮤드:8",
        _CollectedResult(
            records=[
                ProductSourceRecord(
                    source_brand_name="뮤드",
                    product_name_ko="뮤드 캐시 상품",
                    regular_price=17000,
                    source="oliveyoung",
                    source_product_id="cached-1",
                )
            ],
            errors=[],
            has_official_records=True,
        ),
    )
    network = NetworkCollector()
    service = SearchService(
        collectors=[network],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=cache,
        index_background_refresh_enabled=False,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    response = await service.search("뮤드", SearchCriteria(limit=8))
    await service.close()

    assert response.count == 1
    assert response.results[0].product_name_ko == "뮤드 캐시 상품"
    assert network.calls == []


@pytest.mark.asyncio
async def test_search_service_trusts_cached_official_related_keyword_results(
    tmp_path,
) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"ROUND LAB","aliases":["라운드랩"],"sources":[]}]}',
        encoding="utf-8",
    )
    cache = AsyncTTLCache[_CollectedResult](ttl_seconds=60)
    await cache.set(
        "히알루론산:8",
        _CollectedResult(
            records=[
                ProductSourceRecord(
                    source_brand_name="라운드랩",
                    product_name_ko="라운드랩 수분 장벽 크림",
                    regular_price=24000,
                    source="oliveyoung",
                    source_product_id="related-cached-1",
                )
            ],
            errors=[],
            has_official_records=True,
        ),
    )
    network = NetworkCollector()
    service = SearchService(
        collectors=[network],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=cache,
        index_background_refresh_enabled=False,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    response = await service.search("히알루론산", SearchCriteria(limit=8))
    await service.close()

    assert response.count == 1
    assert response.results[0].product_name_ko == "라운드랩 수분 장벽 크림"
    assert network.calls == ["히알루론산"]


@pytest.mark.asyncio
async def test_search_service_trusts_indexed_official_related_keyword_results(
    tmp_path,
) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"ROUND LAB","aliases":["라운드랩"],"sources":[]}]}',
        encoding="utf-8",
    )
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    await store.upsert_search_results(
        "히알루론산",
        [
            ProductSourceRecord(
                source_brand_name="라운드랩",
                product_name_ko="라운드랩 수분 장벽 크림",
                regular_price=24000,
                source="oliveyoung",
                source_product_id="related-indexed-1",
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

    response = await service.search("히알루론산", SearchCriteria(limit=8))
    await service.close()

    assert response.count == 1
    assert response.results[0].product_name_ko == "라운드랩 수분 장벽 크림"
    assert network.calls == ["히알루론산"]


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
async def test_search_service_schedules_custom_warm_index_queries(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    service = SearchService(
        collectors=[OfficialCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        product_index=store,
        ingestion_agent=ProductIngestionAgent(store),
        source_discovery_agent=SourceDiscoveryAgent(["선크림"]),
        index_warmup_concurrency=1,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    scheduled = service.schedule_warm_index(["뮤드", "뮤드"], limit=1)
    await service.drain_background_tasks()
    indexed = await store.search("뮤드", 10)
    await service.close()

    assert scheduled == 1
    assert [record.source_product_id for record in indexed] == ["official-live-1"]


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
