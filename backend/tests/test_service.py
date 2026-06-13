import asyncio
import time

import pytest

from app.cache.ttl import AsyncTTLCache
from app.data_collector.base import SearchCriteria, SourceUnavailableError
from app.indexing.agents import ProductIngestionAgent
from app.indexing.store import SQLiteProductIndexStore
from app.models.product import ProductSourceRecord
from app.normalizer.brand import BrandResolver
from app.normalizer.product import ProductNormalizer
from app.service.search_service import SearchService, _CollectedResult


class FakeCollector:
    name = "fake"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        return [
            ProductSourceRecord(
                source_brand_name="BRTC",
                product_name_ko="제품",
                regular_price=24000,
                shade=None,
                image_url=None,
                source="oliveyoung",
            )
        ]


class FailingCollector:
    name = "failing"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        raise SourceUnavailableError("blocked")


class EmptyCollector:
    name = "empty"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        return []


class SlowCollector:
    name = "slow"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        await asyncio.sleep(0.05)
        return [
            ProductSourceRecord(
                source_brand_name="BRTC",
                product_name_ko="느린 제품",
                regular_price=24000,
                source="oliveyoung",
            )
        ]


class VerySlowCollector:
    name = "very-slow"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        await asyncio.sleep(1)
        return [
            ProductSourceRecord(
                source_brand_name="BRTC",
                product_name_ko="매우 느린 제품",
                regular_price=24000,
                source="external",
            )
        ]


class IncompleteCollector:
    name = "incomplete"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        return [
            ProductSourceRecord(
                source_brand_name="한글브랜드",
                product_name_ko="제품",
                regular_price=None,
                shade=None,
                image_url=None,
                source="oliveyoung",
            )
        ]


class MissingNameCollector:
    name = "missing-name"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        return [
            ProductSourceRecord(
                source_brand_name="한글브랜드",
                product_name_ko=None,
                regular_price=12000,
                shade=None,
                image_url=None,
                source="oliveyoung",
            )
        ]


class SoldOutCollector:
    name = "sold-out"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        return [
            ProductSourceRecord(
                source_brand_name="더샘",
                product_name_ko="품절 공식 상품",
                regular_price=None,
                shade=None,
                image_url="https://example.test/item.jpg",
                source="official",
                source_url="https://example.test/product/1",
            )
        ]


class SecondFakeCollector:
    name = "second"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        return [
            ProductSourceRecord(
                source_brand_name="BRTC",
                product_name_ko="다른 제품",
                regular_price=18000,
                shade=None,
                image_url=None,
                source="external",
            )
        ]


class DuplicateFakeCollector:
    name = "duplicate"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        return [
            ProductSourceRecord(
                source_brand_name="BRTC",
                product_name_ko="제품",
                regular_price=12000,
                shade=None,
                image_url=None,
                source="external",
            )
        ]


class LimitAwareCollector:
    name = "limited"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        records = [
            ProductSourceRecord(
                source_brand_name="BRTC",
                product_name_ko="저가 제품",
                regular_price=1000,
                shade=None,
                image_url=None,
                source="oliveyoung",
            ),
            ProductSourceRecord(
                source_brand_name="BRTC",
                product_name_ko="고가 제품",
                regular_price=50000,
                shade=None,
                image_url=None,
                source="oliveyoung",
            ),
        ]
        return records[:limit]


class RelatedKeywordCollector:
    name = "related"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        if keyword != "다슈 크림":
            return []
        return [
            ProductSourceRecord(
                source_brand_name="다슈",
                product_name_ko="다슈 데일리 웨트 컬 크림 150ml",
                regular_price=25000,
                shade=None,
                image_url=None,
                source="external",
            )
        ]


class ImplicitBrandKeywordCollector:
    name = "implicit-brand"

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        self.calls.append((keyword, limit))
        if keyword != "스킨틴트" or limit < 48:
            return []
        return [
            ProductSourceRecord(
                source_brand_name="투쿨포스쿨",
                product_name_ko="베일 스킨 틴트 (+듀얼미러팔레트)",
                regular_price=24000,
                shade=None,
                image_url=None,
                source="external",
                source_url="https://example.test/products/123",
            ),
            ProductSourceRecord(
                source_brand_name="BRTC",
                product_name_ko="다른 스킨틴트",
                regular_price=18000,
                shade=None,
                image_url=None,
                source="external",
            ),
        ]


class TooCoolAliasCollector:
    name = "oliveyoung:public-api"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        self.calls.append(keyword)
        if keyword != "투쿨포스쿨":
            return []
        return [
            ProductSourceRecord(
                source_brand_name="투쿨포스쿨",
                product_name_ko=f"투쿨포스쿨 공식 검색 상품 {index}",
                regular_price=12000 + index,
                source="oliveyoung",
                source_product_id=f"too-cool-{index}",
            )
            for index in range(min(limit, 4))
        ]


