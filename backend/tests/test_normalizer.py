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
    assert resolver.resolve("어바웃톤") == "ABOUT TONE"
    assert resolver.resolve("낫포유") == "NOT4U"
    assert resolver.resolve("캔메이크") == "CANMAKE"
    assert resolver.resolve("홀리카") == "HOLIKA HOLIKA"
    assert resolver.resolve("에스네이처") == "S.NATURE"
    assert resolver.resolve("메디큐브") == "medicube"
    assert resolver.resolve("코스노리") == "COSNORI"
    assert resolver.resolve("오브제") == "OBgE"
    assert resolver.resolve("유리아쥬") == "URIAGE"
    assert resolver.resolve("제로이드") == "ZEROID"
    assert resolver.resolve("크리니크") == "Clinique"
    assert resolver.resolve("버츠비") == "Burt's Bees"
    assert resolver.resolve("빌리프") == "belif"
    assert resolver.resolve("센텔리안24") == "Centellian24"
    assert resolver.resolve("리쥬란") == "REJURAN"
    assert resolver.resolve("듀이트리") == "DEWYTREE"
    assert resolver.resolve("뉴트로지나") == "Neutrogena"
    assert resolver.resolve("더바디샵") == "The Body Shop"
    assert resolver.resolve("멘소래담") == "Mentholatum"
    assert resolver.resolve("디오디너리") == "The Ordinary"
    assert resolver.resolve("아넷사") == "ANESSA"
    assert resolver.resolve("비페스타") == "Bifesta"
    assert resolver.resolve("카멕스") == "Carmex"
    assert resolver.resolve("시미헤이즈뷰티") == "SIMIHAZE BEAUTY"
    assert resolver.resolve("프레시안") == "FRESHIAN"
    assert resolver.resolve("웰라쥬") == "WELLAGE"
    assert resolver.resolve("한율") == "HANYUL"
    assert resolver.resolve("프리메라") == "primera"
    assert resolver.resolve("피캄") == "P.CALM"
    assert resolver.resolve("네오젠") == "NEOGEN"
    assert resolver.resolve("밀크바오밥") == "Milk Baobab"
    assert resolver.resolve("토니모리") == "TONYMOLY"
    assert resolver.resolve("블리스텍스") == "Blistex"
    assert resolver.resolve("나르카") == "NARKA"
    assert resolver.resolve("숨37") == "su:m37°"
    assert resolver.resolve("유이크") == "UIQ"
    assert resolver.resolve("아이오페") == "IOPE"
    assert resolver.resolve("그라펐") is None
    assert resolver.resolve("그라펜") == "GRAFEN"
    assert resolver.resolve("닥터디퍼런트") == "Dr. Different"
    assert resolver.resolve("로벡틴") == "Rovectin"
    assert resolver.resolve("성분에디터") == "SUNGBOON EDITOR"
    assert resolver.resolve("이지듀") == "Easydew"
    assert resolver.resolve("한스킨") == "HANSKIN"
    assert resolver.resolve("바이오던스") == "Biodance"
    assert resolver.resolve("더마토리") == "Dermatory"
    assert resolver.resolve("케이트") == "KATE"
    assert resolver.resolve("일소") == "ilso"
    assert resolver.resolve("하다라보") == "Hada Labo"
    assert resolver.resolve("존슨즈") == "Johnson's"
    assert resolver.resolve("엠도씨") == "MdoC"
    assert resolver.resolve("더페이스샵") == "THE FACE SHOP"
    assert resolver.resolve("카밀") == "Kamill"
    assert resolver.resolve("록시땅") == "L'OCCITANE"
    assert resolver.resolve("라곰") == "LAGOM"
    assert resolver.resolve("랩시리즈") == "LAB SERIES"
    assert resolver.resolve("비오템") == "BIOTHERM"
    assert resolver.resolve("폴라초이스") == "Paula's Choice"
    assert resolver.resolve("메디필") == "MEDIPEEL"
    assert resolver.resolve("바이오힐 보") == "BIOHEAL BOH"
    assert resolver.resolve("투크") == "TOOQ"
    assert resolver.resolve("닥터엘시아") == "Dr.Althea"
    assert resolver.resolve("레이지소사이어티") == "Lazy Society"
    assert resolver.resolve("케어존") == "CAREZONE"
    assert resolver.resolve("아크네스") == "Acnes"
    assert resolver.resolve("나인위시스") == "9wishes"
    assert resolver.resolve("리얼베리어") == "Real Barrier"
    assert resolver.resolve("더마팩토리") == "Derma Factory"
    assert resolver.resolve("달리프") == "DALIF"
    assert resolver.resolve("퍼셀") == "PURCELL"
    assert resolver.resolve("파넬") == "Parnell"
    assert resolver.resolve("원씽") == "ONE THING"
    assert resolver.resolve("쏘내추럴") == "SO NATURAL"
    assert resolver.resolve("디어달리아") == "Dear Dahlia"
    assert resolver.resolve("아떼") == "athe"
    assert resolver.resolve("플르부아") == "pleuvoir"
    assert resolver.resolve("닥터올가") == "Dr.Orga"
    assert resolver.resolve("궁중비책") == "GOONGBE"
    assert resolver.resolve("더랩바이블랑두") == "THE LAB by blanc doux"
    assert resolver.resolve("더툴랩") == "THE TOOL LAB"
    assert resolver.resolve("파파레서피") == "Papa Recipe"
    assert resolver.resolve("눅스") == "NUXE"
    assert resolver.resolve("질레트") == "Gillette"
    assert resolver.resolve("히말라야") == "Himalaya"
    assert resolver.resolve("지베르니") == "GIVERNY"
    assert resolver.resolve("투에이엔") == "2aN"
    assert resolver.resolve("닥터바이오") == "Dr.Bio"
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


