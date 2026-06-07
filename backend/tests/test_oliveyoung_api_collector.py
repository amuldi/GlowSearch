import httpx
import pytest

from app.core.config import Settings
from app.data_collector.oliveyoung_api import OliveYoungPublicApiCollector


@pytest.mark.asyncio
async def test_oliveyoung_public_api_collector_maps_prices_and_source_url() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/oliveyoung/products"
        assert request.url.params["keyword"] == "선크림"
        page = int(request.url.params["page"])
        calls.append(page)
        if page == 2:
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "products": [
                            {
                                "goodsNumber": "A000000255126",
                                "goodsName": "라운드랩 무할인 선크림",
                                "imageUrl": "https://image.oliveyoung.co.kr/item-2.png?l=ko",
                                "priceToPay": 18000,
                                "originalPrice": 18000,
                                "discountRate": 0,
                            }
                        ],
                        "nextPage": False,
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "products": [
                        {
                            "goodsNumber": "A000000255125",
                            "goodsName": "라운드랩 자작나무 수분 톤업 선크림",
                            "imageUrl": "https://image.oliveyoung.co.kr/item.png?l=ko",
                            "priceToPay": 23900,
                            "originalPrice": 25000,
                            "discountRate": 4,
                        }
                    ],
                    "nextPage": True,
                },
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://mcp.aka.page",
    ) as client:
        collector = OliveYoungPublicApiCollector(Settings(), client=client)
        records = await collector.search("선크림", limit=5)

    assert calls == [1, 2]
    assert len(records) == 2
    assert records[0].source == "oliveyoung"
    assert records[0].source_brand_name == "라운드랩"
    assert records[0].source_product_id == "A000000255125"
    assert records[0].regular_price == 23900
    assert records[0].original_price == 25000
    assert records[0].sale_price == 23900
    assert records[0].discount_rate == 4
    assert records[0].source_url == (
        "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000255125"
    )
    assert records[1].source_brand_name == "라운드랩"
    assert records[1].regular_price == 18000
    assert records[1].original_price == 18000
    assert records[1].sale_price is None
    assert records[1].discount_rate is None
