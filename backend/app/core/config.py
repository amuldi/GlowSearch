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
    oliveyoung_public_api_timeout_seconds: float = 6.0
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

    oliveyoung_search_page_size: int = 48
    oliveyoung_search_max_pages: int = 10

    browser_collector_enabled: bool = True
    browser_headless: bool = True
    browser_timeout_seconds: float = 25.0

    apify_token: str | None = None
    apify_actor_id: str = "kitschy_marigold/oliveyoung-search-scraper"

    brand_registry_path: Path = BACKEND_DIR / "data" / "brand_registry.json"
    verified_catalog_path: Path = BACKEND_DIR / "data" / "verified_products.json"

    product_index_enabled: bool = True
    product_index_path: Path = BACKEND_DIR / "data" / "product_index.sqlite3"
    product_index_min_results: int = 8
    product_index_background_refresh_enabled: bool = True
    product_index_warmup_on_startup: bool = True
    product_index_warmup_limit: int = 48
    product_index_warmup_concurrency: int = 2
    product_index_seed_queries: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "선크림",
            "틴트",
            "쿠션",
            "마스카라",
            "토너패드",
            "클렌징오일",
            "뮤드",
            "메디힐",
            "라운드랩",
        ]
    )

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

    @field_validator("product_index_seed_queries", mode="before")
    @classmethod
    def parse_product_index_seed_queries(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
