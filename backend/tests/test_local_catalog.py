import json
from pathlib import Path

import pytest

from app.cache.ttl import AsyncTTLCache
from app.data_collector.base import SearchCriteria
from app.data_collector.local_catalog import LocalVerifiedCatalogCollector
from app.editor.batch import EditorBatchService
from app.models.product import ProductSourceRecord
from app.normalizer.brand import BrandResolver
from app.normalizer.product import ProductNormalizer
from app.service.search_service import SearchService, _CollectedResult


PROJECT_CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "verified_products.json"
PROJECT_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "data" / "brand_registry.json"


class EnglishOnlyCollector:
    name = "official:english-only-fixture"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        if "kill lash" not in keyword.casefold():
            return []
        return [
            ProductSourceRecord(
                source="official",
                source_brand_name_en="CLIO",
                product_name_en="[CLIO] Kill Lash Superproof Mascara",
                product_name_display_en="Kill Lash Superproof Mascara",
                regular_price=14.9,
                currency="USD",
                source_url="https://clubclio.shop/products/clio-kill-lash-superproof-mascara",
                source_product_id="4649459482761",
                image_url="https://clubclio.shop/cdn/shop/products/1longcurling_1000x.jpg",
            )
        ]


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
                        "product_name_display_ko": "틴트",
                        "product_name_display_en": "Tint",
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
    assert records[0].product_name_display_ko == "틴트"
    assert records[0].product_name_display_en == "Tint"
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

    limited_records = await collector.search("global-only-keyword", limit=1)

    assert [record.source for record in limited_records] == ["oliveyoung", "oliveyoung-global"]


@pytest.mark.asyncio
async def test_project_catalog_returns_mixsoon_hyalraebae_cream() -> None:
    collector = LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)

    records = await collector.search("믹순 히알레배 포어 블러링 크림", limit=5)

    assert len(records) == 1
    assert records[0].source_brand_name == "믹순"
    assert records[0].product_name_ko == "믹순 히알레배 포어 블러링 크림 50ml"
    assert records[0].product_name_en is None
    assert records[0].regular_price == 14900
    assert records[0].image_url == "https://mixsoon.co.kr/web/product/big/202606/32bae01761c1d6d179bceb5d03c61f87.jpg"


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
    assert any(record.product_name_display_ko == "스피디 스키니 브로우" for record in records)
    assert any(record.product_name_display_en == "Speedy Skinny Brow" for record in records)
    assert any(record.source == "official" for record in records)
    official_record = next(record for record in records if record.source == "official")
    assert official_record.regular_price == 8.59
    assert official_record.currency == "USD"
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
        record.source_url == "https://www.canmake.com/en/item/detail/creamy-touch-liner"
        for record in records
    )
    official_record = next(record for record in records if record.source == "official")
    assert official_record.product_name_en == "Creamy Touch Liner"
    assert official_record.regular_price == 715
    assert official_record.currency == "JPY"


@pytest.mark.asyncio
async def test_project_catalog_enriches_hera_powder_from_official_source() -> None:
    collector = LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)

    records = await collector.search("헤라 파우더", limit=1)

    assert [record.source for record in records] == ["oliveyoung", "official"]
    assert any(record.product_name_en == "SOFT FINISH LOOSE POWDER" for record in records)
    assert any(record.product_name_display_ko == "소프트 피니시 루스 파우더" for record in records)
    assert any(record.product_name_display_en == "SOFT FINISH LOOSE POWDER" for record in records)
    official_record = next(record for record in records if record.source == "official")
    assert official_record.source_url == "https://int.hera.com/products/soft-finish-loose-powder"
    assert official_record.image_url == (
        "https://int.hera.com/cdn/shop/files/"
        "pdp_mig_2022-12-22-20220718_final_SOFT-FINISH-LOOSE-POWDER_pdp_thumbnail01_pc_1.jpg"
        "?v=1747965799&width=1024"
    )
    assert official_record.regular_price is None


@pytest.mark.asyncio
async def test_project_catalog_enriches_jungsaemmool_liner_from_official_source() -> None:
    collector = LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)

    records = await collector.search("정샘물 콜 펜 라이너", limit=3)

    assert records
    assert any(record.product_name_en == "JUNGSAEMMOOL Artist Kohl Pen Liner" for record in records)
    assert any(record.product_name_display_ko == "아티스트 콜 펜 라이너" for record in records)
    assert any(record.product_name_display_en == "Artist Kohl Pen Liner" for record in records)
    assert any(
        record.source_url == "https://jsmbeauty.com/m/product.html?branduid=2152173"
        for record in records
    )
    official_record = next(record for record in records if record.source == "official")
    assert official_record.image_url == "https://www.jsmbeauty.com/shopimages/jsmbeauty/0030030000182.jpg"