def test_product_normalizer_prefers_verified_display_name_over_rule_cleanup(tmp_path) -> None:
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
            product_name_display_ko="스피디 스키니 브로우",
            product_name_display_en="Speedy Skinny Brow",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000138671",
            source_product_id="A000000138671",
        )
    )

    assert result.product_name_ko == "[6월 올영픽] 페리페라 스피디 스키니 브로우 8 Colors (단품/더블)"
    assert result.product_name_en == "[PERIPERA] Speedy Skinny Brow"
    assert result.product_name_display_ko == "스피디 스키니 브로우"
    assert result.product_name_display_en == "Speedy Skinny Brow"


def test_product_normalizer_cleans_kissme_retail_brow_cara_name(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"KISS ME","aliases":["키스미","KISS ME"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="키스미",
            source_brand_name_en="KISS ME",
            product_name_ko="[1등브로우]키스미 헤비로테이션 컬러링 아이브로우 EX 6종 (단품/브로우카라기획)",
            product_name_en="COLORING EYEBROW EX",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000219593",
            source_product_id="A000000219593",
        )
    )

    assert result.product_name_ko == "[1등브로우]키스미 헤비로테이션 컬러링 아이브로우 EX 6종 (단품/브로우카라기획)"
    assert result.product_name_en == "COLORING EYEBROW EX"
    assert result.product_name_display_ko == "헤비로테이션 컬러링 아이브로우 EX"
    assert result.product_name_display_en == "COLORING EYEBROW EX"


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


def test_product_normalizer_removes_retail_prefix_before_brand(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"ABOUT TONE","aliases":["어바웃톤"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="NEW",
            product_name_ko="[촉촉블러쿠션]NEW 어바웃톤 워터 레이어 핏 쿠션 14g 8종 (기획/단품)",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000235162",
            source_product_id="A000000235162",
        )
    )

    assert result.brand_ko == "어바웃톤"
    assert result.brand_en == "ABOUT TONE"
    assert result.product_name_display_ko == "워터 레이어 핏 쿠션"
    assert result.product_name_en is None
    assert result.product_name_display_en is None


def test_product_normalizer_removes_compact_color_count_and_packaging_suffix(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"WAKEMAKE","aliases":["웨이크메이크"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="웨이크메이크",
            product_name_ko="[미니틴트 증정]웨이크메이크 워터 블러링 레이어 틴트 14COLOR(단품/기획)",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000223250",
            source_product_id="A000000223250",
        )
    )

    assert result.product_name_display_ko == "워터 블러링 레이어 틴트"
    assert result.product_name_en is None
    assert result.product_name_display_en is None


def test_product_normalizer_removes_buy_one_get_one_suffix(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"CLIO","aliases":["클리오"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="클리오",
            product_name_ko="[6월 올영픽/단종부활템 증정] 클리오 킬 래쉬 수퍼프루프 마스카라 1+1기획 (+미니 속눈썹 영양제 증정)",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000121749",
            source_product_id="A000000121749",
        )
    )

    assert result.product_name_display_ko == "킬 래쉬 수퍼프루프 마스카라"
    assert result.product_name_en is None
    assert result.product_name_display_en is None


def test_product_normalizer_removes_color_count_with_refill_bundle_suffix(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"espoir","aliases":["에스쁘아"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="에스쁘아",
            product_name_ko="[핸들 파우치 증정 기획] 에스쁘아 실크 스킨 레이어 쿠션 7colors 본품+리필",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000247764",
            source_product_id="A000000247764",
        )
    )

    assert result.product_name_display_ko == "실크 스킨 레이어 쿠션"
    assert result.product_name_en is None
    assert result.product_name_display_en is None


