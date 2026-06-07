from app.index.store import JsonProductIndexStore
from app.models.product import ProductSourceRecord


async def _upsert_romand(store: JsonProductIndexStore, price: int = 13000) -> None:
    await store.upsert(
        [
            ProductSourceRecord(
                source_brand_name="롬앤",
                product_name_ko="롬앤 글래스팅 틴트",
                regular_price=price,
                currency="KRW",
                image_url="https://example.test/item.jpg",
                source="oliveyoung",
                source_url="https://example.test/product/1",
                source_product_id="A1",
            )
        ],
        queries=["롬앤 틴트", "romand tint"],
    )


async def test_json_product_index_store_returns_matching_records(tmp_path) -> None:
    store = JsonProductIndexStore(tmp_path / "product_index.json")
    await _upsert_romand(store)

    result = await store.search(["romand tint"], limit=10)

    assert result.is_stale is False
    assert len(result.records) == 1
    assert result.records[0].source_brand_name == "롬앤"
    assert result.records[0].regular_price == 13000


async def test_json_product_index_store_marks_expired_records_stale(tmp_path) -> None:
    store = JsonProductIndexStore(
        tmp_path / "product_index.json",
        fresh_ttl_seconds=0,
        stale_ttl_seconds=60,
    )
    await _upsert_romand(store)

    result = await store.search(["롬앤 틴트"], limit=10)

    assert result.is_stale is True
    assert len(result.records) == 1


async def test_json_product_index_store_seeds_verified_catalog(tmp_path) -> None:
    catalog_path = tmp_path / "verified_products.json"
    catalog_path.write_text(
        """
        {
          "products": [
            {
              "brand_en": "mixsoon",
              "brand_ko": "믹순",
              "product_name_ko": "믹순 히알레배 포어 블러링 크림 50ml",
              "price": 14900,
              "source_url": "https://example.test/mixsoon",
              "goods_no": "M1",
              "keywords": ["hyalraebae", "cream"]
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    store = JsonProductIndexStore(
        tmp_path / "product_index.json",
        seed_catalog_path=catalog_path,
    )
    result = await store.search(["hyalraebae cream"], limit=10)

    assert result.is_stale is False
    assert len(result.records) == 1
    assert result.records[0].source_brand_name == "믹순"
