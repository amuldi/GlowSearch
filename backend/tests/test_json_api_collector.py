import httpx
import pytest

from app.data_collector.json_api import JsonApiProductCollector


@pytest.mark.asyncio
async def test_json_api_product_collector_maps_normalized_product_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["q"] == "tint"
        assert request.url.params["limit"] == "2"
        return httpx.Response(
            200,
            json={
                "products": [
                    {
                        "brand": "rom&nd",
                        "productName": "Juicy Lasting Tint",
                        "price": 13000,
                        "imageUrl": "https://example.test/tint.jpg",
                        "productUrl": "https://example.test/products/1",
                        "id": "sku-1",
                    }
                ]
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://example.test",
    ) as client:
        collector = JsonApiProductCollector(
            name="discovery:json-api",
            base_url="https://example.test/products",
            timeout_seconds=1,
            client=client,
        )
        records = await collector.search("tint", 2)

    assert len(records) == 1
    assert records[0].source == "discovery:json-api"
    assert records[0].source_brand_name == "rom&nd"
    assert records[0].product_name_ko == "Juicy Lasting Tint"
    assert records[0].source_product_id == "sku-1"


@pytest.mark.asyncio
async def test_json_api_product_collector_skips_non_barcode_queries_when_configured() -> None:
    collector = JsonApiProductCollector(
        name="barcode:lookup",
        base_url="https://example.test/products",
        timeout_seconds=1,
        barcode_only=True,
    )

    assert await collector.search("립틴트", 2) == []
