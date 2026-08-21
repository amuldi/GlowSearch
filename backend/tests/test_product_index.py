import asyncio
import time
from datetime import UTC, datetime, timedelta

import pytest

from app.cache.ttl import AsyncTTLCache
from app.data_collector.base import SearchCriteria
from app.ingestion.export import write_products_csv
from app.ingestion.oliveyoung_pipeline import OliveYoungIngestionPipeline
from app.indexing.agents import ProductIngestionAgent, SourceDiscoveryAgent
from app.indexing.store import SQLiteProductIndexStore
from app.models.product import ProductSourceRecord
from app.normalizer.brand import BrandAlias
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

    async def search_mapped(self, query: str, limit: int) -> list[ProductSourceRecord]:
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


class FastVerifiedGelCollector:
    name = "oliveyoung:verified-cache"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        return [
            ProductSourceRecord(
                source_brand_name="식물나라",
                product_name_ko="식물나라 부분 캐시 젤",
                regular_price=17000,
                source="oliveyoung",
                source_product_id="verified-gel-1",
            )
        ][:limit]


class SlowPublicGelCollector:
    name = "oliveyoung:public-api"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        self.calls.append(keyword)
        await asyncio.sleep(0.05)
        return [
            ProductSourceRecord(
                source_brand_name="홀리카홀리카",
                product_name_ko="홀리카홀리카 젤테일 아이섀도우",
                regular_price=4900,
                source="oliveyoung",
                source_product_id="public-gel-1",
            ),
            ProductSourceRecord(
                source_brand_name="에스네이처",
                product_name_ko="에스네이처 수분 젤크림",
                regular_price=22900,
                source="oliveyoung",
                source_product_id="public-gel-2",
            ),
        ][:limit]


class SlowEmptyPublicCollector:
    name = "oliveyoung:public-api"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        self.calls.append(keyword)
        await asyncio.sleep(1)
        return []


class BackgroundExpandedGelCollector:
    name = "oliveyoung:public-api"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        self.calls.append(keyword)
        records_by_keyword = {
            "젤": ProductSourceRecord(
                source_brand_name="식물나라",
                product_name_ko="식물나라 수분 젤",
                regular_price=12000,
                source="oliveyoung",
                source_product_id="expanded-gel-1",
            ),
            "클렌징젤": ProductSourceRecord(
                source_brand_name="코스알엑스",
                product_name_ko="코스알엑스 약산성 굿모닝 젤 클렌저",
                regular_price=16000,
                source="oliveyoung",
                source_product_id="expanded-gel-2",
            ),
        }
        record = records_by_keyword.get(keyword)
        return [record] if record and limit > 0 else []


class LimitRecordingRefreshCollector:
    name = "oliveyoung:public-api"

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        self.calls.append((keyword, limit))
        return [
            ProductSourceRecord(
                source_brand_name="라운드랩",
                product_name_ko="라운드랩 백그라운드 보강 상품",
                regular_price=24000,
                source="oliveyoung",
                source_product_id="background-refresh-1",
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
                search_keywords=["로즈 별칭", "편집자 키워드"],
                sold_out=False,
                image_url="https://image.oliveyoung.co.kr/item.png",
                source="oliveyoung",
                source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A1",
                source_product_id="A1",
                updated_at="2026-06-08T00:00:00+00:00",
            )
        ][:limit]