def test_product_normalizer_ignores_polluted_korean_source_brand_and_matches_registry_brand(
    tmp_path,
) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"NOT4U","aliases":["낫포유","NOT4U"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="뿌리는",
            product_name_ko="[1위 속보습미스트] 뿌리는 바디로션 낫포유 크림 바디미스트 200ml",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000214971",
            source_product_id="A000000214971",
        )
    )

    assert result.brand_ko == "낫포유"
    assert result.brand_en == "NOT4U"
    assert result.product_name_display_ko == "크림 바디미스트"
    assert result.product_name_en is None
    assert result.product_name_display_en is None


def test_product_normalizer_removes_refill_bundle_after_size_suffix(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"numbuzin","aliases":["넘버즈인"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="넘버즈인",
            product_name_ko="[쿨링진정]넘버즈인 1번 진정 맑게담은 청초토너 300ml 리필기획(+300ml 증정)",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000190395",
            source_product_id="A000000190395",
        )
    )

    assert result.product_name_display_ko == "1번 진정 맑게담은 청초토너"
    assert result.product_name_en is None
    assert result.product_name_display_en is None


def test_product_normalizer_removes_double_bundle_after_size_and_count_suffix(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"numbuzin","aliases":["넘버즈인"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="넘버즈인",
            product_name_ko="[파데프리] 넘버즈인 3번 도자기결 톤업베이지 선크림 50ml 더블기획 2종 (블러/글로우)",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000257097",
            source_product_id="A000000257097",
        )
    )

    assert result.product_name_display_ko == "3번 도자기결 톤업베이지 선크림"
    assert result.product_name_en is None
    assert result.product_name_display_en is None


def test_product_normalizer_removes_leading_option_count_and_choice_suffix(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"SKIN BENEFIT","aliases":["스킨베네핏"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="스킨베네핏",
            product_name_ko="스킨베네핏 3종 퀵 커버 헤어 마스카라 듀오팩 (흑갈색/자연갈색/자연흑색) 중 택 1",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000218471",
            source_product_id="A000000218471",
        )
    )

    assert result.product_name_display_ko == "퀵 커버 헤어 마스카라 듀오팩"
    assert result.product_name_en is None
    assert result.product_name_display_en is None


def test_product_normalizer_removes_duo_bundle_suffix_with_multiple_sizes(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"numbuzin","aliases":["넘버즈인"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="넘버즈인",
            product_name_ko="[흔적미백] 넘버즈인 5번 글루타치온C 흔적 앰플 30ml+30ml 듀오기획",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000189837",
            source_product_id="A000000189837",
        )
    )

    assert result.product_name_display_ko == "5번 글루타치온C 흔적 앰플"


def test_product_normalizer_removes_limited_bundle_suffix_after_size(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"REJUDERMA","aliases":["리쥬더마"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="리쥬더마",
            product_name_ko="[리쥬란 제약사_4배속 급속진정]리쥬더마 EX 리페어링 크림 20g (+5g*2ea) 한정기획",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000255273",
            source_product_id="A000000255273",
        )
    )

    assert result.product_name_display_ko == "EX 리페어링 크림"


def test_product_normalizer_removes_parenthesized_unit_count_suffix(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"medicube","aliases":["메디큐브"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="메디큐브",
            product_name_ko="[미백원액세럼][NEW]메디큐브 PDRN 핑크 원데이 세럼(1.5ml*10ea)",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000219676",
            source_product_id="A000000219676",
        )
    )

    assert result.product_name_display_ko == "PDRN 핑크 원데이 세럼"


def test_product_normalizer_removes_attached_gift_suffix_after_size(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"LABO-H","aliases":["라보에이치"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="라보에이치",
            product_name_ko="[6월 올영픽/두피선크림] 라보에이치 UV 롤온선세럼15ML+샴푸50증정기획",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000255405",
            source_product_id="A000000255405",
        )
    )

    assert result.product_name_display_ko == "UV 롤온선세럼"


def test_product_normalizer_removes_standalone_refill_planning_suffix(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        (
            '{"entries":[{"official_en":"BEGINS BY JUNGSAEMMOOL",'
            '"aliases":["비긴스 바이 정샘물","비긴스"],"sources":[]}]}'
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
            product_name_ko="[도훈PICK/7일잡티샷] 비긴스 바이 정샘물 나이아신아마이드10 흔적세럼 리필기획",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000231545",
            source_product_id="A000000231545",
        )
    )

    assert result.product_name_display_ko == "나이아신아마이드10 흔적세럼"


def test_product_normalizer_removes_trailing_option_count_with_marker(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"CORALHAZE","aliases":["코랄헤이즈"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="코랄헤이즈",
            product_name_ko="코랄헤이즈 글로우락젤리틴트 6종 (기획/단품) *",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000213198",
            source_product_id="A000000213198",
        )
    )

    assert result.product_name_display_ko == "글로우락젤리틴트"