class ClioBrandFallbackCollector:
    name = "oliveyoung:public-api"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        self.calls.append(keyword)
        records_by_keyword = {
            "킬커버": ProductSourceRecord(
                source_brand_name="클리오",
                product_name_ko="클리오 킬커버 하이 글로우 쿠션",
                regular_price=27000,
                source="oliveyoung",
                source_product_id="clio-kill-cover-1",
            ),
            "클리오 쿠션": ProductSourceRecord(
                source_brand_name="클리오",
                product_name_ko="클리오 쿠션 기획세트",
                regular_price=30000,
                source="oliveyoung",
                source_product_id="clio-cushion-1",
            ),
        }
        record = records_by_keyword.get(keyword)
        return [record] if record and limit > 0 else []


class CatalogJobCollector:
    name = "oliveyoung:public-api"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        self.calls.append(keyword)
        if keyword != "클리오":
            return []
        return [
            ProductSourceRecord(
                source_brand_name="클리오",
                product_name_ko="클리오 인덱스 보강 상품",
                regular_price=18000,
                source="oliveyoung",
                source_product_id="clio-catalog-1",
            )
        ][:limit]


class PartialTooCoolIndexStore:
    async def search(self, query: str, limit: int) -> list[ProductSourceRecord]:
        if query not in {"투쿨포스쿨", "too cool for school", "TOO COOL FOR SCHOOL"}:
            return []
        return [
            ProductSourceRecord(
                source_brand_name="투쿨포스쿨",
                product_name_ko="투쿨포스쿨 부분 인덱스 상품",
                regular_price=10000,
                source="oliveyoung",
                source_product_id="partial-too-cool-1",
            )
        ][:limit]

    async def upsert_search_results(
        self,
        query: str,
        records: list[ProductSourceRecord],
    ) -> None:
        return None

    async def stats(self) -> dict[str, int | str | None]:
        return {"product_count": 1, "query_count": 1, "last_refreshed_at": None}

    async def all_products(self, limit: int | None = None) -> list[ProductSourceRecord]:
        return []

    async def close(self) -> None:
        return None


class BatchKeywordCollector:
    name = "batch"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        if keyword == "메디힐 비타민씨 브라이트닝 패드":
            return [
                ProductSourceRecord(
                    source_brand_name="메디힐",
                    product_name_ko="비타민씨 브라이트닝 패드",
                    regular_price=24000,
                    shade=None,
                    image_url=None,
                    source="oliveyoung",
                )
            ]
        if keyword == "더샘 컨실러 클리어 베이지":
            return [
                ProductSourceRecord(
                    source_brand_name="더샘",
                    product_name_ko="커버 퍼펙션 팁 컨실러",
                    regular_price=6000,
                    shade="클리어 베이지",
                    image_url=None,
                    source="external",
                )
            ]
        return []


class VerifiedCacheCollector:
    name = "oliveyoung:verified-cache"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        if keyword != "메디힐 비타민씨 브라이트닝 패드":
            return []
        return [
            ProductSourceRecord(
                source_brand_name="메디힐",
                product_name_ko="비타민씨 브라이트닝 패드",
                regular_price=24000,
                shade=None,
                image_url=None,
                source="external",
            )
        ]


class RecordingNetworkCollector:
    name = "network"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        self.calls.append(keyword)
        return []


class PartialExternalBrandCollector:
    name = "external"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        if keyword != "에뛰드":
            return []
        return [
            ProductSourceRecord(
                source_brand_name="ETUDE",
                product_name_ko="에뛰드 외부 상품",
                regular_price=16000,
                shade=None,
                image_url=None,
                source="external",
            )
        ]


class BrowserOliveYoungBrandCollector:
    name = "oliveyoung:browser"

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        self.calls.append((keyword, limit))
        if keyword not in {"에뛰드", "에뛰드 마스카라"}:
            return []
        return [
            ProductSourceRecord(
                source_brand_name="에뛰드",
                product_name_ko="에뛰드 컬 픽스 마스카라",
                regular_price=15400,
                shade=None,
                image_url=None,
                source="oliveyoung",
            ),
            ProductSourceRecord(
                source_brand_name="에뛰드",
                product_name_ko="에뛰드 그림자 쉐딩",
                regular_price=16000,
                shade=None,
                image_url=None,
                source="oliveyoung",
            ),
        ]


class BrandCollisionCollector:
    name = "collision"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        return [
            ProductSourceRecord(
                source_brand_name="컬러그램",
                product_name_ko="[NEW 컬러] 뮤드 글라세 립 틴트 3종 택1",
                regular_price=17000,
                source="oliveyoung",
            ),
            ProductSourceRecord(
                source_brand_name="뮤드",
                product_name_ko="뮤드 엔젤 허그 글레이즈 10종",
                regular_price=17000,
                sale_price=12600,
                original_price=17000,
                discount_rate=25,
                source="oliveyoung",
            ),
        ]


class OfficialOrderCollector:
    name = "oliveyoung"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        if keyword != "비타 패드":
            return []
        return [
            ProductSourceRecord(
                source_brand_name="메디힐",
                product_name_ko="메디힐 비타 브라이트닝 패드",
                regular_price=24000,
                source="oliveyoung",
                source_product_id="official-1",
            ),
            ProductSourceRecord(
                source_brand_name="메디힐",
                product_name_ko="메디힐 비타 패드",
                regular_price=22000,
                source="oliveyoung",
                source_product_id="official-2",
            ),
        ][:limit]


