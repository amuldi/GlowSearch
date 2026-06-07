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
    assert (
        resolver.resolve(None, "[기획] 비긴스 바이 정샘물 흔적 세럼")
        == "BEGINS BY JUNGSAEMMOOL"
    )
    assert resolver.match_text("투쿨포스쿨 스킨틴트").official_en == "TOO COOL FOR SCHOOL"
    etude_match = resolver.match_text("에뛰ㄷ")
    assert etude_match.official_en == "ETUDE"
    assert etude_match.matched_alias == "에뛰드"
    assert etude_match.matched_text == "에뛰ㄷ"


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
        "brand_ko": "한글브랜드",
        "brand_en": None,
        "product_name_ko": "제품",
        "price": None,
        "original_price": None,
        "sale_price": None,
        "discount_rate": None,
        "currency": "KRW",
        "shade": None,
        "image_url": None,
        "source_url": None,
        "source": "oliveyoung",
        "source_label": None,
        "source_priority": None,
    }


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
