import asyncio

import pytest

from app.cache.ttl import AsyncTTLCache
from app.data_collector.base import SearchCriteria, SourceUnavailableError
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
async def test_search_service_filters_results_missing_core_fields(tmp_path) -> None:
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