@pytest.mark.asyncio
async def test_project_catalog_enriches_the_saem_concealer_options_from_official_source() -> None:
    collector = LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)

    records = await collector.search("더샘 컨실러 클리어 베이지", limit=3)

    official_record = next(
        record
        for record in records
        if record.canonical_product_id == "verified:the-saem-cover-perfection-tip-concealer-clear-beige"
    )
    assert official_record.source == "official"
    assert official_record.product_name_en == "Cover Perfection Tip Concealer"
    assert official_record.regular_price == 5500
    assert official_record.shade == "1.0 클리어 베이지"
    assert official_record.image_url == (
        "https://www.thesaemcosmetic.com/data/item/1768801816/"
        "thumb-7Luk67KE7Y287Y6Z7IWY7YyB7Luo7Iuk65s_6re466O51_560x750.png"
    )
    assert official_record.options == [
        "0.5 아이스 베이지",
        "1.0 클리어 베이지",
        "1.25 라이트 베이지",
        "1.5 내추럴 베이지",
        "1.75 미들 베이지",
        "2.0 리치 베이지",
        "브라이트너",
        "컨투어 베이지",
        "그린 베이지",
        "피치 베이지",
    ]


@pytest.mark.asyncio
async def test_project_catalog_links_mude_brow_cara_to_official_source_options() -> None:
    collector = LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)

    records = await collector.search("뮤드 브로우카라 소프트 토프", limit=3)

    assert records
    assert {record.source for record in records} >= {"oliveyoung", "official"}
    assert any(record.product_name_display_ko == "인스파이어 스키니 브로우 카라" for record in records)
    official_record = next(record for record in records if record.source == "official")
    assert official_record.product_name_en is None
    assert official_record.regular_price == 14000
    assert official_record.sale_price == 13300
    assert official_record.discount_rate == 5
    assert official_record.rating == 4.8
    assert official_record.review_count == 344
    assert official_record.source_url == (
        "https://mude.co.kr/product/%EB%AE%A4%EB%93%9C-%EC%9D%B8%EC%8A%A4%ED%8C%8C%EC%9D%B4%EC%96%B4-%EC%8A%A4%ED%82%A4%EB%8B%88-%EB%B8%8C%EB%A1%9C%EC%9A%B0%EC%B9%B4%EB%9D%BC/160/category/30/display/1/"
    )
    assert official_record.options == [
        "C01 페이드 인",
        "C02 코튼",
        "B01 밀크 티",
        "B02 뮤트 넛",
        "B03 러스크",
        "B04 소프트 토프",
        "B05 허니 듀",
        "B06 티 라떼",
        "G01 코지 위트",
        "P01 버니",
    ]


@pytest.mark.asyncio
async def test_project_catalog_enriches_kissme_brow_cara_from_official_source() -> None:
    collector = LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)

    records = await collector.search("키스미 아이브로우", limit=3)

    assert {record.source for record in records} >= {"oliveyoung", "official"}
    assert any(record.product_name_display_ko == "헤비로테이션 컬러링 아이브로우 EX" for record in records)
    official_record = next(record for record in records if record.source == "official")
    assert official_record.source_brand_name_en == "KISS ME"
    assert official_record.product_name_en == "COLORING EYEBROW EX"
    assert official_record.product_name_display_en == "COLORING EYEBROW EX"
    assert official_record.source_url == "https://www.isehan.co.jp/heavyrotation/products/coloring_eyebrow_ex/"
    assert official_record.source_product_id == "heavyrotation-coloring-eyebrow-ex"
    assert official_record.image_url == "https://www.isehan.co.jp/heavyrotation/assets/img/common/pkg-01.png"