class VerifiedCatalogBackfillCollector:
    name = "oliveyoung:verified-cache"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        return []

    async def all_records(self, limit: int | None = None) -> list[ProductSourceRecord]:
        records = [
            ProductSourceRecord(
                source_brand_name="롬앤",
                source_brand_name_en="rom&nd",
                product_name_ko="롬앤 베러 댄 쉐입 쉐딩",
                product_name_display_ko="베러 댄 쉐입 쉐딩",
                product_name_display_en="Better Than Shape Shading",
                regular_price=9900,
                shade=None,
                source="oliveyoung",
                source_url="https://oliveyoung.example/products/shading",
                source_product_id="A000000135220",
                search_keywords=["그레이쿨", "베러 댄 쉐입 쉐딩"],
            )
        ]
        if limit is not None and limit > 0:
            return records[:limit]
        return records


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
                search_keywords=["로즈 별칭", "편집자 키워드"],
                sold_out=False,
                source="oliveyoung",
                source_product_id="A1",
                updated_at="2026-06-08T00:00:00+00:00",
            )
        ],
    )

    records = await store.search("로즈", 10)
    keyword_records = await store.search("편집자 키워드", 10)
    all_records = await store.all_products()
    await store.close()

    assert len(records) == 1
    assert records[0].category == "메이크업 > 립"
    assert records[0].rating == 4.7
    assert records[0].review_count == 123
    assert records[0].description == "원본 제공 설명"
    assert records[0].options == ["01 피치", "02 로즈"]
    assert records[0].search_keywords == ["로즈 별칭", "편집자 키워드"]
    assert [record.source_product_id for record in keyword_records] == ["A1"]
    assert records[0].sold_out is False
    assert records[0].updated_at == "2026-06-08T00:00:00+00:00"
    assert all_records[0].source_product_id == "A1"


@pytest.mark.asyncio
async def test_product_index_preserves_decimal_source_prices(tmp_path) -> None:
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    await store.upsert_search_results(
        "speedy skinny brow",
        [
            ProductSourceRecord(
                source_brand_name="페리페라",
                source_brand_name_en="Peripera",
                product_name_ko="[6월 올영픽] 페리페라 스피디 스키니 브로우 8 Colors (단품/더블)",
                product_name_en="[PERIPERA] Speedy Skinny Brow",
                product_name_display_ko="스피디 스키니 브로우",
                product_name_display_en="Speedy Skinny Brow",
                regular_price=8.59,
                currency="USD",
                source="official",
                source_url="https://clubclio.shop/products/peripera-speedy-skinny-brow",
                source_product_id="4601270435977",
            )
        ],
    )

    records = await store.search("speedy skinny brow", 10)
    all_records = await store.all_products()
    await store.close()

    assert records[0].regular_price == 8.59
    assert all_records[0].regular_price == 8.59
    assert records[0].currency == "USD"
    assert records[0].product_name_display_ko == "스피디 스키니 브로우"
    assert records[0].product_name_display_en == "Speedy Skinny Brow"
    assert all_records[0].product_name_display_ko == "스피디 스키니 브로우"


@pytest.mark.asyncio
async def test_product_index_searches_product_display_names(tmp_path) -> None:
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    await store.upsert_search_results(
        "peripera brow",
        [
            ProductSourceRecord(
                source_brand_name="페리페라",
                source_brand_name_en="peripera",
                product_name_ko="[6월 올영픽] 페리페라 스피디 스키니 브로우 8 Colors (단품/더블)",
                product_name_display_ko="스피디 스키니 브로우",
                source="oliveyoung",
                source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000000001",
                source_product_id="A000000000001",
            )
        ],
    )

    records = await store.search("스피디 스키니 브로우", 10)
    await store.close()

    assert records[0].product_name_display_ko == "스피디 스키니 브로우"
    assert records[0].source_product_id == "A000000000001"


