from functools import lru_cache

from app.cache.ttl import AsyncTTLCache
from app.core.config import get_settings
from app.data_collector.apify import ApifyOliveYoungCollector
from app.data_collector.base import ProductCollector
from app.data_collector.browser_oliveyoung import BrowserOliveYoungCollector
from app.data_collector.local_catalog import LocalVerifiedCatalogCollector
from app.data_collector.musinsa import MusinsaProductCollector
from app.data_collector.oliveyoung import OliveYoungCollector
from app.data_collector.official_brand import OfficialBrandSiteCollector
from app.normalizer.brand import BrandResolver
from app.normalizer.musinsa import MusinsaBrandResolver
from app.normalizer.product import ProductNormalizer
from app.service.search_service import SearchService


@lru_cache
def get_search_service() -> SearchService:
    settings = get_settings()
    collectors: list[ProductCollector] = []
    collectors.append(OliveYoungCollector(settings))
    if settings.apify_token:
        collectors.append(ApifyOliveYoungCollector(settings))
    collectors.append(LocalVerifiedCatalogCollector(settings.verified_catalog_path))
    if settings.musinsa_product_collector_enabled:
        collectors.append(MusinsaProductCollector(settings))
    if settings.official_brand_site_collector_enabled:
        collectors.append(OfficialBrandSiteCollector(settings, settings.brand_registry_path))
    if settings.browser_collector_enabled:
        collectors.append(BrowserOliveYoungCollector(settings))

    external_brand_resolvers = []
    if settings.musinsa_brand_lookup_enabled:
        external_brand_resolvers.append(
            MusinsaBrandResolver(
                api_base_url=settings.musinsa_api_base_url,
                timeout_seconds=settings.musinsa_timeout_seconds,
                user_agent=settings.request_user_agent,
            )
        )

    brand_resolver = BrandResolver(
        settings.brand_registry_path,
        external_resolvers=external_brand_resolvers,
    )
    normalizer = ProductNormalizer(brand_resolver, settings.oliveyoung_base_url)
    cache = AsyncTTLCache(ttl_seconds=settings.cache_ttl_seconds)
    return SearchService(collectors=collectors, normalizer=normalizer, cache=cache)