@pytest.mark.asyncio
async def test_project_catalog_enriches_clio_pro_eye_palette_air_english_name() -> None:
    collector = LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)

    records = await collector.search("클리오 치즈냥이", limit=5)

    record = next(
        record
        for record in records
        if record.canonical_product_id == "verified:clio-pro-eye-palette-air-mogamju-library"
    )
    assert record.product_name_en == "[CLIO] Pro Eye Palette Air"
    assert record.product_name_display_ko == "프로 아이 팔레트 에어"
    assert record.product_name_display_en == "Pro Eye Palette Air"
    assert record.shade == "21 모감주 밑 서재"
    assert record.regular_price == 34000
    assert record.rating == 4.41
    assert record.review_count == 119
    assert record.image_url == (
        "https://dn5hzapyfrpio.cloudfront.net/product/abe/"
        "abeb34b0-8494-11f0-98ef-25c6ea03afcd.jpeg"
    )


@pytest.mark.asyncio
async def test_project_catalog_uses_registry_brand_english_for_editor_targets() -> None:
    collector = LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)

    cases = [
        ("하밍 젤리 에어 치크 7호", "verified:haming-jelly-air-cheek", "HAMING"),
        ("오프라 하이라이터", "verified:ofra-mini-highlighter", "OFRA Cosmetics"),
        ("머지 더블 글레이즈 브레이브미", "verified:merzy-double-glaze-locker-gloss", "MERZY"),
        ("비디비치 틴트밤 카라멜허그", "verified:vidivici-peptide-butter-tint-balm", "VIDIVICI"),
    ]

    for query, canonical_id, brand_en in cases:
        records = await collector.search(query, limit=5)
        record = next(record for record in records if record.canonical_product_id == canonical_id)
        assert record.source_brand_name_en == brand_en


@pytest.mark.asyncio
async def test_project_catalog_enriches_ofra_mini_highlighter_english_family_name() -> None:
    collector = LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)

    records = await collector.search("오프라 미니 하이라이터", limit=3)

    record = next(record for record in records if record.canonical_product_id == "verified:ofra-mini-highlighter")
    assert record.product_name_en == "Mini Highlighter"
    assert record.product_name_display_en == "Mini Highlighter"
    assert record.shade is None


@pytest.mark.asyncio
async def test_project_catalog_enriches_brush_images_from_official_sources() -> None:
    collector = LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)

    cases = [
        (
            "G5513",
            "verified:hakuhodo-g5513-eye-shadow-brush",
            "https://hakuho-do.co.jp/cdn/shop/products/"
            "H2235_600_ef3e3164-e44d-4f02-9e4a-d814b07d542c.jpg?v=1750175372",
        ),
        (
            "G5512",
            "verified:hakuhodo-g5512-eye-shadow-brush-short",
            "https://hakuho-do.co.jp/cdn/shop/products/"
            "H2234_600_7349773c-25c3-4ed1-9d48-4e26c206e013.jpg?v=1750175371",
        ),
        (
            "S191",
            "verified:hakuhodo-s191-eyeliner-brush-round",
            "https://store.fudejapan.com/cdn/shop/products/"
            "H2049_600_900x_9535edd0-f436-4995-aa74-ef003b8f78a6.jpg?v=1649152881",
        ),
        (
            "안씨 에보니 42",
            "verified:ancci-ebony-42",
            "https://anccibrush.jp/html/upload/save_image/1027153727_635a27273c2d5.jpg",
        ),
    ]

    for query, canonical_id, image_url in cases:
        records = await collector.search(query, limit=5)
        record = next(record for record in records if record.canonical_product_id == canonical_id)
        assert record.image_url == image_url


@pytest.mark.asyncio
async def test_project_catalog_keeps_olens_image_without_inventing_english_name() -> None:
    collector = LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)

    records = await collector.search("오렌즈 글로이 티어 그레이", limit=5)

    record = next(
        record
        for record in records
        if record.canonical_product_id == "verified:olens-glowy-tear-one-day-gray"
    )
    assert record.image_url == (
        "https://dn5hzapyfrpio.cloudfront.net/product/3f5/"
        "3f578a80-9851-11f0-a909-33a03752c18d.png"
    )
    assert record.product_name_en is None
    assert record.product_name_display_ko == "글로이 티어 원데이"
    assert record.product_name_display_en is None


@pytest.mark.asyncio
async def test_project_catalog_uses_curated_display_names_for_brand_prefixed_records() -> None:
    collector = LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)

    cases = [
        ("포뷰트 텍스처 쉐이크", "verified:forbeaut-texture-shake-spray-100ml", "텍스처 쉐이크 스프레이"),
        ("에이오유 촘촘 아이브로우밤 밀크초코", "verified:aou-dense-eyebrow-balm-milk-choco", "촘촘 아이브로우밤"),
        ("오렌즈 글로이 티어 그레이", "verified:olens-glowy-tear-one-day-gray", "글로이 티어 원데이"),
    ]

    for query, canonical_id, display_name in cases:
        records = await collector.search(query, limit=5)
        record = next(record for record in records if record.canonical_product_id == canonical_id)
        assert record.product_name_display_ko == display_name


