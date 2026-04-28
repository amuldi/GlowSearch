from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode, urlparse

import httpx

from app.core.config import Settings
from app.data_collector.base import SourceUnavailableError
from app.models.product import ProductSourceRecord
from app.normalizer.text import clean_text
from app.parser.generic_product_html import parse_generic_product_results


@dataclass(frozen=True)
class _OfficialBrand:
    official_en: str
    aliases: tuple[str, ...]
    sources: tuple[str, ...]


class OfficialBrandSiteCollector:
    name = "official"

    def __init__(
        self,
        settings: Settings,
        registry_path: Path,
        client: httpx.AsyncClient | None = None,
    ):
        self._settings = settings
        self._registry_path = registry_path
        self._client = client
        self._brands = self._load_brands(registry_path)

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        keyword = keyword.strip()
        if not keyword:
            return []

        matches = self._match_brands(keyword)
        if not matches:
            return []

        if self._client is not None:
            return await self._search_with_client(self._client, keyword, matches, limit)

        async with httpx.AsyncClient(
            timeout=self._settings.official_brand_site_timeout_seconds,
            follow_redirects=True,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "User-Agent": self._settings.request_user_agent,
            },
        ) as client:
            return await self._search_with_client(client, keyword, matches, limit)

    async def _search_with_client(
        self,
        client: httpx.AsyncClient,
        keyword: str,
        matches: list[_OfficialBrand],
        limit: int,
    ) -> list[ProductSourceRecord]:
        records: list[ProductSourceRecord] = []
        for brand in matches[: self._settings.official_brand_site_max_brands]:
            query = self._product_query(keyword, brand)
            for source in brand.sources[: self._settings.official_brand_site_max_sources_per_brand]:
                base_url = self._origin(source)
                candidate_urls = self._candidate_urls(source, query)[
                    : self._settings.official_brand_site_max_search_urls
                ]
                for url in candidate_urls:
                    html = await self._fetch_html(client, url)
                    if not html:
                        continue
                    parsed = parse_generic_product_results(
                        html,
                        base_url=base_url,
                        source_brand_name=brand.official_en,
                        limit=limit,
                    )
                    if parsed:
                        records.extend(parsed)
                        break
                if len(records) >= limit:
                    return self._dedupe(records)[:limit]
        return self._dedupe(records)[:limit]

    async def _fetch_html(self, client: httpx.AsyncClient, url: str) -> str | None:
        try:
            response = await client.get(url)
        except httpx.HTTPError:
            return None
        if response.status_code in {403, 404, 429}:
            return None
        if response.status_code >= 500:
            raise SourceUnavailableError(f"Official brand site returned HTTP {response.status_code}")
        content_type = response.headers.get("content-type", "")
        if content_type and "html" not in content_type and "text" not in content_type:
            return None
        return response.text

    def _match_brands(self, keyword: str) -> list[_OfficialBrand]:
        keyword_key = self._key(keyword)
        if not keyword_key:
            return []
        matches = [
            brand
            for brand in self._brands
            if brand.sources
            and any(alias_key and alias_key in keyword_key for alias_key in map(self._key, brand.aliases))
        ]
        return sorted(matches, key=lambda brand: max(len(self._key(alias)) for alias in brand.aliases), reverse=True)

    def _product_query(self, keyword: str, brand: _OfficialBrand) -> str:
        query = keyword
        for alias in sorted(brand.aliases, key=len, reverse=True):
            query = re.sub(re.escape(alias), " ", query, flags=re.IGNORECASE)
        return clean_text(query) or keyword

    @staticmethod
    def _candidate_urls(source: str, query: str) -> list[str]:
        source = source.rstrip("/")
        origin = OfficialBrandSiteCollector._origin(source)
        encoded = urlencode({"keyword": query})
        q_encoded = urlencode({"q": query})
        return [
            f"{origin}/product/search.html?{encoded}",
            f"{origin}/search?{q_encoded}",
            f"{origin}/search?{encoded}",
            f"{origin}/products?{encoded}",
            f"{source}?{encoded}",
        ]

    @staticmethod
    def _origin(url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return url.rstrip("/")

    @staticmethod
    def _load_brands(registry_path: Path) -> list[_OfficialBrand]:
        if not registry_path.exists():
            return []
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
        brands: list[_OfficialBrand] = []
        for entry in payload.get("entries", []):
            official = clean_text(entry.get("official_en"))
            if not official:
                continue
            aliases = tuple(
                alias
                for alias in [official, *entry.get("aliases", [])]
                if clean_text(alias)
            )
            sources = tuple(
                source
                for source in entry.get("sources", [])
                if isinstance(source, str) and source.startswith(("http://", "https://"))
            )
            brands.append(_OfficialBrand(official_en=official, aliases=aliases, sources=sources))
        return brands

    @staticmethod
    def _dedupe(records: list[ProductSourceRecord]) -> list[ProductSourceRecord]:
        deduped: list[ProductSourceRecord] = []
        seen: set[str] = set()
        for record in records:
            key = record.source_url or f"{record.source_brand_name}:{record.product_name_ko}"
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(record)
        return deduped

    @staticmethod
    def _key(value: str | None) -> str:
        text = clean_text(value)
        if text is None:
            return ""
        return re.sub(r"[\s\-_./|+&'():\[\],]+", "", text).casefold()