class OliveYoungSupplementCollector:
    name = "oliveyoung:public-api"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        if keyword != "비타 패드":
            return []
        return [
            ProductSourceRecord(
                source_brand_name="메디힐",
                product_name_ko="메디힐 비타 패드",
                regular_price=19000,
                source="oliveyoung",
                source_product_id="supplement-1",
            )
        ][:limit]


class SlowOliveYoungSupplementCollector:
    name = "oliveyoung:public-api"

    def __init__(self) -> None:
        self.cancelled = False

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return [
            ProductSourceRecord(
                source_brand_name="메디힐",
                product_name_ko="느린 보조 상품",
                regular_price=19000,
                source="oliveyoung",
                source_product_id="slow-supplement-1",
            )
        ][:limit]


class SlowOfficialOrderCollector:
    name = "oliveyoung"

    def __init__(self) -> None:
        self.cancelled = False

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return []


class SlowFullOfficialGelCollector:
    name = "oliveyoung"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        await asyncio.sleep(0.02)
        if keyword != "젤":
            return []
        return [
            ProductSourceRecord(
                source_brand_name="아로마티카",
                product_name_ko="아로마티카 수딩 알로에 베라 젤 500ml",
                regular_price=18000,
                source="oliveyoung",
                source_product_id="official-gel-1",
            ),
            ProductSourceRecord(
                source_brand_name="코스알엑스",
                product_name_ko="코스알엑스 약산성 굿모닝 젤 클렌저 150ml",
                regular_price=16000,
                source="oliveyoung",
                source_product_id="official-gel-2",
            ),
        ][:limit]


class SparseOliveYoungApiGelCollector:
    name = "oliveyoung:public-api"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        if keyword != "젤":
            return []
        return [
            ProductSourceRecord(
                source_brand_name="식물나라",
                product_name_ko="식물나라 가벼운 수분 선 젤",
                regular_price=18000,
                source="oliveyoung",
                source_product_id="api-gel-1",
            )
        ][:limit]


class ExpandedOliveYoungApiGelCollector:
    name = "oliveyoung:public-api"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        self.calls.append(keyword)
        if keyword == "젤크림":
            await asyncio.sleep(1)
            return []
        records_by_keyword = {
            "젤": ProductSourceRecord(
                source_brand_name="식물나라",
                product_name_ko="식물나라 가벼운 수분 선 젤",
                regular_price=18000,
                source="oliveyoung",
                source_product_id="api-gel-1",
            ),
            "클렌징젤": ProductSourceRecord(
                source_brand_name="코스알엑스",
                product_name_ko="코스알엑스 약산성 굿모닝 젤 클렌저",
                regular_price=16000,
                source="oliveyoung",
                source_product_id="api-gel-2",
            ),
            "필링젤": ProductSourceRecord(
                source_brand_name="비플레인",
                product_name_ko="비플레인 녹두 밀크 필링 젤",
                regular_price=18000,
                source="oliveyoung",
                source_product_id="api-gel-3",
            ),
        }
        record = records_by_keyword.get(keyword)
        return [record] if record and limit > 0 else []


class TintSynonymCollector:
    name = "musinsa"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        self.calls.append(keyword)
        if keyword != "립틴트":
            return []
        return [
            ProductSourceRecord(
                source_brand_name="롬앤",
                product_name_ko="롬앤 글래스팅 립틴트",
                regular_price=13000,
                source="musinsa",
                source_product_id="musinsa-tint-1",
            )
        ][:limit]


class LotionExpansionCollector:
    name = "oliveyoung:public-api"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        self.calls.append(keyword)
        if keyword != "바디로션":
            return []
        return [
            ProductSourceRecord(
                source_brand_name="더마비",
                product_name_ko="[단독/대용량] 더마비 데일리 모이스처 바디로션 860ml",
                regular_price=23000,
                source="oliveyoung",
                source_product_id="lotion-1",
            )
        ][:limit]


class JungSaemMoolSubBrandCollector:
    name = "oliveyoung:public-api"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        self.calls.append(keyword)
        records_by_keyword = {
            "정샘물": ProductSourceRecord(
                source_brand_name="정샘물",
                product_name_ko="정샘물 스킨 세팅 베이스",
                regular_price=33000,
                source="oliveyoung",
                source_product_id="jsm-base",
            ),
            "비긴스 바이 정샘물": ProductSourceRecord(
                source_brand_name="비긴스",
                product_name_ko="[기획] 비긴스 바이 정샘물 흔적 세럼",
                regular_price=42000,
                sale_price=25990,
                original_price=42000,
                discount_rate=38,
                source="oliveyoung",
                source_product_id="begins-serum",
            ),
        }
        record = records_by_keyword.get(keyword)
        return [record] if record and limit > 0 else []