@pytest.mark.asyncio
async def test_project_catalog_enriches_hourglass_concealer_from_official_source() -> None:
    collector = LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)

    records = await collector.search("아워글래스 컨실러 스톤", limit=1)

    assert [record.source for record in records] == ["musinsa", "official"]
    assert any(record.product_name_en == "Vanish™ Airbrush Concealer" for record in records)
    assert any(record.product_name_display_ko == "배니쉬 에어브러쉬 컨실러" for record in records)
    assert any(record.product_name_display_en == "Vanish™ Airbrush Concealer" for record in records)
    official_record = next(record for record in records if record.source == "official")
    assert official_record.source_url == (
        "https://www.hourglasscosmetics.com/products/vanish-airbrush-concealer"
        "?variant=44511549620422"
    )
    assert official_record.source_product_id == "H216230001"
    assert official_record.regular_price == 39
    assert official_record.currency == "USD"
    assert official_record.image_url is not None
    assert "Stone.png" in official_record.image_url
    assert official_record.options == ["Stone 1.3 - Very Fair - Cool Pink / Full-size .20 fl oz"]


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
    assert result.product_name_display_ko == "크리미 터치 라이너"
    assert result.product_name_display_en == "Creamy Touch Liner"
    assert result.shade == "[15]Cappuccino Pink"
    assert any(
        offer.source == "official"
        and offer.source_url == "https://www.canmake.com/en/item/detail/creamy-touch-liner"
        and offer.price == 715
        and offer.currency == "JPY"
        for offer in result.offers
    )


@pytest.mark.asyncio
async def test_project_catalog_search_service_merges_hera_official_english_name() -> None:
    service = SearchService(
        collectors=[LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)],
        normalizer=ProductNormalizer(
            BrandResolver(PROJECT_REGISTRY_PATH),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        index_background_refresh_enabled=False,
    )

    response = await service.search("헤라 파우더", SearchCriteria(limit=1))
    await service.close()

    assert response.count == 1
    result = response.results[0]
    assert result.canonical_product_id == "verified:hera-soft-finish-loose-powder-15g"
    assert result.product_name_display_ko == "소프트 피니시 루스 파우더"
    assert result.product_name_en == "SOFT FINISH LOOSE POWDER"
    assert result.product_name_display_en == "SOFT FINISH LOOSE POWDER"
    assert [offer.source for offer in result.offers] == ["oliveyoung", "official"]
    assert any(
        offer.source == "official"
        and offer.source_url == "https://int.hera.com/products/soft-finish-loose-powder"
        and offer.image_url
        == (
            "https://int.hera.com/cdn/shop/files/"
            "pdp_mig_2022-12-22-20220718_final_SOFT-FINISH-LOOSE-POWDER_pdp_thumbnail01_pc_1.jpg"
            "?v=1747965799&width=1024"
        )
        and offer.price is None
        for offer in result.offers
    )
    assert "product_name_en" not in result.enrichment_missing_fields
    assert "official_source" not in result.enrichment_missing_fields


@pytest.mark.asyncio
async def test_project_catalog_search_service_merges_hourglass_official_english_name() -> None:
    service = SearchService(
        collectors=[LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)],
        normalizer=ProductNormalizer(
            BrandResolver(PROJECT_REGISTRY_PATH),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        index_background_refresh_enabled=False,
    )

    response = await service.search("아워글래스 컨실러 스톤", SearchCriteria(limit=1))
    await service.close()

    assert response.count == 1
    result = response.results[0]
    assert result.canonical_product_id == "verified:hourglass-vanish-airbrush-concealer-stone"
    assert result.product_name_display_ko == "배니쉬 에어브러쉬 컨실러"
    assert result.product_name_en == "Vanish™ Airbrush Concealer"
    assert result.product_name_display_en == "Vanish™ Airbrush Concealer"
    assert result.shade == "스톤"
    assert result.price == 39
    assert result.original_price == 39
    assert result.currency == "USD"
    assert result.image_url is not None
    assert "Stone.png" in result.image_url
    assert [offer.source for offer in result.offers] == ["official", "musinsa"]
    assert any(
        offer.source == "official"
        and offer.source_url
        == "https://www.hourglasscosmetics.com/products/vanish-airbrush-concealer?variant=44511549620422"
        and offer.source_product_id == "H216230001"
        and offer.price == 39
        and offer.currency == "USD"
        and offer.image_url is not None
        and "Stone.png" in offer.image_url
        for offer in result.offers
    )
    assert "product_name_en" not in result.enrichment_missing_fields
    assert "price" not in result.enrichment_missing_fields
    assert "image_url" not in result.enrichment_missing_fields
    assert "official_source" not in result.enrichment_missing_fields


