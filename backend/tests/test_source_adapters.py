import httpx
import pytest

from app.source_adapters import OpenBeautyFactsCollector, SerpApiShoppingCollector


@pytest.mark.asyncio
async def test_serpapi_shopping_collector_maps_shopping_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["engine"] == "google_shopping"
        assert request.url.params["q"] == "lip tint"
        return httpx.Response(
            200,
            json={
                "shopping_results": [
                    {
                        "title": "rom&nd Juicy Lasting Tint",
                        "product_id": "SERP1",
                        "product_link": "https://example.test/product",
                        "thumbnail": "https://example.test/image.jpg",
                        "extracted_price": 14,
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        collector = SerpApiShoppingCollector(
            api_key="test-key",
            timeout_seconds=1,
            client=client,
        )
        records = await collector.search("lip tint", limit=5)

    assert len(records) == 1
    assert records[0].product_name_ko == "rom&nd Juicy Lasting Tint"
    assert records[0].source == "serpapi:google-shopping"
    assert records[0].source_url == "https://example.test/product"
    assert records[0].regular_price == 14


@pytest.mark.asyncio
async def test_open_beauty_facts_collector_maps_barcode_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/1234567890123.json")
        return httpx.Response(
            200,
            json={
                "product": {
                    "brands": "Example Beauty",
                    "product_name": "Hydrating Cream",
                    "image_url": "https://example.test/cream.jpg",
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        collector = OpenBeautyFactsCollector(timeout_seconds=1, client=client)
        records = await collector.search("1234567890123", limit=5)

    assert len(records) == 1
    assert records[0].source_brand_name == "Example Beauty"
    assert records[0].product_name_ko == "Hydrating Cream"
    assert records[0].source == "openbeautyfacts"
    assert records[0].source_product_id == "1234567890123"
