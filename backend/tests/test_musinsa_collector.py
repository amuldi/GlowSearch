import httpx
import pytest

from app.core.config import Settings
from app.data_collector.musinsa import MusinsaProductCollector


@pytest.mark.asyncio
async def test_musinsa_product_collector_maps_public_search_items() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api2/dp/v2/plp/goods"
        assert request.url.params["keyword"] == "퓌"
        assert request.url.params["category"] == "104"
        return httpx.Response(
            200,
            json={
                "data": {
                    "list": [
                        {
                            "goodsNo": 3995579,
                            "goodsName": "퓌 3D 볼류밍 글로스 (17 Colors)",
                            "goodsLinkUrl": "https://www.musinsa.com/products/3995579",
                            "thumbnail": "https://image.msscdn.net/item.jpg",
                            "normalPrice": 18000,
                            "price": 16200,
                            "brand": "fwee",
                            "brandName": "퓌",
                        }
                    ]
                },
                "meta": {"result": "SUCCESS"},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        collector = MusinsaProductCollector(Settings(), client=client)
        records = await collector.search("퓌", 3)

    assert len(records) == 1
    assert records[0].source_brand_name == "퓌"
    assert records[0].product_name_ko == "퓌 3D 볼류밍 글로스 (17 Colors)"
    assert records[0].regular_price == 18000
    assert records[0].shade == "17 Colors"
    assert records[0].image_url == "https://image.msscdn.net/item.jpg"
    assert records[0].source == "musinsa"
    assert records[0].source_url == "https://www.musinsa.com/products/3995579"


@pytest.mark.asyncio
async def test_musinsa_product_collector_uses_beauty_category_only() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["category"] == "104"
        assert request.url.params["keyword"] == "푸마"
        return httpx.Response(
            200,
            json={
                "data": {"list": []},
                "meta": {"result": "SUCCESS"},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        collector = MusinsaProductCollector(Settings(), client=client)
        records = await collector.search("푸마", 3)

    assert records == []


@pytest.mark.asyncio
async def test_musinsa_product_collector_paginates_for_large_limits() -> None:
    seen_pages: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params["page"]
        seen_pages.append(page)
        return httpx.Response(
            200,
            json={
                "data": {
                    "list": [
                        {
                            "goodsNo": f"{page}01",
                            "goodsName": f"틴트 {page}",
                            "goodsLinkUrl": f"https://www.musinsa.com/products/{page}01",
                            "thumbnail": "https://image.msscdn.net/item.jpg",
                            "normalPrice": 18000,
                            "brand": "fwee",
                            "brandName": "퓌",
                        }
                    ]
                },
                "meta": {"result": "SUCCESS"},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        collector = MusinsaProductCollector(Settings(), client=client)
        records = await collector.search("틴트", 96)

    assert seen_pages == ["1", "2"]
    assert len(records) == 2