@pytest.mark.asyncio
async def test_project_catalog_search_service_returns_clio_verified_english_name() -> None:
    service = SearchService(
        collectors=[LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)],
        normalizer=ProductNormalizer(
            BrandResolver(PROJECT_REGISTRY_PATH),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        index_background_refresh_enabled=False,
    )

    response = await service.search("클리오 치즈냥이", SearchCriteria(limit=1))
    await service.close()

    assert response.count == 1
    result = response.results[0]
    assert result.canonical_product_id == "verified:clio-pro-eye-palette-air-mogamju-library"
    assert result.product_name_display_ko == "프로 아이 팔레트 에어"
    assert result.product_name_en == "[CLIO] Pro Eye Palette Air"
    assert result.product_name_display_en == "Pro Eye Palette Air"
    assert result.shade == "21 모감주 밑 서재"
    assert "product_name_en" not in result.enrichment_missing_fields


@pytest.mark.asyncio
async def test_search_service_keeps_source_backed_english_only_product_names() -> None:
    registry_path = PROJECT_REGISTRY_PATH
    service = SearchService(
        collectors=[EnglishOnlyCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        index_background_refresh_enabled=False,
    )

    response = await service.search("kill lash superproof mascara", SearchCriteria(limit=1))
    await service.close()

    assert response.count == 1
    result = response.results[0]
    assert result.product_name_ko is None
    assert result.product_name_en == "[CLIO] Kill Lash Superproof Mascara"
    assert result.product_name_display_ko is None
    assert result.product_name_display_en == "Kill Lash Superproof Mascara"
    assert result.source_url == "https://clubclio.shop/products/clio-kill-lash-superproof-mascara"
    assert result.quality_score >= 90


@pytest.mark.asyncio
async def test_project_catalog_adds_clio_kill_lash_from_official_global_source() -> None:
    collector = LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)

    records = await collector.search("kill lash superproof mascara", limit=3)

    record = next(
        record
        for record in records
        if record.canonical_product_id == "verified:clio-kill-lash-superproof-mascara"
    )
    assert record.product_name_ko is None
    assert record.product_name_en == "[CLIO] Kill Lash Superproof Mascara"
    assert record.product_name_display_en == "Kill Lash Superproof Mascara"
    assert record.regular_price == 14.9
    assert record.currency == "USD"
    assert record.source == "official"
    assert record.source_url == "https://clubclio.shop/products/clio-kill-lash-superproof-mascara"
    assert record.options == [
        "01 Long Curling / Mascara Remover",
        "01 Long Curling / None",
        "02 Volume Curling / Mascara Remover",
        "02 Volume Curling / None",
        "04 Extreme Volume / Mascara Remover",
        "04 Extreme Volume / None",
    ]


@pytest.mark.asyncio
async def test_project_catalog_search_service_returns_clio_kill_lash_english_only_result() -> None:
    service = SearchService(
        collectors=[LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)],
        normalizer=ProductNormalizer(
            BrandResolver(PROJECT_REGISTRY_PATH),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        index_background_refresh_enabled=False,
    )

    response = await service.search("kill lash superproof mascara", SearchCriteria(limit=1))
    await service.close()

    assert response.count == 1
    result = response.results[0]
    assert result.canonical_product_id == "verified:clio-kill-lash-superproof-mascara"
    assert result.product_name_ko is None
    assert result.product_name_en == "[CLIO] Kill Lash Superproof Mascara"
    assert result.product_name_display_en == "Kill Lash Superproof Mascara"
    assert result.price == 14.9
    assert result.currency == "USD"
    assert result.source == "official"
    assert "product_name_en" not in result.enrichment_missing_fields


