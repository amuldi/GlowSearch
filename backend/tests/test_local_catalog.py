import json

import pytest

from app.data_collector.local_catalog import LocalVerifiedCatalogCollector


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
