from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "GlowSearch"
    api_prefix: str = ""
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    cors_origin_regex: str | None = r"https://.*\.vercel\.app"

    oliveyoung_base_url: str = "https://www.oliveyoung.co.kr"
    oliveyoung_public_api_enabled: bool = True
    oliveyoung_public_api_base_url: str = "https://mcp.aka.page"
    oliveyoung_public_api_timeout_seconds: float = 4.0
    oliveyoung_only_results: bool = True
    request_timeout_seconds: float = 12.0
    request_user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    )

    cache_ttl_seconds: int = 180
    max_results: int = 480
    source_time_budget_seconds: float = 2.5
    managed_scraping_time_budget_seconds: float = 4.0
    detail_enrichment_enabled: bool = False
    detail_enrichment_max_records: int = 12
    detail_concurrency: int = 6

    product_index_enabled: bool = True
    product_index_path: Path = BACKEND_DIR / "data" / "product_index.json"
    product_index_seed_verified_catalog: bool = True
    product_index_fresh_ttl_seconds: int = 3600
    product_index_stale_ttl_seconds: int = 604800
    stale_revalidate_enabled: bool = True

    oliveyoung_search_page_size: int = 48
    oliveyoung_search_max_pages: int = 10

    browser_collector_enabled: bool = True
    browser_headless: bool = True
    browser_timeout_seconds: float = 25.0

    apify_token: str | None = None
    apify_actor_id: str = "kitschy_marigold/oliveyoung-search-scraper"

    brightdata_serp_enabled: bool = False
    brightdata_api_key: str | None = None
    brightdata_serp_zone: str = "serp_api1"
    brightdata_country: str = "us"

    serpapi_enabled: bool = False
    serpapi_api_key: str | None = None
    serpapi_location: str | None = None
    serpapi_gl: str | None = "us"
    serpapi_hl: str | None = "en"

    bing_web_search_enabled: bool = False
    bing_web_search_api_key: str | None = None
    bing_web_search_market: str = "en-US"

    google_programmable_search_enabled: bool = False
    google_programmable_search_api_key: str | None = None
    google_programmable_search_engine_id: str | None = None

    open_beauty_facts_enabled: bool = True
    barcode_lookup_enabled: bool = False
    barcode_lookup_api_key: str | None = None
    upcitemdb_enabled: bool = False
    upcitemdb_api_key: str | None = None

    musinsa_brand_lookup_enabled: bool = True
    musinsa_product_collector_enabled: bool = True
    musinsa_api_base_url: str = "https://api.musinsa.com/api2/dp"
    musinsa_timeout_seconds: float = 2.5
    musinsa_beauty_category_code: str = "104"

    official_brand_site_collector_enabled: bool = True
    official_brand_site_timeout_seconds: float = 1.5
    official_brand_site_max_brands: int = 1
    official_brand_site_max_sources_per_brand: int = 1
    official_brand_site_max_search_urls: int = 2

    brand_registry_path: Path = BACKEND_DIR / "data" / "brand_registry.json"
    verified_catalog_path: Path = BACKEND_DIR / "data" / "verified_products.json"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="GLOWSEARCH_",
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