class SlowPrimaryJungSaemMoolCollector:
    name = "oliveyoung:public-api"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        if keyword == "정샘물":
            await asyncio.sleep(0.02)
            return [
                ProductSourceRecord(
                    source_brand_name="정샘물",
                    product_name_ko=f"정샘물 공식 검색 상품 {index}",
                    regular_price=30000 + index,
                    source="oliveyoung",
                    source_product_id=f"jsm-primary-{index}",
                )
                for index in range(4)
            ][:limit]
        if keyword == "비긴스 바이 정샘물":
            return [
                ProductSourceRecord(
                    source_brand_name="비긴스",
                    product_name_ko=f"비긴스 바이 정샘물 보강 상품 {index}",
                    regular_price=20000 + index,
                    source="oliveyoung",
                    source_product_id=f"jsm-fallback-{index}",
                )
                for index in range(4)
            ][:limit]
        return []


@pytest.mark.asyncio
async def test_search_service_applies_price_filter(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    service = SearchService(
        collectors=[FakeCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
    )

    response = await service.search("제품", SearchCriteria(min_price=30000, limit=24))

    assert response.count == 0
    assert response.results == []


@pytest.mark.asyncio
async def test_search_service_hides_failed_source_errors_after_fallback_success(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    service = SearchService(
        collectors=[FailingCollector(), FakeCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
    )

    response = await service.search("제품", SearchCriteria(limit=24))

    assert response.count == 1
    assert response.source_errors == []


@pytest.mark.asyncio
async def test_search_service_merges_results_from_multiple_sources(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    service = SearchService(
        collectors=[FakeCollector(), SecondFakeCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
    )

    response = await service.search("제품", SearchCriteria(limit=24))

    assert response.count == 2
    assert [result.source for result in response.results] == ["oliveyoung", "external"]
    assert [result.source_label for result in response.results] == ["Olive Young", "External source"]


@pytest.mark.asyncio
async def test_search_service_uses_source_priority_for_tied_matches(tmp_path) -> None:
    class ReversedPriorityCollector:
        name = "reversed-priority"

        async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
            return [
                ProductSourceRecord(
                    source_brand_name="BRTC",
                    product_name_ko="제품 공식몰",
                    regular_price=24000,
                    source="official",
                ),
                ProductSourceRecord(
                    source_brand_name="BRTC",
                    product_name_ko="제품 올리브영",
                    regular_price=24000,
                    source="oliveyoung",
                ),
            ]

    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    service = SearchService(
        collectors=[ReversedPriorityCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
    )

    response = await service.search("제품", SearchCriteria(limit=24))

    assert [result.source for result in response.results] == ["oliveyoung", "official"]


@pytest.mark.asyncio
async def test_search_service_returns_fast_results_before_live_deadline(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    service = SearchService(
        collectors=[SecondFakeCollector(), VerySlowCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        source_time_budget_seconds=2,
        live_collect_deadline_seconds=0.02,
    )

    started_at = time.perf_counter()
    response = await service.search("다른", SearchCriteria(limit=24))
    elapsed = time.perf_counter() - started_at

    assert elapsed < 0.5
    assert response.count == 1
    assert response.results[0].source == "external"


@pytest.mark.asyncio
async def test_search_service_can_filter_to_oliveyoung_sources_only(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    service = SearchService(
        collectors=[FakeCollector(), SecondFakeCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        allowed_result_source_prefixes=("oliveyoung",),
    )

    response = await service.search("제품", SearchCriteria(limit=24))

    assert response.count == 1
    assert response.results[0].source == "oliveyoung"


@pytest.mark.asyncio
async def test_search_service_treats_known_brand_query_as_brand_filter(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        (
            '{"entries":['
            '{"official_en":"mude","aliases":["뮤드"],"sources":[]},'
            '{"official_en":"colorgram","aliases":["컬러그램"],"sources":[]}'
            "]}"
        ),
        encoding="utf-8",
    )
    service = SearchService(
        collectors=[BrandCollisionCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        allowed_result_source_prefixes=("oliveyoung",),
    )

    response = await service.search("뮤드", SearchCriteria(limit=24))

    assert response.count == 1
    assert response.results[0].brand_ko == "뮤드"
    assert response.results[0].brand_en == "mude"
    assert response.results[0].product_name_ko == "뮤드 엔젤 허그 글레이즈 10종"


@pytest.mark.asyncio
async def test_search_service_preserves_official_oliveyoung_order(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"MEDIHEAL","aliases":["메디힐"],"sources":[]}]}',
        encoding="utf-8",
    )
    service = SearchService(
        collectors=[OfficialOrderCollector(), OliveYoungSupplementCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        prefer_live_official_results=True,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    response = await service.search("비타 패드", SearchCriteria(limit=2))

    assert response.count == 2
    assert [result.product_name_ko for result in response.results] == [
        "메디힐 비타 브라이트닝 패드",
        "메디힐 비타 패드",
    ]


@pytest.mark.asyncio
async def test_search_service_returns_primary_oliveyoung_before_slow_supplements(
    tmp_path,
) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"MEDIHEAL","aliases":["메디힐"],"sources":[]}]}',
        encoding="utf-8",
    )
    slow_supplement = SlowOliveYoungSupplementCollector()
    service = SearchService(
        collectors=[OfficialOrderCollector(), slow_supplement],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        prefer_live_official_results=True,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    started_at = time.perf_counter()
    response = await service.search("비타 패드", SearchCriteria(limit=2))
    elapsed = time.perf_counter() - started_at

    assert elapsed < 0.4
    assert response.count == 2
    assert [result.product_name_ko for result in response.results] == [
        "메디힐 비타 브라이트닝 패드",
        "메디힐 비타 패드",
    ]
    await asyncio.sleep(0)
    assert slow_supplement.cancelled is True


@pytest.mark.asyncio
async def test_search_service_returns_public_api_before_slow_official_html(
    tmp_path,
) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"MEDIHEAL","aliases":["메디힐"],"sources":[]}]}',
        encoding="utf-8",
    )
    slow_official = SlowOfficialOrderCollector()
    service = SearchService(
        collectors=[slow_official, OliveYoungSupplementCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        prefer_live_official_results=True,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    started_at = time.perf_counter()
    response = await service.search("비타 패드", SearchCriteria(limit=1))
    elapsed = time.perf_counter() - started_at

    assert elapsed < 0.4
    assert response.count == 1
    assert response.results[0].product_name_ko == "메디힐 비타 패드"
    await asyncio.sleep(0)
    assert slow_official.cancelled is True


@pytest.mark.asyncio
async def test_search_service_waits_for_primary_html_on_sparse_broad_keyword(
    tmp_path,
) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    service = SearchService(
        collectors=[SlowFullOfficialGelCollector(), SparseOliveYoungApiGelCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        preserve_official_order=True,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    response = await service.search("젤", SearchCriteria(limit=2))

    assert response.count == 2
    assert [result.product_name_ko for result in response.results] == [
        "아로마티카 수딩 알로에 베라 젤 500ml",
        "코스알엑스 약산성 굿모닝 젤 클렌저 150ml",
    ]


@pytest.mark.asyncio
async def test_search_service_keeps_related_keyword_queries_off_critical_path(
    tmp_path,
) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    collector = ExpandedOliveYoungApiGelCollector()
    service = SearchService(
        collectors=[collector],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        preserve_official_order=True,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    started_at = time.perf_counter()
    response = await service.search("젤", SearchCriteria(limit=3))
    elapsed = time.perf_counter() - started_at

    assert elapsed < 0.4
    assert response.count == 1
    assert [result.product_name_ko for result in response.results] == [
        "식물나라 가벼운 수분 선 젤",
    ]
    assert collector.calls == ["젤"]


@pytest.mark.asyncio
async def test_search_service_rescues_empty_primary_with_related_queries(
    tmp_path,
) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"rom&nd","aliases":["롬앤"],"sources":[]}]}',
        encoding="utf-8",
    )
    collector = TintSynonymCollector()
    service = SearchService(
        collectors=[collector],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
    )

    response = await service.search("틴트", SearchCriteria(limit=4))

    assert collector.calls[:2] == ["틴트", "립틴트"]
    assert response.count == 1
    assert response.results[0].product_name_ko == "롬앤 글래스팅 립틴트"


@pytest.mark.asyncio
async def test_search_service_rescues_empty_lotion_query_with_category_expansion(
    tmp_path,
) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    collector = LotionExpansionCollector()
    service = SearchService(
        collectors=[collector],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        allowed_result_source_prefixes=("oliveyoung",),
    )

    response = await service.search("로션", SearchCriteria(limit=4))

    assert "로션" in collector.calls
    assert "바디로션" in collector.calls
    assert response.count == 1
    assert response.results[0].brand_ko == "더마비"
    assert response.results[0].product_name_ko == "[단독/대용량] 더마비 데일리 모이스처 바디로션 860ml"


@pytest.mark.asyncio
async def test_search_service_keeps_source_failures_in_diagnostics_only(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    service = SearchService(
        collectors=[FailingCollector(), FakeCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
    )

    response = await service.search("제품", SearchCriteria(limit=24))
    diagnostics = service.diagnostics()

    assert response.count == 1
    assert response.source_errors == []
    assert diagnostics["metrics"]["sources"]["failing"]["failures"] == 1
    assert diagnostics["metrics"]["sources"]["fake"]["successes"] == 1


@pytest.mark.asyncio
async def test_search_service_expands_jungsaemmool_subbrand_queries(
    tmp_path,
) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        (
            '{"entries":['
            '{"official_en":"JUNGSAEMMOOL","aliases":["정샘물"],"sources":[]},'
            '{"official_en":"BEGINS BY JUNGSAEMMOOL",'
            '"aliases":["비긴스 바이 정샘물","비긴스"],"sources":[]}'
            "]}"
        ),
        encoding="utf-8",
    )
    collector = JungSaemMoolSubBrandCollector()
    service = SearchService(
        collectors=[collector],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        preserve_official_order=True,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    response = await service.search("정샘물", SearchCriteria(limit=4))

    assert "비긴스 바이 정샘물" in collector.calls
    assert response.count == 2
    assert [result.brand_ko for result in response.results] == [
        "정샘물",
        "비긴스 바이 정샘물",
    ]
    assert response.results[1].brand_en == "BEGINS BY JUNGSAEMMOOL"
    assert response.results[1].product_name_ko == "[기획] 비긴스 바이 정샘물 흔적 세럼"


@pytest.mark.asyncio
async def test_search_service_waits_for_primary_jungsaemmool_results(
    tmp_path,
) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        (
            '{"entries":['
            '{"official_en":"JUNGSAEMMOOL","aliases":["정샘물"],"sources":[]},'
            '{"official_en":"BEGINS BY JUNGSAEMMOOL",'
            '"aliases":["비긴스 바이 정샘물","비긴스"],"sources":[]}'
            "]}"
        ),
        encoding="utf-8",
    )
    service = SearchService(
        collectors=[SlowPrimaryJungSaemMoolCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        preserve_official_order=True,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    response = await service.search("정샘물", SearchCriteria(limit=4))

    assert response.count == 4
    assert [result.product_name_ko for result in response.results] == [
        "정샘물 공식 검색 상품 0",
        "정샘물 공식 검색 상품 1",
        "정샘물 공식 검색 상품 2",
        "정샘물 공식 검색 상품 3",
    ]


@pytest.mark.asyncio
async def test_search_service_dedupes_same_product_from_later_sources(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    service = SearchService(
        collectors=[FakeCollector(), DuplicateFakeCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
    )

    response = await service.search("제품", SearchCriteria(limit=24))

    assert response.count == 1
    assert response.results[0].source == "oliveyoung"
    assert response.results[0].price == 24000


@pytest.mark.asyncio
async def test_search_service_brand_filter_accepts_korean_alias(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"BRTC","aliases":["비알티씨"],"sources":[]}]}',
        encoding="utf-8",
    )
    service = SearchService(
        collectors=[FakeCollector(), SecondFakeCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
    )

    response = await service.search("제품", SearchCriteria(brand="비알티씨", limit=24))

    assert response.count == 2


@pytest.mark.asyncio
async def test_search_service_collects_more_before_filtering(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    service = SearchService(
        collectors=[LimitAwareCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
    )

    response = await service.search("제품", SearchCriteria(min_price=20000, limit=1))

    assert response.count == 1
    assert response.results[0].product_name_ko == "고가 제품"


@pytest.mark.asyncio
async def test_search_service_collects_brand_related_keyword_query(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"DASHU","aliases":["다슈"],"sources":[]}]}',
        encoding="utf-8",
    )
    service = SearchService(
        collectors=[RelatedKeywordCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
    )

    response = await service.search("크림", SearchCriteria(brand="다슈", limit=24))

    assert response.count == 1
    assert response.results[0].brand_en == "DASHU"
    assert response.results[0].product_name_ko == "다슈 데일리 웨트 컬 크림 150ml"


@pytest.mark.asyncio
async def test_search_service_infers_brand_from_query_and_returns_official_fields(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"TOO COOL FOR SCHOOL","aliases":["투쿨포스쿨"],"sources":[]}]}',
        encoding="utf-8",
    )
    collector = ImplicitBrandKeywordCollector()
    service = SearchService(
        collectors=[collector],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
    )

    response = await service.search("투쿨포스쿨 스킨틴트", SearchCriteria(limit=1))

    assert ("스킨틴트", 48) in collector.calls
    assert response.count == 1
    assert response.results[0].brand_en == "TOO COOL FOR SCHOOL"
    assert response.results[0].product_name_ko == "베일 스킨 틴트 (+듀얼미러팔레트)"
    assert response.results[0].price == 24000
    assert response.results[0].source_url == "https://example.test/products/123"


@pytest.mark.asyncio
async def test_search_service_expands_english_brand_query_to_korean_alias(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        (
            '{"entries":[{"official_en":"TOO COOL FOR SCHOOL",'
            '"aliases":["투쿨포스쿨","too cool for school"],"sources":[]}]}'
        ),
        encoding="utf-8",
    )
    collector = TooCoolAliasCollector()
    service = SearchService(
        collectors=[collector],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        preserve_official_order=True,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    response = await service.search("too cool for school", SearchCriteria(limit=4))

    assert "투쿨포스쿨" in collector.calls
    assert response.count == 4
    assert response.results[0].brand_ko == "투쿨포스쿨"
    assert response.results[0].brand_en == "TOO COOL FOR SCHOOL"


@pytest.mark.asyncio
async def test_search_service_expands_partial_english_brand_alias_query(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        (
            '{"entries":[{"official_en":"TOO COOL FOR SCHOOL",'
            '"aliases":["투쿨포스쿨","too cool for school"],"sources":[]}]}'
        ),
        encoding="utf-8",
    )
    collector = TooCoolAliasCollector()
    service = SearchService(
        collectors=[collector],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        preserve_official_order=True,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    response = await service.search("too cool", SearchCriteria(limit=4))

    assert "투쿨포스쿨" in collector.calls
    assert response.count == 4
    assert response.results[0].brand_ko == "투쿨포스쿨"
    assert response.results[0].brand_en == "TOO COOL FOR SCHOOL"


@pytest.mark.parametrize("query", ["클리오", "clio"])
@pytest.mark.asyncio
async def test_search_service_rescues_clio_brand_query_with_related_terms(
    tmp_path,
    query: str,
) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"CLIO","aliases":["클리오","CLIO"],"sources":[]}]}',
        encoding="utf-8",
    )
    collector = ClioBrandFallbackCollector()
    service = SearchService(
        collectors=[collector],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        preserve_official_order=True,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    response = await service.search(query, SearchCriteria(limit=4))

    assert "킬커버" in collector.calls
    assert response.count == 2
    assert [result.brand_en for result in response.results] == ["CLIO", "CLIO"]
    assert response.results[0].brand_ko == "클리오"


@pytest.mark.asyncio
async def test_search_service_returns_partial_brand_index_immediately(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        (
            '{"entries":[{"official_en":"TOO COOL FOR SCHOOL",'
            '"aliases":["투쿨포스쿨","too cool for school"],"sources":[]}]}'
        ),
        encoding="utf-8",
    )
    collector = TooCoolAliasCollector()
    service = SearchService(
        collectors=[collector],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        product_index=PartialTooCoolIndexStore(),
        index_min_results=1,
        preserve_official_order=True,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    response = await service.search("투쿨포스쿨", SearchCriteria(limit=4))

    assert collector.calls == []
    assert response.count == 1
    assert response.results[0].product_name_ko == "투쿨포스쿨 부분 인덱스 상품"


@pytest.mark.asyncio
async def test_search_service_records_empty_and_low_result_gaps(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    service = SearchService(
        collectors=[],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        product_index=store,
        index_background_refresh_enabled=False,
    )

    response = await service.search("없는 상품", SearchCriteria(limit=24))
    await service.drain_background_tasks()
    gaps = await service.recent_search_gaps()
    jobs = await service.recent_catalog_jobs()
    diagnostics = service.diagnostics()
    await service.close()

    assert response.count == 0
    assert gaps[0]["query"] == "없는 상품"
    assert gaps[0]["last_reason"] == "empty_result"
    assert jobs[0]["query"] == "없는 상품"
    assert jobs[0]["status"] == "pending"
    assert diagnostics["metrics"]["search_gaps"] == 1


@pytest.mark.asyncio
async def test_search_service_enqueues_low_result_index_gap(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        (
            '{"entries":[{"official_en":"TOO COOL FOR SCHOOL",'
            '"aliases":["투쿨포스쿨","too cool for school"],"sources":[]}]}'
        ),
        encoding="utf-8",
    )
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    await store.upsert_search_results(
        "투쿨포스쿨",
        [
            ProductSourceRecord(
                source_brand_name="투쿨포스쿨",
                product_name_ko="투쿨포스쿨 부분 인덱스 상품",
                regular_price=10000,
                source="oliveyoung",
                source_product_id="partial-too-cool-1",
            )
        ],
    )
    service = SearchService(
        collectors=[],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        product_index=store,
        index_background_refresh_enabled=False,
    )

    response = await service.search("투쿨포스쿨", SearchCriteria(limit=24))
    await service.drain_background_tasks()
    gaps = await service.recent_search_gaps()
    jobs = await service.recent_catalog_jobs()
    await service.close()

    assert response.count == 1
    assert gaps[0]["query"] == "투쿨포스쿨"
    assert gaps[0]["last_reason"] == "low_result_count"
    assert any(job["query"] == "투쿨포스쿨" for job in jobs)
    assert all(job["priority"] == 20 for job in jobs)


@pytest.mark.asyncio
async def test_search_service_runs_catalog_jobs_into_index(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"CLIO","aliases":["클리오","CLIO"],"sources":[]}]}',
        encoding="utf-8",
    )
    store = SQLiteProductIndexStore(tmp_path / "product_index.sqlite3")
    await store.enqueue_catalog_jobs(["클리오"], priority=10)
    collector = CatalogJobCollector()
    service = SearchService(
        collectors=[collector],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        product_index=store,
        ingestion_agent=ProductIngestionAgent(store),
        index_background_refresh_enabled=False,
        allowed_result_source_prefixes=("oliveyoung",),
    )

    summary = await service.run_catalog_jobs(max_jobs=1, limit_per_query=10)
    indexed = await store.search("클리오", 10)
    stats = await service.catalog_job_stats()
    await service.close()

    assert collector.calls == ["클리오"]
    assert summary.completed_jobs == 1
    assert summary.stored_count == 1
    assert indexed[0].product_name_ko == "클리오 인덱스 보강 상품"
    assert stats["completed"] == 1


def test_search_service_suggests_brand_aliases_and_related_terms(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        (
            '{"entries":[{"official_en":"TOO COOL FOR SCHOOL",'
            '"aliases":["투쿨포스쿨","too cool for school"],"sources":[]}]}'
        ),
        encoding="utf-8",
    )
    service = SearchService(
        collectors=[],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
    )

    assert "투쿨포스쿨" in service.suggest("투", limit=10)
    assert "TOO COOL FOR SCHOOL" in service.suggest("too", limit=10)


@pytest.mark.asyncio
async def test_search_service_handles_multiline_queries_as_one_result_each(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        (
            '{"entries":['
            '{"official_en":"MEDIHEAL","aliases":["메디힐"],"sources":[]},'
            '{"official_en":"the SAEM","aliases":["더샘"],"sources":[]}'
            "]}"
        ),
        encoding="utf-8",
    )
    service = SearchService(
        collectors=[BatchKeywordCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
    )

    response = await service.search(
        "메디힐 비타민씨 브라이트닝 패드\n더샘 컨실러 클리어 베이지",
        SearchCriteria(limit=24),
    )

    assert response.count == 2
    assert [product.brand_en for product in response.results] == ["MEDIHEAL", "the SAEM"]
    assert response.results[0].product_name_ko == "비타민씨 브라이트닝 패드"
    assert response.results[1].shade == "클리어 베이지"


@pytest.mark.asyncio
async def test_search_service_shortcuts_verified_batch_matches(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"MEDIHEAL","aliases":["메디힐"],"sources":[]}]}',
        encoding="utf-8",
    )
    network = RecordingNetworkCollector()
    service = SearchService(
        collectors=[VerifiedCacheCollector(), network],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
    )

    response = await service.search(
        "메디힐 비타민씨 브라이트닝 패드\n없는 상품",
        SearchCriteria(limit=24),
    )

    assert response.count == 1
    assert response.results[0].brand_en == "MEDIHEAL"
    assert "메디힐 비타민씨 브라이트닝 패드" not in network.calls


@pytest.mark.asyncio
async def test_search_service_uses_network_collectors_for_specific_search(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"MEDIHEAL","aliases":["메디힐"],"sources":[]}]}',
        encoding="utf-8",
    )
    network = RecordingNetworkCollector()
    service = SearchService(
        collectors=[VerifiedCacheCollector(), network],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
    )

    response = await service.search("메디힐 비타민씨 브라이트닝 패드", SearchCriteria(limit=24))

    assert response.count == 1
    assert response.results[0].brand_en == "MEDIHEAL"
    assert "메디힐 비타민씨 브라이트닝 패드" in network.calls


