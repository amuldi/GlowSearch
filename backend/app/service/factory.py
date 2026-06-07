from functools import lru_cache

from app.cache.ttl import AsyncTTLCache
from app.core.config import Settings, get_settings
from app.data_collector.apify import ApifyOliveYoungCollector
from app.data_collector.base import ProductCollector
from app.data_collector.browser_oliveyoung import BrowserOliveYoungCollector
from app.data_collector.local_catalog import LocalVerifiedCatalogCollector
from app.data_collector.oliveyoung import OliveYoungCollector
from app.data_collector.oliveyoung_api import OliveYoungPublicApiCollector
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
    return SearchService(
        collectors=collectors,
        normalizer=normalizer,
        cache=cache,
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
