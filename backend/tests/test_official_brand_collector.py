import httpx
import pytest

from app.core.config import Settings
from app.data_collector.official_brand import OfficialBrandSiteCollector


@pytest.mark.asyncio
async def test_official_brand_collector_searches_matched_brand_site(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        """
        {
          "entries": [
            {
              "official_en": "OFFICIAL BRAND",
              "aliases": ["공식브랜드"],
              "sources": ["https://brand.example"]
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/product/search.html"
        assert request.url.params["keyword"] == "틴트"
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="""
            <ul>
              <li class="xans-record-">
                <a href="/product/tint/10"><img src="/tint.jpg" /></a>
                <p class="name">공식 틴트</p>
                <span class="price">18,000원</span>
              </li>
            </ul>
            """,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        collector = OfficialBrandSiteCollector(Settings(), registry_path, client=client)
        records = await collector.search("공식브랜드 틴트", 3)

    assert len(records) == 1
    assert records[0].source == "official"
    assert records[0].source_brand_name == "OFFICIAL BRAND"
    assert records[0].product_name_ko == "공식 틴트"
    assert records[0].regular_price == 18000
    assert records[0].image_url == "https://brand.example/tint.jpg"
    assert records[0].source_url == "https://brand.example/product/tint/10"


@pytest.mark.asyncio
async def test_official_brand_collector_keeps_sold_out_products_without_price(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        """
        {
          "entries": [
            {
              "official_en": "OFFICIAL BRAND",
              "aliases": ["공식브랜드"],
              "sources": ["https://brand.example"]
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="""
            <ul>
              <li class="xans-record-">
                <a href="/product/sold-out/11"><img src="/sold-out.jpg" /></a>
                <p class="name">품절 공식 상품</p>
                <span class="soldout">품절</span>
              </li>
            </ul>
            """,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        collector = OfficialBrandSiteCollector(Settings(), registry_path, client=client)
        records = await collector.search("공식브랜드 품절 상품", 3)

    assert len(records) == 1
    assert records[0].product_name_ko == "품절 공식 상품"
    assert records[0].regular_price is None
    assert records[0].source_url == "https://brand.example/product/sold-out/11"