@pytest.mark.asyncio
async def test_project_catalog_search_service_uses_verified_display_names_for_editor_sample() -> None:
    service = SearchService(
        collectors=[LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)],
        normalizer=ProductNormalizer(
            BrandResolver(PROJECT_REGISTRY_PATH),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        index_background_refresh_enabled=False,
    )

    response = await service.search("페리페라 스키니브로우", SearchCriteria(limit=3))
    await service.close()

    assert response.count == 1
    result = response.results[0]
    assert result.product_name_ko == "[6월 올영픽] 페리페라 스피디 스키니 브로우 8 Colors (단품/더블)"
    assert result.product_name_en == "[PERIPERA] Speedy Skinny Brow"
    assert result.product_name_display_ko == "스피디 스키니 브로우"
    assert result.product_name_display_en == "Speedy Skinny Brow"


@pytest.mark.asyncio
async def test_project_catalog_search_service_uses_verified_display_names_for_recent_cleanups() -> None:
    service = SearchService(
        collectors=[LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)],
        normalizer=ProductNormalizer(
            BrandResolver(PROJECT_REGISTRY_PATH),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        index_background_refresh_enabled=False,
    )

    cases = [
        ("포뷰트 텍스처 쉐이크", "verified:forbeaut-texture-shake-spray-100ml", "텍스처 쉐이크 스프레이"),
        ("에이오유 촘촘 아이브로우밤 밀크초코", "verified:aou-dense-eyebrow-balm-milk-choco", "촘촘 아이브로우밤"),
        ("오렌즈 글로이 티어 그레이", "verified:olens-glowy-tear-one-day-gray", "글로이 티어 원데이"),
    ]

    try:
        for query, canonical_id, display_name in cases:
            response = await service.search(query, SearchCriteria(limit=1))
            assert response.count == 1
            result = response.results[0]
            assert result.canonical_product_id == canonical_id
            assert result.product_name_display_ko == display_name
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_project_catalog_search_service_merges_kissme_official_english_name() -> None:
    service = SearchService(
        collectors=[LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)],
        normalizer=ProductNormalizer(
            BrandResolver(PROJECT_REGISTRY_PATH),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        index_background_refresh_enabled=False,
    )

    response = await service.search("키스미 아이브로우", SearchCriteria(limit=1))
    await service.close()

    assert response.count == 1
    result = response.results[0]
    assert result.canonical_product_id == "verified:kissme-heavy-rotation-coloring-eyebrow-ex"
    assert result.brand_en == "KISS ME"
    assert result.product_name_display_ko == "헤비로테이션 컬러링 아이브로우 EX"
    assert result.product_name_en == "COLORING EYEBROW EX"
    assert result.product_name_display_en == "COLORING EYEBROW EX"
    assert [offer.source for offer in result.offers] == ["oliveyoung", "official"]
    assert any(
        offer.source == "official"
        and offer.source_url == "https://www.isehan.co.jp/heavyrotation/products/coloring_eyebrow_ex/"
        and offer.source_product_id == "heavyrotation-coloring-eyebrow-ex"
        and offer.image_url == "https://www.isehan.co.jp/heavyrotation/assets/img/common/pkg-01.png"
        for offer in result.offers
    )
    assert "brand_en" not in result.enrichment_missing_fields
    assert "product_name_en" not in result.enrichment_missing_fields
    assert "official_source" not in result.enrichment_missing_fields


@pytest.mark.asyncio
async def test_project_catalog_editor_batch_returns_kissme_official_english_candidate() -> None:
    search_service = SearchService(
        collectors=[LocalVerifiedCatalogCollector(PROJECT_CATALOG_PATH)],
        normalizer=ProductNormalizer(
            BrandResolver(PROJECT_REGISTRY_PATH),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        index_background_refresh_enabled=False,
    )
    service = EditorBatchService(search_service)

    response = await service.batch("키스미 아이브로우", limit=3)
    await search_service.close()

    assert response.count == 1
    item = response.items[0]
    assert item.parsed.brand_query == "키스미"
    assert item.parsed.brand_en == "KISS ME"
    assert item.status == "확인됨"
    assert len(item.candidates) == 1
    product = item.candidates[0].product
    assert product.product_name_display_ko == "헤비로테이션 컬러링 아이브로우 EX"
    assert product.product_name_en == "COLORING EYEBROW EX"
    assert product.product_name_display_en == "COLORING EYEBROW EX"
    assert any(offer.source == "official" and offer.source_url for offer in product.offers)
