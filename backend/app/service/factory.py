from functools import lru_cache

from app.cache.ttl import AsyncTTLCache
from app.core.config import Settings, get_settings
from app.data_collector.apify import ApifyOliveYoungCollector
from app.data_collector.base import ProductCollector
from app.data_collector.brand_shopify import BrandShopifyCollector
from app.data_collector.browser_oliveyoung import BrowserOliveYoungCollector
from app.data_collector.json_api import JsonApiProductCollector
from app.data_collector.local_catalog import LocalVerifiedCatalogCollector
from app.data_collector.musinsa import MusinsaBeautyCollector
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
from app.search_engine.analytics import InMemorySearchAnalytics
from app.search_engine.intent import SearchIntentExpander
from app.search_engine.related import RelatedKeywordService
from app.search_engine.sqlite_provider import SQLiteSearchProvider
from app.search_engine.synonyms import SearchSynonymExpander
from app.service.search_service import SearchService
from app.service.source_policy import SourcePolicy


@lru_cache
def get_search_service() -> SearchService:
    settings = get_settings()
    collectors = _build_collectors(settings)

    brand_resolver = BrandResolver(settings.brand_registry_path)
    normalizer = ProductNormalizer(brand_resolver, settings.oliveyoung_base_url)
    cache = AsyncTTLCache(ttl_seconds=settings.cache_ttl_seconds)
    index_store = (
        SQLiteProductIndexStore(
            settings.product_index_path,
            turso_sync_url=settings.turso_database_url,
            turso_auth_token=settings.turso_auth_token,
            turso_sync_interval_seconds=settings.turso_sync_interval_seconds,
        )
        if settings.product_index_enabled
        else None
    )
    if isinstance(index_store, SQLiteProductIndexStore):
        index_store.seed_brand_aliases(normalizer.index_aliases())
    detail_enricher = (
        OliveYoungDetailEnrichmentAgent(settings)
        if settings.product_index_detail_enrichment_enabled
        else None
    )
    ingestion_agent = (
        ProductIngestionAgent(index_store, normalizer=normalizer, detail_enricher=detail_enricher)
        if index_store
        else None
    )
    brand_seed_queries = list(settings.product_index_brand_queries)
    if settings.product_index_brand_registry_warmup_enabled:
        brand_seed_queries.extend(
            brand_resolver.warmup_aliases(settings.product_index_brand_registry_warmup_limit)
        )
    discovery_agent = SourceDiscoveryAgent(
        settings.product_index_seed_queries,
        category_queries=settings.product_index_category_queries,
        brand_queries=brand_seed_queries,
        max_seed_queries=settings.product_index_max_seed_queries,
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
        index_background_refresh_limit=settings.product_index_background_refresh_limit,
        index_warmup_limit=settings.product_index_warmup_limit,
        index_warmup_concurrency=settings.product_index_warmup_concurrency,
        prefer_live_official_results=settings.oliveyoung_live_search_required,
        preserve_official_order=settings.oliveyoung_official_order_enabled,
        source_time_budget_seconds=settings.source_time_budget_seconds,
        live_collect_deadline_seconds=settings.live_collect_deadline_seconds,
        live_first_result_grace_seconds=settings.live_first_result_grace_seconds,
        background_collect_deadline_seconds=settings.background_collect_deadline_seconds,
        source_time_budgets={
            "oliveyoung:public-api": settings.oliveyoung_public_api_timeout_seconds,
            "oliveyoung:apify": settings.managed_scraping_time_budget_seconds,
            "oliveyoung:browser": settings.browser_timeout_seconds,
            settings.managed_search_api_source: settings.managed_search_api_timeout_seconds,
            settings.musinsa_api_source: settings.musinsa_api_timeout_seconds,
            "musinsa": settings.musinsa_direct_timeout_seconds,
            "official": settings.brand_shopify_timeout_seconds,
            settings.oliveyoung_global_api_source: settings.oliveyoung_global_api_timeout_seconds,
            settings.official_brand_api_source: settings.official_brand_api_timeout_seconds,
            settings.global_discovery_api_source: settings.global_discovery_api_timeout_seconds,
            settings.barcode_lookup_api_source: settings.barcode_lookup_api_timeout_seconds,
        },
        source_policy=SourcePolicy(allowed_prefixes=settings.result_source_prefixes),
    )


