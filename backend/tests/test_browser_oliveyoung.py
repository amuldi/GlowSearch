import pytest

from app.core.config import Settings
from app.data_collector.base import SourceUnavailableError
from app.data_collector.browser_oliveyoung import BrowserOliveYoungCollector


BASE_URL = "https://www.oliveyoung.co.kr"


@pytest.mark.asyncio
async def test_browser_collector_parses_mock_html() -> None:
    async def load_html(value: str) -> str:
        if value.startswith("https://"):
            return """
            <div data-qa-name="text-product-title">
              <h3>BRTC V10 비타민 화이트닝 슬리핑팩 100ml</h3>
            </div>
            <span data-qa-name="text-product-discount-price">24,000원</span>
            """
        return """
        <ul class="cate_prd_list">
          <li>
            <div class="prd_info">
              <a href="javascript:common.link.moveGoodsDetail('A000000113988');">
                <img src="//image.oliveyoung.co.kr/item.jpg" />
              </a>
              <span class="tx_brand">BRTC</span>
              <p class="tx_name">BRTC V10 비타민 화이트닝 슬리핑팩 100ml</p>
              <p class="prd_price"><span class="tx_org">24,000원</span></p>
            </div>
          </li>
        </ul>
        """

    collector = BrowserOliveYoungCollector(
        Settings(oliveyoung_base_url=BASE_URL),
        html_loader=load_html,
    )

    records = await collector.search("틴트", limit=3)

    assert len(records) == 1
    assert records[0].source_brand_name == "BRTC"
    assert records[0].regular_price == 24000
    assert records[0].product_name_ko == "BRTC V10 비타민 화이트닝 슬리핑팩 100ml"
    assert records[0].source == "oliveyoung"


@pytest.mark.asyncio
async def test_browser_collector_raises_on_blocked_html() -> None:
    async def load_html(keyword: str) -> str:
        return "<html><body>Checking your browser before accessing cf-challenge</body></html>"

    collector = BrowserOliveYoungCollector(
        Settings(oliveyoung_base_url=BASE_URL),
        html_loader=load_html,
    )

    with pytest.raises(SourceUnavailableError, match="blocked"):
        await collector.search("틴트", limit=3)


@pytest.mark.asyncio
async def test_browser_collector_raises_on_empty_html() -> None:
    async def load_html(keyword: str) -> str:
        return ""

    collector = BrowserOliveYoungCollector(
        Settings(oliveyoung_base_url=BASE_URL),
        html_loader=load_html,
    )

    with pytest.raises(SourceUnavailableError, match="empty HTML"):
        await collector.search("틴트", limit=3)
