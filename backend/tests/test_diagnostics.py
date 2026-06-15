import json

from app.api.routes import _adapter_readiness, _verified_catalog_stats
from app.core.config import Settings


def test_verified_catalog_stats_counts_sources_and_english_names(tmp_path) -> None:
    catalog_path = tmp_path / "verified_products.json"
    catalog_path.write_text(
        json.dumps(
            {
                "products": [
                    {
                        "canonical_product_id": "verified:one",
                        "brand_ko": "브랜드",
                        "product_name_ko": "제품",
                        "product_name_en": "Product",
                        "source": "official",
                        "source_url": "https://brand.example/product",
                    },
                    {
                        "canonical_product_id": "verified:two",
                        "brand_ko": "브랜드",
                        "product_name_ko": "제품2",
                        "source_url": "https://www.musinsa.com/products/1",
                    },
                    {
                        "brand_ko": "브랜드",
                        "product_name_ko": "제품3",
                        "source": "oliveyoung:verified-cache",
                        "offers": [
                            {
                                "source": "musinsa",
                                "source_url": "https://www.musinsa.com/products/2",
                            }
                        ],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    stats = _verified_catalog_stats(catalog_path)

    assert stats["exists"] is True
    assert stats["total"] == 3
    assert stats["canonical_product_id"] == 2
    assert stats["product_name_en"] == 1
    assert stats["source_counts"] == {
        "musinsa": 2,
        "official": 1,
        "oliveyoung": 1,
    }


def test_adapter_readiness_explains_disabled_and_missing_base_url(tmp_path) -> None:
    settings = Settings(
        verified_catalog_path=tmp_path / "verified_products.json",
        oliveyoung_public_api_enabled=True,
        musinsa_api_enabled=False,
        musinsa_api_base_url="https://provider.example/musinsa",
        oliveyoung_global_api_enabled=True,
        oliveyoung_global_api_base_url=None,
        official_brand_api_enabled=True,
        official_brand_api_base_url="https://provider.example/official",
    )

    readiness = _adapter_readiness(settings)

    assert readiness["oliveyoung_public_api"]["reason"] == "ready"
    assert readiness["musinsa"]["reason"] == "disabled"
    assert readiness["musinsa"]["base_url_configured"] is True
    assert readiness["oliveyoung_global"]["reason"] == "missing_base_url"
    assert readiness["official_brand"]["reason"] == "ready"
