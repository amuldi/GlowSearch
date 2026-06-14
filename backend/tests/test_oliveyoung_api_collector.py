import httpx
import pytest

from app.core.config import Settings
from app.data_collector.base import SourceUnavailableError
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
                            "categoryName": "스킨케어 > 선케어",
                            "rating": 4.8,
                            "reviewCount": "1,234",
                            "options": ["50ml"],
                            "inStock": True,
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
        collector = OliveYoungPublicApiCollector(
            Settings(oliveyoung_public_api_rate_limit_per_second=0),
            client=client,
        )
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
    assert records[0].category == "스킨케어 > 선케어"
    assert records[0].rating == 4.8
    assert records[0].review_count == 1234
    assert records[0].options == ["50ml"]
    assert records[0].sold_out is False
    assert records[0].source_url == (
        "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000255125"
    )
    assert records[1].source_brand_name == "라운드랩"
    assert records[1].regular_price == 18000
    assert records[1].original_price == 18000
    assert records[1].sale_price is None
    assert records[1].discount_rate is None


@pytest.mark.asyncio
async def test_oliveyoung_public_api_collector_uses_large_page_for_broad_search() -> None:
    calls: list[tuple[int, int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/oliveyoung/products"
        page = int(request.url.params["page"])
        size = int(request.url.params["size"])
        calls.append((page, size))
        products = [
            {
                "goodsNumber": f"A{i:012d}",
                "goodsName": f"정샘물 테스트 상품 {i}",
                "imageUrl": f"https://image.oliveyoung.co.kr/item-{i}.png?l=ko",
                "priceToPay": 10000 + i,
                "originalPrice": 12000 + i,
                "discountRate": 10,
            }
            for i in range(size)
        ]
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "products": products,
                    "nextPage": True,
                },
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://mcp.aka.page",
    ) as client:
        collector = OliveYoungPublicApiCollector(
            Settings(oliveyoung_public_api_rate_limit_per_second=0),
            client=client,
        )
        records = await collector.search("정샘물", limit=48)

    assert calls == [(1, 48)]
    assert len(records) == 48
    assert records[0].source_brand_name == "정샘물"


@pytest.mark.asyncio
async def test_oliveyoung_public_api_collector_continues_when_total_count_indicates_more() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        calls.append(page)
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "products": [
                        {
                            "goodsNumber": f"A00000000000{page}",
                            "goodsName": f"투쿨포스쿨 테스트 상품 {page}",
                            "priceToPay": 10000 + page,
                            "originalPrice": 12000 + page,
                            "discountRate": 10,
                        }
                    ],
                    "totalCount": 2,
                },
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://mcp.aka.page",
    ) as client:
        collector = OliveYoungPublicApiCollector(
            Settings(oliveyoung_public_api_rate_limit_per_second=0),
            client=client,
        )
        records = await collector.search("투쿨포스쿨", limit=3)

    assert calls == [1, 2]
    assert [record.source_product_id for record in records] == [
        "A000000000001",
        "A000000000002",
    ]


@pytest.mark.asyncio
async def test_oliveyoung_public_api_collector_retries_transient_errors() -> None:
    calls = 0
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, text="temporary unavailable")
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "products": [
                        {
                            "goodsNumber": "A000000000001",
                            "goodsName": "뮤드 테스트 틴트",
                            "priceToPay": 10000,
                            "originalPrice": 12000,
                            "discountRate": 16,
                        }
                    ],
                    "nextPage": False,
                },
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://mcp.aka.page",
    ) as client:
        collector = OliveYoungPublicApiCollector(
            Settings(
                oliveyoung_public_api_rate_limit_per_second=0,
                oliveyoung_public_api_retry_attempts=2,
                oliveyoung_public_api_retry_base_delay_seconds=0,
            ),
            client=client,
            sleep=fake_sleep,
        )
        records = await collector.search("뮤드", limit=1)

    assert calls == 2
    assert sleep_calls == [0]
    assert records[0].source_product_id == "A000000000001"


@pytest.mark.asyncio
async def test_oliveyoung_public_api_collector_reports_http_error_type_when_message_is_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("", request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://mcp.aka.page",
    ) as client:
        collector = OliveYoungPublicApiCollector(
            Settings(
                oliveyoung_public_api_rate_limit_per_second=0,
                oliveyoung_public_api_retry_attempts=1,
            ),
            client=client,
        )
        with pytest.raises(SourceUnavailableError) as exc_info:
            await collector.search("선세럼", limit=1)

    assert "ConnectError" in str(exc_info.value)


@pytest.mark.asyncio
async def test_oliveyoung_public_api_collector_backs_off_on_bot_detection() -> None:
    async def fake_sleep(_seconds: float) -> None:
        return None

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="<html><title>잠시만 기다려 주세요 - 올리브영</title><script>cf_chl</script>",
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://mcp.aka.page",
    ) as client:
        collector = OliveYoungPublicApiCollector(
            Settings(
                oliveyoung_public_api_rate_limit_per_second=0,
                oliveyoung_public_api_retry_attempts=1,
            ),
            client=client,
            sleep=fake_sleep,
        )
        with pytest.raises(SourceUnavailableError):
            await collector.search("젤", limit=1)
