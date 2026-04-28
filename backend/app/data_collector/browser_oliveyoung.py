from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlencode

from app.core.config import Settings
from app.data_collector.base import SourceUnavailableError
from app.models.product import ProductSourceRecord
from app.parser.oliveyoung_html import parse_detail_page, parse_search_results


HtmlLoader = Callable[[str], Awaitable[str]]


PRODUCT_WAIT_SELECTOR = (
    "ul.cate_prd_list > li, "
    "ul.prd_list > li, "
    "li[data-ref-goodsno], "
    "li[data-goods-no], "
    "div.prd_info"
)
READY_WAIT_SELECTOR = f"{PRODUCT_WAIT_SELECTOR}, .no_result, .search_no_data, [class*='noData']"
DETAIL_WAIT_SELECTOR = (
    "[data-qa-name='text-product-title'], "
    "[data-qa-name='text-product-discount-price'], "
    ".prd_detail_box, "
    ".prd_name, "
    "[class*='price-area']"
)
BLOCKED_MARKERS = (
    "cf-challenge",
    "cf-mitigated",
    "challenge-platform",
    "verify you are human",
    "checking your browser",
)


class BrowserOliveYoungCollector:
    name = "oliveyoung:browser"

    def __init__(self, settings: Settings, html_loader: HtmlLoader | None = None):
        self._settings = settings
        self._base_url = settings.oliveyoung_base_url.rstrip("/")
        self._html_loader = html_loader
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._browser_lock = asyncio.Lock()

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        keyword = keyword.strip()
        if not keyword:
            return []

        records = await self._load_search_records(keyword, limit)
        if self._should_enrich(records):
            records = await self._enrich_detail_pages(records)
        return records[:limit]

    async def _load_search_records(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        page_size = max(1, min(self._settings.oliveyoung_search_page_size, 48))
        max_pages = max(1, self._settings.oliveyoung_search_max_pages)
        target_pages = min(max_pages, max(1, math.ceil(limit / page_size)))
        records: list[ProductSourceRecord] = []
        seen: set[str] = set()

        for page in range(1, target_pages + 1):
            html = await self._load_search_html(keyword, page=page, page_size=page_size)
            if not html.strip():
                raise SourceUnavailableError("Olive Young browser session returned empty HTML")
            if self._is_blocked_html(html):
                raise SourceUnavailableError("Olive Young browser session was blocked")

            page_records = parse_search_results(html, base_url=self._base_url, limit=page_size)
            new_records = []
            for record in page_records:
                key = record.source_product_id or f"{record.source_brand_name}:{record.product_name_ko}"
                if key in seen:
                    continue
                seen.add(key)
                new_records.append(record)
            if not new_records:
                break
            records.extend(new_records)
            if len(records) >= limit:
                break
        return records

    async def _load_search_html(self, keyword: str, *, page: int, page_size: int) -> str:
        if self._html_loader:
            return await self._html_loader(keyword)

        query = urlencode(
            {
                "query": keyword,
                "pageIdx": page,
                "rowsPerPage": page_size,
                "sort": "WEIGHT/DESC",
            }
        )
        url = f"{self._base_url}/store/search/getSearchMain.do?{query}"
        return await self._load_url_html(url, wait_selector=READY_WAIT_SELECTOR)

    async def _load_url_html(self, url: str, wait_selector: str = DETAIL_WAIT_SELECTOR) -> str:
        if self._html_loader:
            return await self._html_loader(url)

        try:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        except ImportError as exc:
            raise SourceUnavailableError(
                "Playwright is not installed. Run `pip install -r requirements.txt`."
            ) from exc

        timeout_ms = int(self._settings.browser_timeout_seconds * 1000)

        try:
            browser = await self._get_browser()
            context = await browser.new_context(
                user_agent=self._settings.request_user_agent,
                locale="ko-KR",
                viewport={"width": 1365, "height": 900},
                extra_http_headers={
                    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                },
            )
            try:
                page = await context.new_page()
                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )
                if response and response.status in {403, 429}:
                    raise SourceUnavailableError(
                        f"Olive Young browser request blocked with HTTP {response.status}"
                    )
                await self._wait_for_render(page, timeout_ms, wait_selector)
                return await page.content()
            finally:
                await context.close()
        except SourceUnavailableError:
            raise
        except PlaywrightTimeoutError as exc:
            raise SourceUnavailableError("Olive Young browser request timed out") from exc
        except Exception as exc:
            raise SourceUnavailableError(f"Olive Young browser collector failed: {exc}") from exc

    async def _enrich_detail_pages(
        self,
        records: list[ProductSourceRecord],
    ) -> list[ProductSourceRecord]:
        semaphore = asyncio.Semaphore(self._settings.detail_concurrency)

        async def enrich(record: ProductSourceRecord) -> ProductSourceRecord:
            if not record.source_url:
                return record
            async with semaphore:
                try:
                    html = await self._load_url_html(record.source_url)
                except SourceUnavailableError:
                    return record

                detail = parse_detail_page(
                    html,
                    base_url=self._base_url,
                    source_url=record.source_url,
                )
                return record.model_copy(
                    update={
                        "source_brand_name": detail.source_brand_name or record.source_brand_name,
                        "product_name_ko": detail.product_name_ko or record.product_name_ko,
                        "regular_price": detail.regular_price
                        if detail.regular_price is not None
                        else record.regular_price,
                        "shade": detail.shade or record.shade,
                        "image_url": detail.image_url or record.image_url,
                        "source_url": detail.source_url or record.source_url,
                        "source_product_id": detail.source_product_id or record.source_product_id,
                    }
                )

        return await asyncio.gather(*(enrich(record) for record in records))

    def _should_enrich(self, records: list[ProductSourceRecord]) -> bool:
        return (
            self._settings.detail_enrichment_enabled
            and bool(records)
            and len(records) <= self._settings.detail_enrichment_max_records
        )

    async def _get_browser(self) -> Any:
        if self._browser and self._browser.is_connected():
            return self._browser

        async with self._browser_lock:
            if self._browser and self._browser.is_connected():
                return self._browser

            try:
                from playwright.async_api import async_playwright
            except ImportError as exc:
                raise SourceUnavailableError(
                    "Playwright is not installed. Run `pip install -r requirements.txt`."
                ) from exc

            if self._playwright is None:
                self._playwright = await async_playwright().start()

            try:
                self._browser = await self._playwright.chromium.launch(
                    headless=self._settings.browser_headless,
                )
            except Exception:
                await self._stop_playwright()
                raise

            return self._browser

    async def close(self) -> None:
        async with self._browser_lock:
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                finally:
                    self._browser = None
            await self._stop_playwright()

    async def _stop_playwright(self) -> None:
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            finally:
                self._playwright = None

    @staticmethod
    async def _wait_for_render(page: Any, timeout_ms: int, wait_selector: str) -> None:
        try:
            await page.wait_for_selector(wait_selector, timeout=min(timeout_ms, 8000))
            await page.wait_for_timeout(250)
        except Exception:
            pass

    @staticmethod
    def _is_blocked_html(html: str) -> bool:
        lower_html = html.casefold()
        return any(marker in lower_html for marker in BLOCKED_MARKERS)
