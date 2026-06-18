import json
from pathlib import Path

from app.models.product import ProductSourceRecord
from app.normalizer.brand import BrandResolver
from app.normalizer.product import ProductNormalizer


PROJECT_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "data" / "brand_registry.json"


def test_brand_resolver_uses_verified_registry(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "official_en": "BE READY",
                        "aliases": ["비레디"],
                        "sources": ["https://www.instagram.com/bereadyofficial/"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    resolver = BrandResolver(registry_path)

    assert resolver.resolve("비레디") == "BE READY"
    assert resolver.resolve(None, "[단독기획] 비레디 블루 파운데이션") == "BE READY"
    assert resolver.resolve("BRTC") == "BRTC"
    assert resolver.resolve("브랜드") is None


def test_brand_resolver_uses_external_resolver_after_registry_miss(tmp_path) -> None:
    class FakeExternalResolver:
        def resolve(self, source_brand_name: str | None, *fallback_texts: str | None) -> str | None:
            if source_brand_name == "테스트브랜드" or any(
                text and "테스트브랜드" in text for text in fallback_texts
            ):
                return "TEST BRAND"
            return None

        def close(self) -> None:
            pass

    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    resolver = BrandResolver(registry_path, external_resolvers=[FakeExternalResolver()])

    assert resolver.resolve("테스트브랜드") == "TEST BRAND"
    assert resolver.resolve(None, "테스트브랜드 제품명") == "TEST BRAND"


def test_project_registry_maps_oliveyoung_korean_brand_names() -> None:
    resolver = BrandResolver(PROJECT_REGISTRY_PATH)

    assert resolver.resolve("퓌") == "fwee"
    assert resolver.resolve("식물나라") == "SHINGMULNARA"
    assert resolver.resolve("메디힐") == "MEDIHEAL"
    assert resolver.resolve("라로슈포제") == "La Roche-Posay"
    assert resolver.resolve("투쿨포스쿨") == "TOO COOL FOR SCHOOL"
    assert resolver.resolve("믹순") == "mixsoon"
    assert resolver.resolve("뮤드") == "mude"
    assert resolver.resolve("비긴스") == "BEGINS BY JUNGSAEMMOOL"
    assert resolver.resolve("어반디케이") == "Urban Decay"
    assert resolver.resolve("하밍") == "HAMING"
    assert resolver.resolve("오프라") == "OFRA Cosmetics"
    assert resolver.resolve("머지") == "MERZY"
    assert resolver.resolve("비디비치") == "VIDIVICI"
    assert resolver.resolve("캔메이크") == "CANMAKE"
    assert resolver.resolve("홀리카") == "HOLIKA HOLIKA"
    assert (
        resolver.resolve(None, "[기획] 비긴스 바이 정샘물 흔적 세럼")
        == "BEGINS BY JUNGSAEMMOOL"
    )
    assert resolver.match_text("투쿨포스쿨 스킨틴트").official_en == "TOO COOL FOR SCHOOL"
    assert resolver.match_text("더마 토너 패드 비타") is None
    assert resolver.match_text("프로 아이 팔레트 에어") is None
    etude_match = resolver.match_text("에뛰ㄷ")
    assert etude_match.official_en == "ETUDE"
    assert etude_match.matched_alias == "에뛰드"
    assert etude_match.matched_text == "에뛰ㄷ"


def test_brand_resolver_expands_korean_ampersand_typo_variants(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "official_en": "rom&nd",
                        "aliases": ["롬앤", "romand", "rom&nd"],
                        "sources": [],
                    },
                    {
                        "official_en": "Centellian24",
                        "aliases": ["센텔리안24"],
                        "sources": [],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    resolver = BrandResolver(registry_path)

    assert resolver.resolve("롬엔") == "rom&nd"
    assert resolver.match_text("롬엔 글래스팅 틴트").official_en == "rom&nd"
    assert resolver.resolve("샌텔리안24") is None


def test_product_normalizer_preserves_nulls(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="한글브랜드",
            product_name_ko="제품",
            regular_price=None,
            shade=None,
            image_url=None,
            source="oliveyoung",
        )
    )

    assert result.model_dump() == {
        "canonical_product_id": None,
        "brand_ko": "한글브랜드",
        "brand_en": None,
        "product_name_ko": "제품",
        "product_name_en": None,
        "product_name_display_ko": "제품",
        "product_name_display_en": None,
        "category": None,
        "price": None,
        "original_price": None,
        "sale_price": None,
        "discount_rate": None,
        "rating": None,
        "review_count": None,
        "currency": "KRW",
        "shade": None,
        "image_url": None,
        "description": None,
        "options": None,
        "sold_out": None,
        "source_url": None,
        "source_product_id": None,
        "source": "oliveyoung",
        "source_label": None,
        "source_priority": None,
        "quality_score": 60,
        "enrichment_missing_fields": [
            "brand_en",
            "product_name_en",
            "price",
            "image_url",
        ],
        "offers": [],
        "updated_at": None,
    }


def test_product_normalizer_uses_source_english_fields_without_fallback_text(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"Registry Brand","aliases":["브랜드"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="브랜드",
            source_brand_name_en="Source Brand",
            product_name_ko="제품명",
            product_name_en="Source Product Name",
            regular_price=12000,
            image_url="https://example.test/item.jpg",
            rating=4.8,
            source="official",
            source_url="https://example.test/product",
        )
    )

    assert result.brand_en == "Source Brand"
    assert result.product_name_en == "Source Product Name"
    assert result.product_name_display_ko == "제품명"
    assert result.product_name_display_en == "Source Product Name"
    assert result.quality_score == 110
    assert result.enrichment_missing_fields == []
    assert result.offers[0].source == "official"
    assert result.offers[0].source_url == "https://example.test/product"
    assert "미확인" not in json.dumps(result.model_dump(), ensure_ascii=False)


def test_product_normalizer_maps_english_brand_from_registry_only(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"Anua","aliases":["아누아"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="아누아",
            product_name_ko="어성초 77 수딩 토너",
            source="oliveyoung",
            source_product_id="A1",
        )
    )

    assert result.brand_en == "Anua"
    assert result.product_name_en is None
    assert result.product_name_display_en is None


def test_product_normalizer_keeps_latin_only_source_name_as_english_product_name(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"HAKUHODO","aliases":["하쿠호도"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="하쿠호도",
            product_name_ko="S191 Eyeliner Brush Round",
            source="official",
            source_url="https://example.test/s191",
        )
    )

    assert result.product_name_en == "S191 Eyeliner Brush Round"
    assert result.product_name_display_en == "S191 Eyeliner Brush Round"


def test_product_normalizer_exposes_display_name_without_retail_promo_terms(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        """
        {
          "entries": [
            {
              "official_en": "peripera",
              "aliases": ["페리페라", "peripera", "PERIPERA"],
              "sources": []
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="페리페라",
            product_name_ko="[6월 올영픽] 페리페라 스피디 스키니 브로우 8 Colors (단품/더블)",
            product_name_en="[PERIPERA] Speedy Skinny Brow",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000138671",
            source_product_id="A000000138671",
        )
    )

    assert result.product_name_ko == "[6월 올영픽] 페리페라 스피디 스키니 브로우 8 Colors (단품/더블)"
    assert result.product_name_en == "[PERIPERA] Speedy Skinny Brow"
    assert result.product_name_display_ko == "스피디 스키니 브로우"
    assert result.product_name_display_en == "Speedy Skinny Brow"


def test_product_normalizer_does_not_translate_display_name_without_source_english(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"SHINGMULNARA","aliases":["식물나라"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="식물나라",
            product_name_ko="식물나라 가벼운 수분 선 젤 60ml 단품/2입 기획",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000225224",
            source_product_id="A000000225224",
        )
    )

    assert result.product_name_display_ko == "가벼운 수분 선 젤"
    assert result.product_name_en is None
    assert result.product_name_display_en is None


def test_product_normalizer_removes_trailing_size_and_option_counts(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"Heart Percent","aliases":["하트퍼센트"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="하트퍼센트",
            product_name_ko="[이한 PICK] 하트퍼센트 도트 온 무드 올 커버 립 베이스 4.1g 9종",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000221612",
            source_product_id="A000000221612",
        )
    )

    assert result.product_name_display_ko == "도트 온 무드 올 커버 립 베이스"
    assert result.product_name_en is None
    assert result.product_name_display_en is None


def test_product_normalizer_removes_parenthesized_option_lists(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"MEDIHEAL","aliases":["메디힐"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.musinsa.com",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="메디힐",
            product_name_ko="더마 토너 패드 100매 8종 (티트리/마데카소사이드/피디알엔/콜라겐/워터마이드/비타/피토엔자임/레티놀)",
            source="musinsa",
            source_url="https://www.musinsa.com/products/3020375",
            source_product_id="3020375",
        )
    )

    assert result.product_name_display_ko == "더마 토너 패드"
    assert result.product_name_en is None
    assert result.product_name_display_en is None


def test_product_normalizer_cleans_canmake_retail_name_with_verified_english(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"CANMAKE","aliases":["캔메이크","CANMAKE"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="캔메이크",
            product_name_ko="[신상출시/초슬림라이너] 캔메이크 크리미 터치 라이너 10종 택1",
            product_name_en="Creamy Touch Liner",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000232543",
            source_product_id="A000000232543",
        )
    )

    assert result.product_name_ko == "[신상출시/초슬림라이너] 캔메이크 크리미 터치 라이너 10종 택1"
    assert result.product_name_en == "Creamy Touch Liner"
    assert result.product_name_display_ko == "크리미 터치 라이너"
    assert result.product_name_display_en == "Creamy Touch Liner"


def test_product_normalizer_preserves_the_saem_verified_english_display_name(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"the SAEM","aliases":["더샘","the SAEM"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.thesaemcosmetic.com",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="더샘",
            product_name_ko="커버 퍼펙션 팁 컨실러",
            product_name_en="Cover Perfection Tip Concealer",
            source="official",
            source_url="https://www.thesaemcosmetic.com/product/item.php?it_id=1768801816",
            source_product_id="1768801816",
        )
    )

    assert result.product_name_display_ko == "커버 퍼펙션 팁 컨실러"
    assert result.product_name_en == "Cover Perfection Tip Concealer"
    assert result.product_name_display_en == "Cover Perfection Tip Concealer"


def test_product_normalizer_expands_short_korean_subbrand_alias(tmp_path) -> None:
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
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="비긴스",
            product_name_ko="[기획] 비긴스 바이 정샘물 흔적 세럼",
            regular_price=42000,
            sale_price=25990,
            original_price=42000,
            source="oliveyoung",
        )
    )

    assert result.brand_ko == "비긴스 바이 정샘물"
    assert result.brand_en == "BEGINS BY JUNGSAEMMOOL"


def test_product_normalizer_prefers_spaced_korean_brand_alias(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        (
            '{"entries":['
            '{"official_en":"BEGINS BY JUNGSAEMMOOL",'
            '"aliases":["비긴스 바이 정샘물"],"sources":[]}'
            "]}"
        ),
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="비긴스바이정샘물",
            product_name_ko="[기획] 비긴스바이정샘물 블루 수국 히알 수분세럼",
            regular_price=24000,
            sale_price=16800,
            original_price=24000,
            source="oliveyoung",
        )
    )

    assert result.brand_ko == "비긴스 바이 정샘물"
    assert result.brand_en == "BEGINS BY JUNGSAEMMOOL"


def test_brand_resolver_exposes_korean_warmup_aliases(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        """
        {
          "entries": [
            {"official_en": "mude", "aliases": ["뮤드", "mude"], "sources": []},
            {"official_en": "rom&nd", "aliases": ["rom&nd", "롬앤"], "sources": []}
          ]
        }
        """,
        encoding="utf-8",
    )

    resolver = BrandResolver(registry_path)

    assert resolver.warmup_aliases() == ["뮤드", "롬앤"]
    assert resolver.warmup_aliases(1) == ["뮤드"]


def test_brand_resolver_exposes_aliases_with_korean_first() -> None:
    resolver = BrandResolver(PROJECT_REGISTRY_PATH)

    aliases = resolver.aliases_for("too cool for school")

    assert aliases[0] == "투쿨포스쿨"
    assert "TOO COOL FOR SCHOOL" in aliases