def test_product_normalizer_removes_choice_parenthetical_suffix(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"Clinique","aliases":["크리니크"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="크리니크",
            product_name_ko="크리니크 각질케어토너 200ml (피부타입별 선택)",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000160562",
            source_product_id="A000000160562",
        )
    )

    assert result.product_name_display_ko == "각질케어토너"


def test_product_normalizer_keeps_kit_name_while_removing_option_count(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"Easydew","aliases":["이지듀"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="이지듀",
            product_name_ko="[열감진정리페어] 이지듀 EGFx 다운타임 3종 키트 (세럼 40ml+크림60ml+오인트겔5ml)",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000257406",
            source_product_id="A000000257406",
        )
    )

    assert result.product_name_display_ko == "EGFx 다운타임 키트"


def test_product_normalizer_removes_color_count_limited_planning_suffix(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"hince","aliases":["힌스"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="힌스",
            product_name_ko="[미니 플럼핑 립 펜슬 증정] 힌스 누 블러 틴트 10 Colors 한정 기획",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000246345",
            source_product_id="A000000246345",
        )
    )

    assert result.product_name_display_ko == "누 블러 틴트"


def test_product_normalizer_removes_usage_parenthetical_after_size(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"HAIRPLUS","aliases":["헤어플러스"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="헤어플러스",
            product_name_ko="[화해1위] 헤어플러스 단백질 본드 앰플 에센스 70ml(노워시 헤어팩)",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000119707",
            source_product_id="A000000119707",
        )
    )

    assert result.product_name_display_ko == "단백질 본드 앰플 에센스"


def test_product_normalizer_removes_count_and_limited_bundle_suffix(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"HAIRPLUS","aliases":["헤어플러스"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="헤어플러스",
            product_name_ko="[포켓몬 에디션][손상케어] 헤어플러스 단백질 본드 앰플에센스 70ml 2개입 한정/단독기획 (노워시)",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000125539",
            source_product_id="A000000125539",
        )
    )

    assert result.product_name_display_ko == "단백질 본드 앰플에센스"


def test_product_normalizer_removes_planning_pack_suffix(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"celimax","aliases":["셀리맥스"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="셀리맥스",
            product_name_ko="셀리맥스 대용량 토너패드 기획팩 2종 택1",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000240786",
            source_product_id="A000000240786",
        )
    )

    assert result.product_name_display_ko == "대용량 토너패드"


def test_product_normalizer_removes_oy_exclusive_parenthetical_and_sheet_count(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"NEEDLY","aliases":["니들리"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="니들리",
            product_name_ko="니들리 데일리 토너 패드 80매 (+20매 증정기획) (OY단독)",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000225053",
            source_product_id="A000000225053",
        )
    )

    assert result.product_name_display_ko == "데일리 토너 패드"


def test_product_normalizer_removes_short_channel_parenthetical(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"ROUND LAB","aliases":["라운드랩"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="라운드랩",
            product_name_ko="[속광탄력/콜라겐팩] 라운드랩 동백 딥 콜라겐 탄력 겔 마스크 4매 (온)",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000211151",
            source_product_id="A000000211151",
        )
    )

    assert result.product_name_display_ko == "동백 딥 콜라겐 탄력 겔 마스크"


def test_product_normalizer_removes_shade_choice_parenthetical_after_size(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"ONE OF THEM","aliases":["원오브뎀"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="원오브뎀",
            product_name_ko="[하루종일 착붙] 원오브뎀 드 뗑 쿠션 12g(1호, 2호)",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000206573",
            source_product_id="A000000206573",
        )
    )

    assert result.product_name_display_ko == "드 뗑 쿠션"


def test_product_normalizer_removes_ad_parenthetical_and_color_count(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"ETUDE","aliases":["에뛰드"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="에뛰드",
            product_name_ko="[NEW 컬러] 에뛰드 드로잉 아이즈 컬러링 브로우카라 (26AD) 8 Colors",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000244840",
            source_product_id="A000000244840",
        )
    )

    assert result.product_name_display_ko == "드로잉 아이즈 컬러링 브로우카라"


def test_product_normalizer_removes_multi_pack_suffix_after_size(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"Neutrogena","aliases":["뉴트로지나"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="뉴트로지나",
            product_name_ko="[재구매율1위/보들촉촉밀크] 뉴트로지나 딥클린 클렌징로션(클렌징 밀크) 200ml 2입",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000228248",
            source_product_id="A000000228248",
        )
    )

    assert result.product_name_display_ko == "딥클린 클렌징로션"


def test_product_normalizer_removes_special_limited_planning_suffix(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"HOLIKA HOLIKA","aliases":["홀리카홀리카"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="홀리카홀리카",
            product_name_ko="홀리카홀리카 래쉬코렉팅마스카라 꿀조합 특별한정기획",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000206074",
            source_product_id="A000000206074",
        )
    )

    assert result.product_name_display_ko == "래쉬코렉팅마스카라 꿀조합"


