import httpx

from app.normalizer.musinsa import MusinsaBrandResolver


def test_musinsa_brand_resolver_uses_exact_brand_name_eng() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api2/dp/v1/plp/brand"
        assert request.url.params["keyword"] == "퓌"
        return httpx.Response(
            200,
            json={
                "data": {
                    "list": [
                        {
                            "brand": "fwee",
                            "brandName": "퓌",
                            "brandNameEng": "FWEE",
                        }
                    ]
                },
                "meta": {"result": "SUCCESS"},
            },
        )

    resolver = MusinsaBrandResolver(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert resolver.resolve("퓌") == "FWEE"


def test_musinsa_brand_resolver_does_not_guess_ambiguous_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "list": [
                        {"brand": "nike", "brandName": "나이키", "brandNameEng": "NIKE"},
                        {
                            "brand": "newbalance",
                            "brandName": "뉴발란스",
                            "brandNameEng": "NEW BALANCE",
                        },
                    ]
                }
            },
        )

    resolver = MusinsaBrandResolver(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert resolver.resolve("나") is None
