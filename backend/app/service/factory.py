from functools import lru_cache

from app.cache.ttl import AsyncTTLCache
from app.core.config import Settings, get_settings
from app.data_collector.apify import ApifyOliveYoungCollector
from app.data_collector.base import ProductCollector
from app.data_collector.browser_oliveyoung import BrowserOliveYoungCollector
from app.data_collector.local_catalog import LocalVerifiedCatalogCollector
from app.data_collector.oliveyoung import OliveYoungCollector
from app.data_collector.oliveyoung_api import OliveYoungPublicApiCollector
from app.indexing.agents import (
    OliveYoungDetailEnrichmentAgent,
    ProductIngestionAgent,
    SourceDiscoveryAgent,
)
from app.indexing.store import SQLiteProductIndexStore
from app.normalizer.brand import BrandResolver
from app.normalizer.product import ProductNormalizer
from app.service.search_service import SearchService


@lru_cache
def get_search_service() -> SearchService:
    settings = get_settings()
    collectors = _build_collectors(settings)

    brand_resolver = BrandResolver(settings.brand_registry_path)
    normalizer = ProductNormalizer(brand_resolver, settings.oliveyoung_base_url)
    cache = AsyncTTLCache(ttl_seconds=settings.cache_ttl_seconds)
    index_store = (
        SQLiteProductIndexStore(settings.product_index_path)
        if settings.product_index_enabled
        else None
    )
    detail_enricher = (
        OliveYoungDetailEnrichmentAgent(settings)
        if settings.product_index_detail_enrichment_enabled
        else None
    )
    ingestion_agent = (
        ProductIngestionAgent(index_store, detail_enricher=detail_enricher)
        if index_store
        else None
    )
    discovery_agent = SourceDiscoveryAgent(
        settings.product_index_seed_queries,
        category_queries=settings.product_index_category_queries,
        brand_queries=settings.product_index_brand_queries,
    )
    return SearchService(
        collectors=collectors,
        normalizer=normalizer,
        cache=cache,
        product_index=index_store,
        ingestion_agent=ingestion_agent,
        source_discovery_agent=discovery_agent,
        index_min_results=settings.product_index_min_results,
        index_background_refresh_enabled=settings.product_index_background_refresh_enabled,
        index_warmup_limit=settings.product_index_warmup_limit,
        index_warmup_concurrency=settings.product_index_warmup_concurrency,
        source_time_budget_seconds=settings.source_time_budget_seconds,
        source_time_budgets={
            "oliveyoung:public-api": settings.oliveyoung_public_api_timeout_seconds,
            "oliveyoung:apify": settings.managed_scraping_time_budget_seconds,
            "oliveyoung:browser": settings.browser_timeout_seconds,
        },
        allowed_result_source_prefixes=("oliveyoung",),
    )


def _build_collectors(settings: Settings) -> list[ProductCollector]:
    collectors: list[ProductCollector] = [
        OliveYoungCollector(settings),
    ]
    if settings.oliveyoung_public_api_enabled:
        collectors.append(OliveYoungPublicApiCollector(settings))
    collectors.append(LocalVerifiedCatalogCollector(settings.verified_catalog_path))
    if settings.apify_token:
        collectors.append(ApifyOliveYoungCollector(settings))
    if settings.browser_collector_enabled:
        collectors.append(BrowserOliveYoungCollector(settings))
    return collectors
