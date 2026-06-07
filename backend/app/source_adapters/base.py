from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.models.product import ProductSourceRecord


@dataclass(frozen=True)
class SourceAdapterCapabilities:
    product_search: bool = True
    discovery: bool = False
    barcode_lookup: bool = False
    managed_scraping: bool = False
    sitemap_ingestion: bool = False


@dataclass(frozen=True)
class SourceAdapterMetadata:
    name: str
    priority: int
    timeout_seconds: float
    critical_path: bool
    capabilities: SourceAdapterCapabilities


@dataclass(frozen=True)
class DiscoveredSource:
    url: str
    title: str | None
    source: str
    snippet: str | None = None


class ProductSourceAdapter(Protocol):
    name: str
    metadata: SourceAdapterMetadata

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        ...


class DiscoveryAdapter(Protocol):
    name: str
    metadata: SourceAdapterMetadata

    async def discover(self, keyword: str, limit: int) -> list[DiscoveredSource]:
        ...
