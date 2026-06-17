import json
from pathlib import Path

import pytest

from app.cache.ttl import AsyncTTLCache
from app.data_collector.base import SearchCriteria
from app.data_collector.local_catalog import LocalVerifiedCatalogCollector
from app.normalizer.brand import BrandResolver
from app.normalizer.product import ProductNormalizer
from app.service.search_service import SearchService, _CollectedResult


PROJECT_CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "verified_products.json"
PROJECT_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "data" / "brand_registry.json"


@pytest.mark.asyncio
async def test_local_catalog_returns_verified_matching_products(tmp_path) -> None:
    catalog_path = tmp_path / "verified_products.json"
    catalog_path.write_text(
        json.dumps(
            {
                "products": [
                    {
                        "brand_en": "rom&nd",
                        "brand_ko": "롬앤",
                        "product_name_ko": "롬앤 틴트",
                        "price": 13000,
                        "image_url": "https://example.com/image.jpg",
                        "source_url": "https://example.com/product",
                        "goods_no": "A000",
                        "keywords": ["romand", "틴트"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    collector = LocalVerifiedCatalogCollector(catalog_path)

    records = await collector.search("romand", limit=10)

    assert len(records) == 1
    assert records[0].source_brand_name == "롬앤"
    assert records[0].product_name_ko == "롬앤 틴트"
    assert records[0].regular_price == 13000
    assert records[0].source_url == "https://example.com/product"
    assert records[0].search_keywords == ["romand", "틴트"]

    all_records = await collector.all_records()

    assert len(all_records) == 1
    assert all_records[0].search_keywords == ["romand", "틴트"]


@pytest.mark.asyncio
async def test_local_catalog_expands_verified_canonical_source_group(tmp_path) -> None:
    catalog_path = tmp_path / "verified_products.json"
    catalog_path.write_text(
        json.dumps(
            {
                "products": [
                    {
                        "canonical_product_id": "verified-romand-tint",
                        "brand_en": "rom&nd",
                        "brand_ko": "롬앤",
                        "product_name_ko": "롬앤 틴트",
                        "price": 13000,
                        "source_url": "https://oliveyoung.example/product",
                        "goods_no": "A000",
                        "source": "oliveyoung",
                        "keywords": ["롬앤", "틴트"],
                    },
                    {
                        "canonical_product_id": "verified-romand-tint",
                        "brand_en": "rom&nd",
                        "brand_ko": "롬앤",
                        "product_name_ko": "rom&nd tint",
                        "product_name_en": "rom&nd tint",
                        "price": 12,
                        "currency": "USD",
                        "source_url": "https://global.oliveyoung.example/product",
                        "goods_no": "G000",
                        "source": "oliveyoung-global",
                        "keywords": ["global-only-keyword"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    collector = LocalVerifiedCatalogCollector(catalog_path)

    records = await collector.search("global-only-keyword", limit=10)

    assert [record.source for record in records] == ["oliveyoung", "oliveyoung-global"]
    assert {record.canonical_product_id for record in records} == {"verified-romand-tint"}
    assert records[1].product_name_en == "rom&nd tint"


@pytest.mark.asyncio
async def test_project_catalog_returns_mixsoon_hyalraebae_cream() -> None:
    collector = LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)

    records = await collector.search("믹순 히알레배 포어 블러링 크림", limit=5)

    assert len(records) == 1
    assert records[0].source_brand_name == "믹순"
    assert records[0].product_name_ko == "믹순 히알레배 포어 블러링 크림 50ml"
    assert records[0].regular_price == 14900


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "expected_name"),
    [
        ("헤라 파우더", "헤라 소프트 피니시 루스 파우더 15g"),
        ("롬앤 쉐딩 그레이쿨", "롬앤 베러 댄 쉐입 쉐딩"),
        ("페리페라 스키니브로우", "[6월 올영픽] 페리페라 스피디 스키니 브로우 8 Colors (단품/더블)"),
        ("하밍 젤리 에어 치크", "[NEW] 하밍 젤리 에어 치크"),
        ("홀리카 팔레트 핑크올로지", "[NEW한정기획] 홀리카홀리카 마이페이브 무드 아이 팔레트"),
        ("머지 더블 글레이즈 브레이브미", "[NEW단독기획/김서영PICK] 머지 더블 글레이즈 락커 글로스 12종 단품/기획"),
        ("비디비치 틴트밤 카라멜허그", "[미니틴트 증정기획] 비디비치 펩타이드 버터 틴트밤 기획/단품"),
        ("포근 픽싱 틴트 19호", "에뛰드 포근 픽싱 틴트 (단품/기획) 17 Colors"),
        ("클리오 치즈냥이", "(클리오X국가유산청) 프로 아이 팔레트 에어"),
    ],
)
async def test_project_catalog_covers_editor_sample_source_verified_items(
    query: str,
    expected_name: str,
) -> None:
    collector = LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)

    records = await collector.search(query, limit=5)

    assert records
    assert records[0].product_name_ko == expected_name
    assert records[0].source_url


@pytest.mark.asyncio
async def test_project_catalog_enriches_peripera_skinny_brow_from_official_source() -> None:
    collector = LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)

    records = await collector.search("페리페라 스키니브로우", limit=5)

    assert any(record.product_name_en == "[PERIPERA] Speedy Skinny Brow" for record in records)
    assert any(record.source == "official" for record in records)
    assert any(
        record.source_url == "https://clubclio.shop/products/peripera-speedy-skinny-brow"
        for record in records
    )


@pytest.mark.asyncio
async def test_project_catalog_enriches_canmake_cappuccino_shade_from_official_source() -> None:
    collector = LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)

    records = await collector.search("캔메이크 아라 카푸치노", limit=5)

    assert any(record.shade == "[15]Cappuccino Pink" for record in records)
    assert any(record.source == "official" for record in records)
    assert any(
        record.source_url == "https://www.canmake.com/item/detail/creamy-touch-liner/"
        for record in records
    )


@pytest.mark.asyncio
async def test_project_catalog_search_service_matches_canmake_editor_abbreviation() -> None:
    service = SearchService(
        collectors=[LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)],
        normalizer=ProductNormalizer(
            BrandResolver(PROJECT_REGISTRY_PATH),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        index_background_refresh_enabled=False,
    )

    response = await service.search("캔메이크 아라 카푸치노", SearchCriteria(limit=3))
    await service.close()

    assert response.count == 1
    result = response.results[0]
    assert result.brand_ko == "캔메이크"
    assert result.shade == "[15]Cappuccino Pink"
    assert any(
        offer.source == "official"
        and offer.source_url == "https://www.canmake.com/item/detail/creamy-touch-liner/"
        for offer in result.offers
    )