def test_product_normalizer_removes_usage_parenthetical_for_lash_serum(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"HOLIKA HOLIKA","aliases":["홀리카홀리카"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="홀리카홀리카",
            product_name_ko="홀리카홀리카 래쉬코렉팅케어 에센셜 세럼 (속눈썹영양제)",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000150279",
            source_product_id="A000000150279",
        )
    )

    assert result.product_name_display_ko == "래쉬코렉팅케어 에센셜 세럼"


def test_product_normalizer_removes_attached_size_planning_suffix(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"NUXE","aliases":["눅스"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="눅스",
            product_name_ko="[고보습 허니 립밤]눅스 레브드미엘 립밤 15g기획 (+핸드앤네일크림15ml 증정)",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000012315",
            source_product_id="A000000012315",
        )
    )

    assert result.product_name_display_ko == "레브드미엘 립밤"


def test_product_normalizer_removes_option_count_pick_suffix(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"BBABA","aliases":["빼바"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="빼바",
            product_name_ko="[포켓몬에디션] 빼바 리얼초콜릿 프로틴바 40g 4종 1택 (다크/화이트/쿠키앤크림/그릭요거트)",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000191560",
            source_product_id="A000000191560",
        )
    )

    assert result.product_name_display_ko == "리얼초콜릿 프로틴바"


def test_product_normalizer_removes_unscented_parenthetical_after_size(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"NIVEA","aliases":["니베아"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="니베아",
            product_name_ko="[NEW/ 피부장벽 2주 개선]니베아 리페어 앤 케어 바디로션 400ml (무향)",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000245253",
            source_product_id="A000000245253",
        )
    )

    assert result.product_name_display_ko == "리페어 앤 케어 바디로션"


def test_product_normalizer_removes_attached_trailing_option_count(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"MERYTHOD","aliases":["메리쏘드"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="메리쏘드",
            product_name_ko="메리쏘드 릴타투 벨벳 틴트5종",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000207242",
            source_product_id="A000000207242",
        )
    )

    assert result.product_name_display_ko == "릴타투 벨벳 틴트"


def test_product_normalizer_removes_simple_count_parenthetical(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"Blistex","aliases":["블리스텍스"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="블리스텍스",
            product_name_ko="블리스텍스 립 메덱스 립밤 대용량팩 7g (12개입)",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000162708",
            source_product_id="A000000162708",
        )
    )

    assert result.product_name_display_ko == "립 메덱스 립밤 대용량팩"


def test_product_normalizer_removes_descriptive_ampoule_parenthetical(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"Centellian24","aliases":["센텔리안24"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="센텔리안24",
            product_name_ko="[진정/속보습] 센텔리안24 마데카 데일리 리페어 앰플 50ml (첫단계진정앰플)",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000179256",
            source_product_id="A000000179256",
        )
    )

    assert result.product_name_display_ko == "마데카 데일리 리페어 앰플"


def test_product_normalizer_removes_ad_parenthetical_after_color_count(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"TIRTIR","aliases":["티르티르"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="티르티르",
            product_name_ko="[NEW/서옥공동개발] 티르티르 마스크 핏 레드 쿠션 파운데이션 18g 20 colors (AD)",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000254926",
            source_product_id="A000000254926",
        )
    )

    assert result.product_name_display_ko == "마스크 핏 레드 쿠션 파운데이션"


def test_product_normalizer_removes_cup_pack_parenthetical_and_choice_count(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"LINDSAY","aliases":["린제이"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="린제이",
            product_name_ko="[72관왕/1위] 린제이 매직(앰플) 모델링 팩 (컵팩) 3종 택1",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000103258",
            source_product_id="A000000103258",
        )
    )

    assert result.product_name_display_ko == "매직 앰플 모델링 팩"


def test_product_normalizer_flattens_variant_parentheses_without_dropping_text(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"ENTROPY","aliases":["엔트로피"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="엔트로피",
            product_name_ko="[필름광] 엔트로피 메이크업 참 틴트(글로시 겔) 10 Colors",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000216751",
            source_product_id="A000000216751",
        )
    )

    assert result.product_name_display_ko == "메이크업 참 틴트 글로시 겔"


def test_product_normalizer_removes_attached_planning_suffix_after_size_bundle(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"ILLIYOON","aliases":["일리윤"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="일리윤",
            product_name_ko="[5년연속1위] 일리윤 세라마이드 아토 로션기획(600ML+600ML)",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000171848",
            source_product_id="A000000171848",
        )
    )

    assert result.product_name_display_ko == "세라마이드 아토 로션"


