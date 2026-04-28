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
    assert resolver.match_text("투쿨포스쿨 스킨틴트").official_en == "TOO COOL FOR SCHOOL"


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
        "brand_en": None,
        "product_name_ko": "제품",
        "price": None,
        "currency": "KRW",
        "shade": None,
        "image_url": None,
        "source_url": None,
        "source": "oliveyoung",
    }