@pytest.mark.asyncio
async def test_search_service_returns_fast_results_without_browser_supplement(
    tmp_path,
) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"ETUDE","aliases":["에뛰드"],"sources":[]}]}',
        encoding="utf-8",
    )
    browser = BrowserOliveYoungBrandCollector()
    service = SearchService(
        collectors=[PartialExternalBrandCollector(), browser],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
    )

    response = await service.search("에뛰드", SearchCriteria(limit=48))

    assert response.count == 1
    assert response.results[0].source == "external"
    assert response.results[0].product_name_ko == "에뛰드 외부 상품"
    assert browser.calls == []


@pytest.mark.asyncio
async def test_search_service_corrects_partial_korean_brand_input_for_oliveyoung(
    tmp_path,
) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"ETUDE","aliases":["에뛰드"],"sources":[]}]}',
        encoding="utf-8",
    )
    service = SearchService(
        collectors=[BrowserOliveYoungBrandCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
    )

    response = await service.search("에뛰ㄷ 마스카라", SearchCriteria(limit=48))

    assert response.count == 1
    assert response.results[0].brand_en == "ETUDE"
    assert response.results[0].product_name_ko == "에뛰드 컬 픽스 마스카라"


@pytest.mark.asyncio
async def test_search_service_hides_failed_source_errors_after_empty_success(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    service = SearchService(
        collectors=[FailingCollector(), EmptyCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
    )

    response = await service.search("제품", SearchCriteria(limit=24))

    assert response.count == 0
    assert response.results == []
    assert response.source_errors == []


@pytest.mark.asyncio
async def test_search_service_enforces_source_time_budget(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    service = SearchService(
        collectors=[SlowCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        source_time_budget_seconds=0.001,
    )

    response = await service.search("제품", SearchCriteria(limit=24))

    assert response.count == 0
    assert response.source_errors == ["slow: request timed out"]


@pytest.mark.asyncio
async def test_search_service_keeps_results_missing_english_brand_alias(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    service = SearchService(
        collectors=[IncompleteCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
    )

    response = await service.search("제품", SearchCriteria(limit=24))

    assert response.count == 1
    assert response.results[0].brand_ko == "한글브랜드"
    assert response.results[0].brand_en is None


@pytest.mark.asyncio
async def test_search_service_filters_results_missing_product_name(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    service = SearchService(
        collectors=[MissingNameCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
    )

    response = await service.search("한글브랜드", SearchCriteria(limit=24))

    assert response.count == 0
    assert response.results == []


@pytest.mark.asyncio
async def test_search_service_keeps_sold_out_results_without_price(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"the SAEM","aliases":["더샘"],"sources":[]}]}',
        encoding="utf-8",
    )
    service = SearchService(
        collectors=[SoldOutCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
    )

    response = await service.search("더샘 품절 공식 상품", SearchCriteria(limit=24))

    assert response.count == 1
    assert response.results[0].brand_en == "the SAEM"
    assert response.results[0].price is None