def test_product_normalizer_removes_bracketed_variant_punctuation_from_display_name(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"Round A Round","aliases":["라운드어라운드"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="라운드어라운드",
            product_name_ko="[제주한정판매]라운드어라운드 센티드 모이스처라이징 립밤 [제주 감귤]",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000244702",
            source_product_id="A000000244702",
        )
    )

    assert result.product_name_display_ko == "센티드 모이스처라이징 립밤 제주 감귤"


def test_product_normalizer_removes_inner_beauty_count_suffix(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"CJ","aliases":["CJ"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="CJ",
            product_name_ko="[6월 올영픽/콜라겐] CJ 이너비 글로우앰플 6병 (6일분)",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000224239",
            source_product_id="A000000224239",
        )
    )

    assert result.product_name_display_ko == "이너비 글로우앰플"


def test_product_normalizer_removes_flattened_planning_suffixes(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        (
            '{"entries":['
            '{"official_en":"Aveeno","aliases":["아비노"],"sources":[]},'
            '{"official_en":"BEYOND","aliases":["비욘드"],"sources":[]},'
            '{"official_en":"Avene","aliases":["아벤느"],"sources":[]}'
            "]}"
        ),
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    cases = [
        (
            "아비노",
            "[71ml증정] 아비노 바디로션 532ml 단독기획(자몽향)",
            "바디로션",
        ),
        (
            "비욘드",
            "비욘드 엔젤아쿠아 소프트 페이셜 필링젤 더블기획(100mlX2입)(비건)",
            "엔젤아쿠아 소프트 페이셜 필링젤",
        ),
        (
            "아벤느",
            "아벤느 이드랑스 아쿠아 크림-인-젤 50ml 기획(에센스인로션25ml+클리낭스젤15ml)(2602)",
            "이드랑스 아쿠아 크림-인-젤",
        ),
    ]
    for brand, product_name, expected in cases:
        result = normalizer.normalize(
            ProductSourceRecord(
                source_brand_name=brand,
                product_name_ko=product_name,
                source="oliveyoung",
                source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000000001",
                source_product_id="A000000000001",
            )
        )

        assert result.product_name_display_ko == expected


def test_product_normalizer_removes_cross_choice_and_large_bundle_suffixes(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        (
            '{"entries":['
            '{"official_en":"Dr.G","aliases":["닥터지"],"sources":[]},'
            '{"official_en":"AESTURA","aliases":["에스트라"],"sources":[]},'
            '{"official_en":"ROUND LAB","aliases":["라운드랩"],"sources":[]},'
            '{"official_en":"CLIO","aliases":["클리오"],"sources":[]},'
            '{"official_en":"TOO COOL FOR SCHOOL","aliases":["투쿨포스쿨"],"sources":[]}'
            "]}"
        ),
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    cases = [
        (
            "닥터지",
            "닥터지 레드 블레미쉬 클리어 수딩 크림 70ml 1+1 교차선택",
            "레드 블레미쉬 클리어 수딩 크림",
        ),
        (
            "에스트라",
            "에스트라 아토베리어365 크림 80ml 더블기획(80ml+80ml) 교차선택",
            "아토베리어365 크림",
        ),
        (
            "라운드랩",
            "[수분진정] 라운드랩 1025 독도 토너 500ml 대용량 기획세트 (+100ml 증정)",
            "1025 독도 토너",
        ),
        (
            "클리오",
            "[단독기획] 클리오 킬커버 파운웨어 쿠션 더 뉴 15g 본품+리필",
            "킬커버 파운웨어 쿠션 더 뉴",
        ),
        (
            "투쿨포스쿨",
            "[증정기획] 투쿨포스쿨 아트클래스 바이로댕 쉐딩 9.5g+브러쉬",
            "아트클래스 바이로댕 쉐딩",
        ),
    ]
    for brand, product_name, expected in cases:
        result = normalizer.normalize(
            ProductSourceRecord(
                source_brand_name=brand,
                product_name_ko=product_name,
                source="oliveyoung",
                source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000000002",
                source_product_id="A000000000002",
            )
        )

        assert result.product_name_display_ko == expected
        assert result.product_name_display_en is None


def test_product_normalizer_ignores_polluted_source_brand_and_removes_spf_color_suffix(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="*[고커버/롱래스팅]",
            product_name_ko="*[고커버/롱래스팅] 티핏 아이시 핏 커버 쿠션 이엑스 3colors SPF50+ PA++++",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000229907",
            source_product_id="A000000229907",
        )
    )

    assert result.brand_ko is None
    assert result.product_name_display_ko == "티핏 아이시 핏 커버 쿠션 이엑스"


def test_product_normalizer_removes_mid_square_bracket_planning_suffix(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"REJURAN","aliases":["리쥬란"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="리쥬란",
            product_name_ko="[모공PDRN] 리쥬란 더마 힐러 포어 타이트닝 앰플 30ml [한정기획(+토너패드2매X6)/단품]_올영픽",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000243084",
            source_product_id="A000000243084",
        )
    )

    assert result.product_name_display_ko == "더마 힐러 포어 타이트닝 앰플"


def test_product_normalizer_removes_spf_color_count_suffix(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"espoir","aliases":["에스쁘아"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="에스쁘아",
            product_name_ko="[1등 더마 BB 크림] 에스쁘아 더마커버 블레미쉬 밤 40g 2colors SPF 50 PA++++",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000253243",
            source_product_id="A000000253243",
        )
    )

    assert result.product_name_display_ko == "더마커버 블레미쉬 밤"


def test_product_normalizer_removes_trailing_size_bundle_and_spf_noise(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        (
            '{"entries":['
            '{"official_en":"dAlba","aliases":["달바"],"sources":[]},'
            '{"official_en":"TOCOBO","aliases":["토코보"],"sources":[]},'
            '{"official_en":"ROUND LAB","aliases":["라운드랩"],"sources":[]},'
            '{"official_en":"Hada Labo","aliases":["하다라보"],"sources":[]},'
            '{"official_en":"make p:rem","aliases":["메이크프렘"],"sources":[]},'
            '{"official_en":"DINSI","aliases":["딘시"],"sources":[]},'
            '{"official_en":"LABO-H","aliases":["라보에이치"],"sources":[]},'
            '{"official_en":"espoir","aliases":["에스쁘아"],"sources":[]},'
            '{"official_en":"Anua","aliases":["아누아"],"sources":[]},'
            '{"official_en":"UREAGE","aliases":["유리아쥬"],"sources":[]},'
            '{"official_en":"DASHU","aliases":["다슈"],"sources":[]},'
            '{"official_en":"Avene","aliases":["아벤느"],"sources":[]},'
            '{"official_en":"KIMJEONGMOON ALOE","aliases":["김정문알로에"],"sources":[]},'
            '{"official_en":"Burt\'s Bees","aliases":["버츠비"],"sources":[]},'
            '{"official_en":"O HUI","aliases":["오휘"],"sources":[]}'
            "]}"
        ),
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    cases = [
        (
            "달바",
            "[생기톤업] 달바 워터풀 톤업 선크림 65ml + 65ml 대용량 기획세트",
            "워터풀 톤업 선크림",
        ),
        (
            "토코보",
            "[수분선크림/화잘먹] 토코보 바이오 워터리 선크림 50mL SPF50+ PA++++",
            "바이오 워터리 선크림",
        ),
        (
            "라운드랩",
            "[NEW] 라운드랩 독도 클렌징 오일 200ml + 독도 클렌저 150ml 기획",
            "독도 클렌징 오일",
        ),
        (
            "하다라보",
            "[피지제거/말끔결/고보습] 하다라보 고쿠쥰 클렌징 오일 200mL*2 기획",
            "고쿠쥰 클렌징 오일",
        ),
        (
            "메이크프렘",
            "[뽀용톤업/무기자차] 메이크프렘 수딩 핑크 톤업 선크림 40ml+40ml 기획 (+20ml)",
            "수딩 핑크 톤업 선크림",
        ),
        (
            "딘시",
            "딘시 프리미엄 비건 블루 톤업 선크림 50ml+20ml 증량기획",
            "프리미엄 비건 블루 톤업 선크림",
        ),
        (
            "라보에이치",
            "라보에이치 두피강화클리닉 앰플토닉 100ML+100ML리필 기획",
            "두피강화클리닉 앰플토닉",
        ),
        (
            "에스쁘아",
            "[100시간 지속/고커버] 에스쁘아 비벨벳 커버쿠션 SPF42 PA++ 본품+리필",
            "비벨벳 커버쿠션",
        ),
        (
            "아누아",
            "[수지pick/화해1위] 아누아 피디알엔 히알루론산 캡슐 100 세럼 1ml*10ea",
            "피디알엔 히알루론산 캡슐 100 세럼",
        ),
        (
            "유리아쥬",
            "[대용량/단독기획] 유리아쥬 진피 마일드 젤 500ml+진-8 100ml",
            "진피 마일드 젤",
        ),
        (
            "다슈",
            "[변우석 Pick]다슈 포맨 프리미엄 울트라 본드 젤 다운펌 100ml*2입",
            "포맨 프리미엄 울트라 본드 젤 다운펌",
        ),
        (
            "아벤느",
            "아벤느 클리낭스 클렌징 젤 200ml*피지잡는 *약산성클렌저 *클렌징폼",
            "클리낭스 클렌징 젤",
        ),
        (
            "김정문알로에",
            "[증량기획] 김정문알로에 큐어 리알로에 워터 젤리 토너 500ml+50ml [젤리토너]",
            "큐어 리알로에 워터 젤리 토너",
        ),
        (
            "버츠비",
            "버츠비 석류 립밤 듀오팩 (버츠비 석류 립밤 4.25g x 2)",
            "석류 립밤 듀오팩",
        ),
        (
            "오휘",
            "오휘 얼티밋 핏 진 쿠션 본품15g+리필15g (롱웨어/톤업)",
            "얼티밋 핏 진 쿠션",
        ),
    ]
    for brand, product_name, expected in cases:
        result = normalizer.normalize(
            ProductSourceRecord(
                source_brand_name=brand,
                product_name_ko=product_name,
                source="oliveyoung",
                source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000000003",
                source_product_id="A000000000003",
            )
        )

        assert result.product_name_display_ko == expected


def test_product_normalizer_removes_spaced_korean_brand_alias_from_display_name(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"BIOHEAL BOH","aliases":["바이오힐보","BIOHEAL BOH"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="바이오힐보",
            product_name_ko="[탄력토너] 바이오힐 보 프로바이오덤 3D 리프팅 에센셜 토너 150ml",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000203207",
            source_product_id="A000000203207",
        )
    )

    assert result.product_name_display_ko == "프로바이오덤 3D 리프팅 에센셜 토너"


def test_product_normalizer_removes_leading_collaboration_parenthetical_tag(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"CLIO","aliases":["클리오"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://glowpick.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="클리오",
            product_name_ko="(클리오X국가유산청) 프로 아이 팔레트 에어",
            source="glowpick",
            source_url="https://glowpick.co.kr/product/183245",
            source_product_id="183245",
        )
    )

    assert result.product_name_display_ko == "프로 아이 팔레트 에어"
    assert result.product_name_en is None
    assert result.product_name_display_en is None


def test_product_normalizer_removes_stuck_size_and_color_option_suffix(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"FOR BEAUT","aliases":["포뷰트"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="포뷰트",
            product_name_ko="포뷰트 두피 타투15g 블랙/브라운 단품/기획",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000223552",
            source_product_id="A000000223552",
        )
    )

    assert result.product_name_display_ko == "두피 타투"
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


def test_product_normalizer_removes_verified_shade_suffix_from_display_name(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"OLENS","aliases":["오렌즈","OLENS"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://glowpick.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="오렌즈",
            product_name_ko="글로이 티어 원데이 그레이",
            shade="그레이",
            source="glowpick",
            source_url="https://glowpick.co.kr/product/183668",
            source_product_id="183668",
        )
    )

    assert result.product_name_ko == "글로이 티어 원데이 그레이"
    assert result.product_name_display_ko == "글로이 티어 원데이"
    assert result.shade == "그레이"
    assert result.product_name_en is None
    assert result.product_name_display_en is None


def test_product_normalizer_removes_numbered_shade_suffix_from_display_name(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"rom&nd","aliases":["롬앤","rom&nd"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="롬앤",
            product_name_ko="롬앤 베러 댄 쉐입 쉐딩 02 그레이쿨",
            shade="02 그레이쿨",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000000001",
            source_product_id="A000000000001",
        )
    )

    assert result.product_name_display_ko == "베러 댄 쉐입 쉐딩"
    assert result.shade == "02 그레이쿨"
    assert result.product_name_en is None


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


def test_product_normalizer_removes_compact_korean_subbrand_prefix_from_display_name(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        (
            '{"entries":['
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
            product_name_ko="[10만나노히알/3초수분플럼핑]비긴스바이정샘물 블루 수국 히알 수분세럼 30ml",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000248097",
            source_product_id="A000000248097",
        )
    )

    assert result.brand_ko == "비긴스 바이 정샘물"
    assert result.product_name_display_ko == "블루 수국 히알 수분세럼"


def test_product_normalizer_removes_attached_gift_planning_suffix_from_display_name(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"RYO","aliases":["려"],"sources":[]}]}',
        encoding="utf-8",
    )
    normalizer = ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )

    result = normalizer.normalize(
        ProductSourceRecord(
            source_brand_name="려",
            product_name_ko="[뿌리볼륨스타일링]려 루트젠 뿌리볼류머 150ML+샴푸증정기획_올영단독한정",
            source="oliveyoung",
            source_url="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000240265",
            source_product_id="A000000240265",
        )
    )

    assert result.product_name_display_ko == "루트젠 뿌리볼류머"
    assert result.product_name_display_en is None


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


def test_project_brand_registry_maps_new_coverage_brands() -> None:
    resolver = BrandResolver(PROJECT_REGISTRY_PATH)

    beyond_match = resolver.match_text("비욘드 수분 로션")
    benton_match = resolver.match_text("벤튼 시카 수분 선쿠션")

    assert beyond_match is not None
    assert beyond_match.official_en == "BEYOND"
    assert benton_match is not None
    assert benton_match.official_en == "Benton"