@pytest.mark.asyncio
async def test_search_service_backfills_verified_catalog_into_index(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    service = SearchService(
        collectors=[VerifiedCatalogBackfillCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        product_index=store,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    count = await service.backfill_verified_catalog()
    records = await store.search("그레이쿨", 10)
    await service.close()

    assert count == 1
    assert [record.source_product_id for record in records] == ["A000000135220"]
    assert records[0].search_keywords == ["그레이쿨", "베러 댄 쉐입 쉐딩"]
    assert records[0].product_name_display_ko == "베러 댄 쉐입 쉐딩"
    assert records[0].product_name_display_en == "Better Than Shape Shading"


@pytest.mark.asyncio
async def test_product_index_searches_fts_terms_and_brand_aliases(tmp_path) -> None:
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    await store.upsert_brand_aliases(
        [
            BrandAlias(official_en="TOO COOL FOR SCHOOL", alias="투쿨포스쿨"),
            BrandAlias(official_en="TOO COOL FOR SCHOOL", alias="too cool for school"),
            BrandAlias(official_en="Derma:B", alias="더마비"),
            BrandAlias(official_en="Derma:B", alias="Derma:B"),
        ]
    )
    await store.upsert_search_results(
        "초기",
        [
            ProductSourceRecord(
                source_brand_name="투쿨포스쿨",
                product_name_ko="투쿨포스쿨 디테일링 메탈 마스카라",
                regular_price=16000,
                source="oliveyoung",
                source_product_id="too-cool-1",
            ),
            ProductSourceRecord(
                source_brand_name="더마비",
                product_name_ko="[단독/대용량] 더마비 데일리 모이스처 바디로션 860ml",
                regular_price=23000,
                source="oliveyoung",
                source_product_id="dermab-1",
            ),
        ],
    )

    english_brand = await store.search("too cool", 10)
    partial_category = await store.search("로션", 10)
    await store.close()

    assert [record.source_product_id for record in english_brand] == ["too-cool-1"]
    assert [record.source_product_id for record in partial_category] == ["dermab-1"]


@pytest.mark.asyncio
async def test_product_index_records_search_gaps(tmp_path) -> None:
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")

    await store.record_search_gap("없는 상품", result_count=0, reason="empty_result")
    await store.record_search_gap("없는 상품", result_count=1, reason="low_result_count")
    stats = await store.stats()
    gaps = await store.recent_search_gaps()
    await store.close()

    assert stats["search_gap_count"] == 1
    assert stats["last_search_gap_at"] is not None
    assert gaps[0]["query"] == "없는 상품"
    assert gaps[0]["result_count"] == 1
    assert gaps[0]["miss_count"] == 2
    assert gaps[0]["last_reason"] == "low_result_count"


@pytest.mark.asyncio
async def test_product_index_catalog_jobs_are_claimed_and_completed(tmp_path) -> None:
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")

    enqueued = await store.enqueue_catalog_jobs(
        ["로션", "로션", "틴트"],
        priority=20,
        max_attempts=2,
    )
    claimed = await store.claim_catalog_jobs(limit=1)
    await store.complete_catalog_job(
        claimed[0].id,
        status="completed",
        product_count=12,
    )
    stats = await store.catalog_job_stats()
    recent = await store.recent_catalog_jobs()
    await store.close()

    assert enqueued == 2
    assert claimed[0].query == "로션"
    assert claimed[0].status == "running"
    assert claimed[0].attempt_count == 1
    assert stats["completed"] == 1
    assert stats["pending"] == 1
    assert recent[0]["status"] == "completed"
    assert recent[0]["product_count"] == 12


@pytest.mark.asyncio
async def test_product_index_resets_stale_running_catalog_jobs(tmp_path) -> None:
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    await store.enqueue_catalog_jobs(["오래된 작업", "최근 작업"], priority=20, max_attempts=2)
    claimed = await store.claim_catalog_jobs(limit=2)
    old_started_at = (datetime.now(tz=UTC) - timedelta(hours=2)).isoformat()
    recent_started_at = datetime.now(tz=UTC).isoformat()
    store._connection.execute(  # noqa: SLF001 - direct timestamp setup keeps this storage test focused.
        "UPDATE catalog_jobs SET started_at = ? WHERE id = ?",
        (old_started_at, claimed[0].id),
    )
    store._connection.execute(  # noqa: SLF001
        "UPDATE catalog_jobs SET started_at = ? WHERE id = ?",
        (recent_started_at, claimed[1].id),
    )
    store._connection.commit()  # noqa: SLF001

    reset_count = await store.reset_stale_catalog_jobs(older_than_minutes=30)
    stats = await store.catalog_job_stats()
    reclaimed = await store.claim_catalog_jobs(limit=1)
    await store.close()

    assert reset_count == 1
    assert stats["pending"] == 1
    assert stats["running"] == 1
    assert reclaimed[0].query == "오래된 작업"
    assert reclaimed[0].attempt_count == 2


@pytest.mark.asyncio
async def test_ingestion_pipeline_runs_catalog_jobs(tmp_path) -> None:
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    await store.enqueue_catalog_jobs(["틴트"], priority=10)
    pipeline = OliveYoungIngestionPipeline(
        collector=FakeIngestionCollector(),
        store=store,
        ingestion_agent=ProductIngestionAgent(store),
    )

    summary = await pipeline.ingest_catalog_jobs(max_jobs=5, limit_per_query=10)
    records = await store.search("로즈", 10)
    stats = await store.catalog_job_stats()
    await store.close()

    assert summary.job_count == 1
    assert summary.completed_jobs == 1
    assert summary.failed_jobs == 0
    assert records[0].product_name_ko == "뮤드 틴트 상품"
    assert stats["completed"] == 1


@pytest.mark.asyncio
async def test_product_ingestion_agent_normalizes_records_before_indexing(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"BEYOND","aliases":["비욘드"],"sources":[]}]}',
        encoding="utf-8",
    )
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )
    agent = ProductIngestionAgent(store, normalizer=normalizer)

    await agent.ingest_search_results(
        ["수분"],
        [
            ProductSourceRecord(
                source_brand_name="비욘드",
                product_name_ko="[NEW] 비욘드 엔젤 아쿠아 이온 히알루 10% 수분 로션 200ml",
                source="oliveyoung",
                source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000257196",
                source_product_id="A000000257196",
            )
        ],
    )
    records = await store.search("비욘드 수분", 5)
    await store.close()
    normalizer.close()

    assert records[0].source_brand_name == "비욘드"
    assert records[0].source_brand_name_en == "BEYOND"


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
async def test_search_service_uses_fts_index_after_empty_network(tmp_path) -> None:
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
    assert network.calls == ["뮤드"]


