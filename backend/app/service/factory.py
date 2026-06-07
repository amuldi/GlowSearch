from functools import lru_cache

from app.cache.ttl import AsyncTTLCache
from app.core.config import get_settings
from app.data_collector.apify import ApifyOliveYoungCollector
from app.data_collector.base import ProductCollector
from app.data_collector.browser_oliveyoung import BrowserOliveYoungCollector
from app.data_collector.local_catalog import LocalVerifiedCatalogCollector
from app.data_collector.musinsa import MusinsaProductCollector
from app.data_collector.oliveyoung import OliveYoungCollector
from app.data_collector.oliveyoung_api import OliveYoungPublicApiCollector
from app.data_collector.official_brand import OfficialBrandSiteCollector
from app.index.store import JsonProductIndexStore
from app.normalizer.brand import BrandResolver
from app.normalizer.musinsa import MusinsaBrandResolver
from app.normalizer.product import ProductNormalizer
from app.service.search_service import SearchService
from app.source_adapters import (
    BarcodeLookupCollector,
    BingWebSearchCollector,
    BrightDataSerpCollector,
    GoogleProgrammableSearchCollector,
    OpenBeautyFactsCollector,
    SerpApiShoppingCollector,
    UPCItemDBCollector,
)


@lru_cache
def get_search_service() -> SearchService:
    settings = get_settings()
    source_priorities = {
        "oliveyoung:verified-cache": 0,
        "openbeautyfacts": 5,
        "oliveyoung": 10,
        "musinsa": 20,
        "official": 25,
        "serpapi:google-shopping": 40,
        "barcodelookup": 45,
        "upcitemdb": 50,
        "brightdata:serp": 65,
        "bing:web-search": 70,
        "google:programmable-search": 75,
        "oliveyoung:apify": 80,
        "oliveyoung:browser": 100,
    }
    collectors: list[ProductCollector] = []
    collectors.append(OliveYoungCollector(settings))
    if settings.oliveyoung_public_api_enabled:
        collectors.append(OliveYoungPublicApiCollector(settings))
    if settings.apify_token:
        collectors.append(ApifyOliveYoungCollector(settings))
    collectors.append(LocalVerifiedCatalogCollector(settings.verified_catalog_path))
    if not settings.oliveyoung_only_results and settings.open_beauty_facts_enabled:
        collectors.append(
            OpenBeautyFactsCollector(timeout_seconds=settings.source_time_budget_seconds)
        )
    if not settings.oliveyoung_only_results and settings.serpapi_enabled and settings.serpapi_api_key:
        collectors.append(
            SerpApiShoppingCollector(
                api_key=settings.serpapi_api_key,
                timeout_seconds=settings.source_time_budget_seconds,
                location=settings.serpapi_location,
                gl=settings.serpapi_gl,
                hl=settings.serpapi_hl,
            )
        )
    if (
        not settings.oliveyoung_only_results
        and settings.barcode_lookup_enabled
        and settings.barcode_lookup_api_key
    ):
        collectors.append(
            BarcodeLookupCollector(
                api_key=settings.barcode_lookup_api_key,
                timeout_seconds=settings.source_time_budget_seconds,
            )
        )
    if not settings.oliveyoung_only_results and settings.upcitemdb_enabled:
        collectors.append(
            UPCItemDBCollector(
                api_key=settings.upcitemdb_api_key,
                timeout_seconds=settings.source_time_budget_seconds,
            )
        )
    if (
        not settings.oliveyoung_only_results
        and settings.brightdata_serp_enabled
        and settings.brightdata_api_key
    ):
        collectors.append(
            BrightDataSerpCollector(
                api_key=settings.brightdata_api_key,
                zone=settings.brightdata_serp_zone,
                timeout_seconds=settings.managed_scraping_time_budget_seconds,
                country=settings.brightdata_country,
            )
        )
    if (
        not settings.oliveyoung_only_results
        and settings.bing_web_search_enabled
        and settings.bing_web_search_api_key
    ):
        collectors.append(
            BingWebSearchCollector(
                api_key=settings.bing_web_search_api_key,
                timeout_seconds=settings.source_time_budget_seconds,
                market=settings.bing_web_search_market,
            )
        )
    if (
        settings.google_programmable_search_enabled
        and not settings.oliveyoung_only_results
        and settings.google_programmable_search_api_key
        and settings.google_programmable_search_engine_id
    ):
        collectors.append(
            GoogleProgrammableSearchCollector(
                api_key=settings.google_programmable_search_api_key,
                search_engine_id=settings.google_programmable_search_engine_id,
                timeout_seconds=settings.source_time_budget_seconds,
            )
        )
    if not settings.oliveyoung_only_results and settings.musinsa_product_collector_enabled:
        collectors.append(MusinsaProductCollector(settings))
    if not settings.oliveyoung_only_results and settings.official_brand_site_collector_enabled:
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
    index_store = (
        JsonProductIndexStore(
            settings.product_index_path,
            seed_catalog_path=(
                settings.verified_catalog_path
                if settings.product_index_seed_verified_catalog
                else None
            ),
            fresh_ttl_seconds=settings.product_index_fresh_ttl_seconds,
            stale_ttl_seconds=settings.product_index_stale_ttl_seconds,
            source_priorities=source_priorities,
        )
        if settings.product_index_enabled and not settings.oliveyoung_only_results
        else None
    )
    source_time_budgets = {
        "oliveyoung:apify": settings.managed_scraping_time_budget_seconds,
        "oliveyoung:public-api": settings.oliveyoung_public_api_timeout_seconds,
        "brightdata:serp": settings.managed_scraping_time_budget_seconds,
        "oliveyoung:browser": settings.browser_timeout_seconds,
    }
    cache_ttl_seconds = 0 if settings.oliveyoung_only_results else settings.cache_ttl_seconds
    cache = AsyncTTLCache(ttl_seconds=cache_ttl_seconds)
    return SearchService(
        collectors=collectors,
        normalizer=normalizer,
        cache=cache,
        index_store=index_store,
        source_time_budget_seconds=settings.source_time_budget_seconds,
        source_time_budgets=source_time_budgets,
        source_priorities=source_priorities,
        allowed_result_source_prefixes=("oliveyoung",) if settings.oliveyoung_only_results else None,
        stale_revalidate_enabled=settings.stale_revalidate_enabled,
    )
