import json
from pathlib import Path

import pytest

from app.data_collector.local_catalog import LocalVerifiedCatalogCollector


PROJECT_CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "verified_products.json"


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