@lru_cache
def get_search_provider() -> SQLiteSearchProvider:
    settings = get_settings()
    brand_resolver = BrandResolver(settings.brand_registry_path)
    normalizer = ProductNormalizer(brand_resolver, settings.oliveyoung_base_url)
    # Deliberately local-only: get_search_service() already owns the Turso
    # embedded-replica sync relationship for this same file. Turso's docs warn
    # against opening the local db while a sync is in flight, so a second
    # independent sync_url connection here risks corruption; this store just
    # reads/writes the same on-disk file that the other connection commits to.
    index_store = SQLiteProductIndexStore(settings.product_index_path)
    index_store.seed_brand_aliases(normalizer.index_aliases())
    return SQLiteSearchProvider(
        index_store,
        normalizer,
        source_policy=SourcePolicy(allowed_prefixes=settings.result_source_prefixes),
    )


@lru_cache
def get_related_keyword_service() -> RelatedKeywordService:
    settings = get_settings()
    return RelatedKeywordService(
        SearchSynonymExpander(settings.search_synonyms_path),
        SearchIntentExpander(settings.search_intents_path),
    )


@lru_cache
def get_search_analytics() -> InMemorySearchAnalytics:
    return InMemorySearchAnalytics()


def _build_collectors(settings: Settings) -> list[ProductCollector]:
    collectors: list[ProductCollector] = []
    if settings.oliveyoung_html_collector_enabled:
        collectors.append(OliveYoungCollector(settings))
    if settings.oliveyoung_public_api_enabled:
        collectors.append(OliveYoungPublicApiCollector(settings))
    collectors.append(LocalVerifiedCatalogCollector(settings.verified_catalog_path))
    if settings.apify_token:
        collectors.append(ApifyOliveYoungCollector(settings))
    if settings.managed_search_api_enabled and settings.managed_search_api_base_url:
        collectors.append(
            JsonApiProductCollector(
                name=settings.managed_search_api_source,
                base_url=settings.managed_search_api_base_url,
                timeout_seconds=settings.managed_search_api_timeout_seconds,
            )
        )
    if settings.musinsa_api_enabled and settings.musinsa_api_base_url:
        collectors.append(
            JsonApiProductCollector(
                name=settings.musinsa_api_source,
                base_url=settings.musinsa_api_base_url,
                timeout_seconds=settings.musinsa_api_timeout_seconds,
            )
        )
    if settings.musinsa_direct_enabled:
        collectors.append(
            MusinsaBeautyCollector(
                timeout_seconds=settings.musinsa_direct_timeout_seconds,
                page_size=settings.musinsa_direct_page_size,
            )
        )
    if settings.brand_shopify_enabled:
        collectors.append(
            BrandShopifyCollector(
                settings.brand_registry_path,
                timeout_seconds=settings.brand_shopify_timeout_seconds,
            )
        )
    if settings.oliveyoung_global_api_enabled and settings.oliveyoung_global_api_base_url:
        collectors.append(
            JsonApiProductCollector(
                name=settings.oliveyoung_global_api_source,
                base_url=settings.oliveyoung_global_api_base_url,
                timeout_seconds=settings.oliveyoung_global_api_timeout_seconds,
            )
        )
    if settings.official_brand_api_enabled and settings.official_brand_api_base_url:
        collectors.append(
            JsonApiProductCollector(
                name=settings.official_brand_api_source,
                base_url=settings.official_brand_api_base_url,
                timeout_seconds=settings.official_brand_api_timeout_seconds,
            )
        )
    if settings.global_discovery_api_enabled and settings.global_discovery_api_base_url:
        collectors.append(
            JsonApiProductCollector(
                name=settings.global_discovery_api_source,
                base_url=settings.global_discovery_api_base_url,
                timeout_seconds=settings.global_discovery_api_timeout_seconds,
            )
        )
    if settings.barcode_lookup_api_enabled and settings.barcode_lookup_api_base_url:
        collectors.append(
            JsonApiProductCollector(
                name=settings.barcode_lookup_api_source,
                base_url=settings.barcode_lookup_api_base_url,
                timeout_seconds=settings.barcode_lookup_api_timeout_seconds,
                barcode_only=True,
            )
        )
    if settings.browser_collector_enabled:
        collectors.append(BrowserOliveYoungCollector(settings))
    return collectors