@pytest.mark.asyncio
async def test_search_service_bounds_slow_full_index_fallback(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    service = SearchService(
        collectors=[],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        product_index=SlowProductIndexStore(),
        index_background_refresh_enabled=False,
    )

    started_at = time.monotonic()
    response = await service.search("없는 상품", SearchCriteria(limit=24))
    elapsed = time.monotonic() - started_at
    await service.close()

    assert response.count == 0
    assert elapsed < 0.8


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
async def test_search_service_uses_live_source_for_partial_broad_single_query(
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
    assert official.calls == ["젤"]


@pytest.mark.asyncio
async def test_search_service_uses_live_source_for_partial_benefit_query(
    tmp_path,
) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    await store.upsert_search_results(
        "수분",
        [
            ProductSourceRecord(
                source_brand_name="식물나라",
                product_name_ko="식물나라 부분 인덱스 수분 젤",
                regular_price=17000,
                source="oliveyoung",
                source_product_id="indexed-moisture-1",
            )
        ],
    )

    class MoistureCollector:
        name = "oliveyoung:public-api"

        def __init__(self) -> None:
            self.calls: list[str] = []

        async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
            self.calls.append(keyword)
            return [
                ProductSourceRecord(
                    source_brand_name=f"브랜드{index}",
                    product_name_ko=f"브랜드{index} 수분 크림",
                    regular_price=12000 + index,
                    source="oliveyoung",
                    source_product_id=f"moisture-live-{index}",
                )
                for index in range(limit)
            ]

    collector = MoistureCollector()
    service = SearchService(
        collectors=[collector],
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

    response = await service.search("수분", SearchCriteria(limit=5))
    await service.close()

    assert collector.calls == ["수분"]
    assert response.count == 5
    assert [result.source_product_id for result in response.results] == [
        "moisture-live-0",
        "moisture-live-1",
        "moisture-live-2",
        "moisture-live-3",
        "moisture-live-4",
    ]


@pytest.mark.asyncio
async def test_search_service_uses_full_index_for_sufficient_benefit_query(
    tmp_path,
) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    await store.upsert_search_results(
        "수분",
        [
            ProductSourceRecord(
                source_brand_name=f"브랜드{index}",
                product_name_ko=f"브랜드{index} 수분 크림",
                regular_price=12000 + index,
                source="oliveyoung",
                source_product_id=f"indexed-moisture-{index}",
            )
            for index in range(5)
        ],
    )

    class UnusedCollector:
        name = "oliveyoung:public-api"

        def __init__(self) -> None:
            self.calls: list[str] = []

        async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
            self.calls.append(keyword)
            return []

    collector = UnusedCollector()
    service = SearchService(
        collectors=[collector],
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

    response = await service.search("수분", SearchCriteria(limit=5))
    await service.close()

    assert collector.calls == []
    assert response.count == 5
    assert [result.source_product_id for result in response.results] == [
        "indexed-moisture-0",
        "indexed-moisture-1",
        "indexed-moisture-2",
        "indexed-moisture-3",
        "indexed-moisture-4",
    ]


@pytest.mark.asyncio
async def test_search_service_waits_for_public_api_after_verified_benefit_hit(
    tmp_path,
) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")

    class FastVerifiedMoistureCollector:
        name = "oliveyoung:verified-cache"

        async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
            return [
                ProductSourceRecord(
                    source_brand_name="식물나라",
                    product_name_ko="식물나라 가벼운 수분 선 젤",
                    regular_price=25800,
                    source="oliveyoung",
                    source_product_id="verified-moisture-1",
                )
            ][:limit]

    class SlowPublicMoistureCollector:
        name = "oliveyoung:public-api"

        def __init__(self) -> None:
            self.calls: list[str] = []

        async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
            self.calls.append(keyword)
            await asyncio.sleep(0.02)
            return [
                ProductSourceRecord(
                    source_brand_name=f"브랜드{index}",
                    product_name_ko=f"브랜드{index} 수분 크림",
                    regular_price=12000 + index,
                    source="oliveyoung",
                    source_product_id=f"public-moisture-{index}",
                )
                for index in range(limit)
            ]

    public = SlowPublicMoistureCollector()
    service = SearchService(
        collectors=[FastVerifiedMoistureCollector(), public],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        index_background_refresh_enabled=False,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    response = await service.search("수분", SearchCriteria(limit=5))
    await service.close()

    assert public.calls == ["수분"]
    assert response.count == 5
    assert response.results[0].source_product_id == "public-moisture-0"


@pytest.mark.asyncio
async def test_search_service_returns_partial_index_for_specific_single_query(
    tmp_path,
) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    await store.upsert_search_results(
        "클렌징젤",
        [
            ProductSourceRecord(
                source_brand_name="아벤느",
                product_name_ko="아벤느 클리낭스 클렌징 젤 400ml",
                regular_price=20900,
                source="oliveyoung",
                source_product_id="indexed-cleanser-gel-1",
            ),
            ProductSourceRecord(
                source_brand_name="제로이드",
                product_name_ko="제로이드 더마뉴얼 클렌징젤 200ml",
                regular_price=22000,
                source="oliveyoung",
                source_product_id="indexed-cleanser-gel-2",
            ),
        ],
    )
    public = SlowEmptyPublicCollector()
    service = SearchService(
        collectors=[public],
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

    started_at = time.perf_counter()
    response = await service.search("클렌징젤", SearchCriteria(limit=4))
    elapsed = time.perf_counter() - started_at
    await service.close()

    assert elapsed < 0.4
    assert response.count == 2
    assert public.calls == []
    assert [product.product_name_ko for product in response.results] == [
        "아벤느 클리낭스 클렌징 젤 400ml",
        "제로이드 더마뉴얼 클렌징젤 200ml",
    ]


@pytest.mark.asyncio
async def test_search_service_does_not_cancel_public_source_after_fast_verified_hit(
    tmp_path,
) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    public = SlowPublicGelCollector()
    service = SearchService(
        collectors=[FastVerifiedGelCollector(), public],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        index_background_refresh_enabled=False,
        live_collect_deadline_seconds=0.5,
        live_first_result_grace_seconds=0.01,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    response = await service.search("젤", SearchCriteria(limit=2))
    await service.close()

    assert response.count == 2
    assert [product.product_name_ko for product in response.results] == [
        "홀리카홀리카 젤테일 아이섀도우",
        "에스네이처 수분 젤크림",
    ]
    assert public.calls[0] == "젤"


@pytest.mark.asyncio
async def test_search_service_refreshes_related_queries_in_background(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    collector = BackgroundExpandedGelCollector()
    service = SearchService(
        collectors=[collector],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        product_index=store,
        ingestion_agent=ProductIngestionAgent(store),
        index_background_refresh_enabled=True,
        background_collect_deadline_seconds=1.0,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    response = await service.search("젤", SearchCriteria(limit=1))
    await service.drain_background_tasks()
    indexed = await store.search("클렌징젤", 10)
    await service.close()

    assert response.count == 1
    assert response.results[0].product_name_ko == "식물나라 수분 젤"
    assert "클렌징젤" in collector.calls
    assert indexed[0].product_name_ko == "코스알엑스 약산성 굿모닝 젤 클렌저"


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
        # This test targets the index-read-timeout -> live-collect fallback
        # specifically, not the ordinary-query deferral added alongside it.
        defer_ordinary_query_live_collect=False,
    )

    started_at = time.perf_counter()
    response = await service.search("실시간 제품", SearchCriteria(limit=8))
    elapsed = time.perf_counter() - started_at
    await service.close()

    assert elapsed < 0.8
    assert response.count == 1
    assert network.calls == ["실시간 제품"]


@pytest.mark.asyncio
async def test_search_service_returns_partial_cached_brand_records_immediately(tmp_path) -> None:
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
async def test_search_service_returns_cached_official_related_keyword_results_immediately(
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
    assert network.calls == []


@pytest.mark.asyncio
async def test_search_service_uses_larger_background_refresh_limit(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"ROUND LAB","aliases":["라운드랩"],"sources":[]}]}',
        encoding="utf-8",
    )
    cache = AsyncTTLCache[_CollectedResult](ttl_seconds=60)
    await cache.set(
        "히알루론산:1",
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
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    collector = LimitRecordingRefreshCollector()
    service = SearchService(
        collectors=[collector],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=cache,
        product_index=store,
        ingestion_agent=ProductIngestionAgent(store),
        index_background_refresh_enabled=True,
        index_background_refresh_limit=12,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    response = await service.search("히알루론산", SearchCriteria(limit=1))
    await service.drain_background_tasks()
    await service.close()

    assert response.count == 1
    assert collector.calls == [("히알루론산", 12)]


@pytest.mark.asyncio
async def test_search_service_returns_indexed_official_related_keyword_results_immediately(
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
        # This test targets live-result-ingestion-into-index specifically, not
        # the ordinary-query deferral added alongside it.
        defer_ordinary_query_live_collect=False,
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


# --- product_offers persistence (milestone 2) ---


@pytest.mark.asyncio
async def test_product_offers_persist_on_first_ingest(tmp_path) -> None:
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    await store.upsert_search_results(
        "로션",
        [
            ProductSourceRecord(
                canonical_product_id="verified-lotion-1",
                source_brand_name="새브랜드",
                product_name_ko="새브랜드 로션",
                source="oliveyoung",
                source_product_id="offer-1",
                source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=offer-1",
                original_price=20000,
                sale_price=15000,
                currency="KRW",
                image_url="https://image.example/offer-1.jpg",
                sold_out=False,
                updated_at="2026-08-10T00:00:00+00:00",
            )
        ],
    )
    offers = await store.get_offers(["verified-lotion-1"])
    await store.close()

    assert [offer.source for offer in offers["verified-lotion-1"]] == ["oliveyoung"]
    offer = offers["verified-lotion-1"][0]
    assert offer.source_product_id == "offer-1"
    assert (
        offer.source_url
        == "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=offer-1"
    )
    assert offer.original_price == 20000
    assert offer.sale_price == 15000
    assert offer.price == 15000  # derived: sale_price wins when present
    assert offer.sold_out is False
    assert offer.updated_at == "2026-08-10T00:00:00+00:00"


@pytest.mark.asyncio
async def test_product_offers_reingest_updates_in_place_without_duplicating(tmp_path) -> None:
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    base_record = ProductSourceRecord(
        canonical_product_id="verified-lotion-1",
        source_brand_name="새브랜드",
        product_name_ko="새브랜드 로션",
        source="oliveyoung",
        source_product_id="offer-1",
        source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=offer-1",
        original_price=20000,
        sale_price=15000,
        image_url="https://image.example/offer-1.jpg",
        sold_out=False,
    )
    await store.upsert_search_results("로션", [base_record])

    # Re-ingest: the sale ended (sale_price -> None, should overwrite to None),
    # a new URL is reported (should overwrite), but this pass didn't capture an
    # image (None should NOT clobber the previously known-good image_url).
    await store.upsert_search_results(
        "로션",
        [
            base_record.model_copy(
                update={
                    "source_url": "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=offer-1&v=2",
                    "sale_price": None,
                    "image_url": None,
                    "sold_out": True,
                }
            )
        ],
    )
    offers = await store.get_offers(["verified-lotion-1"])
    stats = await store.stats()
    await store.close()

    assert len(offers["verified-lotion-1"]) == 1  # no duplicate row
    offer = offers["verified-lotion-1"][0]
    assert offer.source_url.endswith("v=2")  # URL updated
    assert offer.sale_price is None  # promotion ending is a meaningful overwrite
    assert offer.price == 20000  # derived price falls back to original_price
    assert (
        offer.image_url == "https://image.example/offer-1.jpg"
    )  # preserved, not clobbered by None
    assert offer.sold_out is True
    assert stats["offer_count"] == 1


@pytest.mark.asyncio
async def test_product_offers_excluded_without_source_product_id(tmp_path) -> None:
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    await store.upsert_search_results(
        "로션",
        [
            ProductSourceRecord(
                canonical_product_id="verified-lotion-2",
                source_brand_name="새브랜드",
                product_name_ko="새브랜드 크림",
                source="oliveyoung",
                source_product_id=None,
                source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=unknown",
                original_price=10000,
            )
        ],
    )
    offers = await store.get_offers(["verified-lotion-2"])
    stats = await store.stats()
    indexed = await store.search("로션", 10)
    await store.close()

    # No offer row was written (no stable per-retailer id to key on)...
    assert offers.get("verified-lotion-2") is None
    assert stats["offer_count"] == 0
    # ...but the record itself is still indexed as before (unchanged behavior).
    assert any(record.canonical_product_id == "verified-lotion-2" for record in indexed)


@pytest.mark.asyncio
async def test_product_offers_do_not_silently_relink_on_canonical_conflict(tmp_path) -> None:
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    await store.upsert_search_results(
        "로션",
        [
            ProductSourceRecord(
                canonical_product_id="verified-lotion-1",
                source="oliveyoung",
                source_product_id="offer-1",
                source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=offer-1",
                original_price=20000,
            )
        ],
    )
    # Same (source, source_product_id) but a *different* canonical_product_id —
    # must not silently move the offer to a different product.
    await store.upsert_search_results(
        "로션",
        [
            ProductSourceRecord(
                canonical_product_id="verified-lotion-99",
                source="oliveyoung",
                source_product_id="offer-1",
                source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=offer-1",
                original_price=999,
            )
        ],
    )
    offers_original = await store.get_offers(["verified-lotion-1"])
    offers_conflicting = await store.get_offers(["verified-lotion-99"])
    stats = await store.stats()
    await store.close()

    assert len(offers_original["verified-lotion-1"]) == 1
    assert offers_original["verified-lotion-1"][0].original_price == 20000  # untouched
    assert offers_conflicting.get("verified-lotion-99") is None  # never linked
    assert stats["offer_canonical_conflicts"] == 1


@pytest.mark.asyncio
async def test_product_offers_survive_store_close_and_reopen(tmp_path) -> None:
    db_path = tmp_path / "product_index.sqlite3"
    store = SQLiteProductIndexStore(db_path)
    await store.upsert_search_results(
        "로션",
        [
            ProductSourceRecord(
                canonical_product_id="verified-lotion-1",
                source="oliveyoung",
                source_product_id="offer-1",
                source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=offer-1",
                original_price=20000,
            )
        ],
    )
    await store.close()

    reopened = SQLiteProductIndexStore(db_path)
    offers = await reopened.get_offers(["verified-lotion-1"])
    await reopened.close()

    assert offers["verified-lotion-1"][0].source_product_id == "offer-1"
    assert offers["verified-lotion-1"][0].original_price == 20000
