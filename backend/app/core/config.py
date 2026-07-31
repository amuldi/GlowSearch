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
    oliveyoung_official_order_enabled: bool = True
    oliveyoung_live_search_required: bool = False
    oliveyoung_html_collector_enabled: bool = False
    oliveyoung_public_api_enabled: bool = True
    oliveyoung_public_api_base_url: str = "https://mcp.aka.page"
    oliveyoung_public_api_timeout_seconds: float = 6.0
    oliveyoung_public_api_retry_attempts: int = 2
    oliveyoung_public_api_retry_base_delay_seconds: float = 0.5
    oliveyoung_public_api_retry_max_delay_seconds: float = 4.0
    oliveyoung_public_api_rate_limit_per_second: float = 2.0
    request_timeout_seconds: float = 12.0
    request_user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    )

    cache_ttl_seconds: int = 180
    max_results: int = 480
    source_time_budget_seconds: float = 2.5
    live_collect_deadline_seconds: float = 3.2
    live_first_result_grace_seconds: float = 0.8
    background_collect_deadline_seconds: float = 90.0
    managed_scraping_time_budget_seconds: float = 4.0
    result_source_prefixes: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "oliveyoung",
            "oliveyoung-global",
            "official",
            "musinsa",
            "coupang",
            "hwahae",
            "glowpick",
            "fudejapan",
            "managed",
            "barcode",
            "discovery",
            "external",
        ]
    )
    detail_enrichment_enabled: bool = False
    detail_enrichment_max_records: int = 12
    detail_concurrency: int = 6

    oliveyoung_search_page_size: int = 48
    oliveyoung_search_max_pages: int = 25

    browser_collector_enabled: bool = False
    browser_headless: bool = True
    browser_timeout_seconds: float = 25.0

    apify_token: str | None = None
    apify_actor_id: str = "kitschy_marigold/oliveyoung-search-scraper"
    managed_search_api_enabled: bool = False
    managed_search_api_base_url: str | None = None
    managed_search_api_source: str = "managed:json-api"
    managed_search_api_timeout_seconds: float = 4.0
    musinsa_api_enabled: bool = False
    musinsa_api_base_url: str | None = None
    musinsa_api_source: str = "musinsa"
    musinsa_api_timeout_seconds: float = 3.0
    musinsa_direct_enabled: bool = False
    musinsa_direct_timeout_seconds: float = 6.0
    musinsa_direct_page_size: int = 24
    brand_shopify_enabled: bool = False
    brand_shopify_timeout_seconds: float = 6.0
    oliveyoung_global_api_enabled: bool = False
    oliveyoung_global_api_base_url: str | None = None
    oliveyoung_global_api_source: str = "oliveyoung-global"
    oliveyoung_global_api_timeout_seconds: float = 3.0
    official_brand_api_enabled: bool = False
    official_brand_api_base_url: str | None = None
    official_brand_api_source: str = "official"
    official_brand_api_timeout_seconds: float = 3.0
    global_discovery_api_enabled: bool = False
    global_discovery_api_base_url: str | None = None
    global_discovery_api_source: str = "discovery:json-api"
    global_discovery_api_timeout_seconds: float = 3.0
    barcode_lookup_api_enabled: bool = False
    barcode_lookup_api_base_url: str | None = None
    barcode_lookup_api_source: str = "barcode:lookup"
    barcode_lookup_api_timeout_seconds: float = 3.0

    brand_registry_path: Path = BACKEND_DIR / "data" / "brand_registry.json"
    verified_catalog_path: Path = BACKEND_DIR / "data" / "verified_products.json"
    search_synonyms_path: Path = BACKEND_DIR / "data" / "search_synonyms.json"
    search_intents_path: Path = BACKEND_DIR / "data" / "search_intents.json"

    product_index_enabled: bool = True
    product_index_path: Path = BACKEND_DIR / "data" / "product_index.sqlite3"
    product_index_admin_token: str | None = None
    product_index_min_results: int = 1
    product_index_background_refresh_enabled: bool = True
    product_index_background_refresh_limit: int = 1200
    product_index_warmup_on_startup: bool = False
    product_index_verified_catalog_backfill_on_startup: bool = True
    product_index_warmup_limit: int = 1200
    product_index_warmup_concurrency: int = 4
    product_index_max_seed_queries: int = 500
    product_index_brand_registry_warmup_enabled: bool = True
    product_index_brand_registry_warmup_limit: int = 300
    product_index_detail_enrichment_enabled: bool = True
    product_index_detail_enrichment_max_records: int = 12
    product_index_seed_queries: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "선크림",
            "틴트",
            "쿠션",
            "마스카라",
            "토너패드",
            "클렌징오일",
            "립틴트",
            "립밤",
            "앰플",
            "선세럼",
            "젤",
            "로션",
            "바디로션",
            "크림",
            "토너",
            "세럼",
            "뮤드",
            "메디힐",
            "라운드랩",
        ]
    )
    product_index_category_queries: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "선크림",
            "선스틱",
            "선쿠션",
            "선세럼",
            "선스프레이",
            "톤업선크림",
            "쿠션",
            "파운데이션",
            "베이스",
            "프라이머",
            "컨실러",
            "파우더",
            "팩트",
            "블러셔",
            "하이라이터",
            "쉐딩",
            "섀딩",
            "틴트",
            "립틴트",
            "립밤",
            "립스틱",
            "립글로스",
            "립라이너",
            "아이섀도우",
            "아이브로우",
            "아이라이너",
            "마스카라",
            "픽서",
            "클렌징오일",
            "클렌징워터",
            "클렌징밤",
            "클렌징폼",
            "클렌징젤",
            "필링",
            "필링젤",
            "스크럽",
            "토너",
            "스킨",
            "에센스",
            "앰플",
            "세럼",
            "로션",
            "젤",
            "수딩젤",
            "알로에젤",
            "크림",
            "젤크림",
            "수분크림",
            "재생크림",
            "아이크림",
            "토너패드",
            "패드",
            "마스크팩",
            "팩",
            "헤어오일",
            "헤어팩",
            "샴푸",
            "트리트먼트",
            "바디워시",
            "바디로션",
            "핸드크림",
            "향수",
            "디퓨저",
            "네일",
            "젤네일",
            "마사지젤",
            "헤어젤",
            "브러시",
            "퍼프",
            "히알루론산",
            "시카",
            "병풀",
            "레티놀",
            "비타민C",
            "비타민씨",
            "나이아신아마이드",
            "세라마이드",
            "판테놀",
            "콜라겐",
            "펩타이드",
            "PDRN",
            "어성초",
            "티트리",
            "알로에",
            "글루타치온",
        ]
    )
    product_index_brand_queries: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "뮤드",
            "메디힐",
            "라운드랩",
            "컬러그램",
            "롬앤",
            "클리오",
            "페리페라",
            "에뛰드",
            "웨이크메이크",
            "어뮤즈",
            "토리든",
            "아누아",
            "퓌",
            "정샘물",
            "비긴스 바이 정샘물",
            "닥터지",
            "에스트라",
            "이니스프리",
            "라네즈",
            "마녀공장",
            "넘버즈인",
            "바이오더마",
            "피지오겔",
            "센텔리안24",
            "달바",
            "스킨푸드",
            "닥터자르트",
            "브링그린",
            "구달",
            "릴리바이레드",
            "투쿨포스쿨",
            "더샘",
            "바닐라코",
            "에스쁘아",
            "헤라",
            "아이소이",
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

    @field_validator(
        "result_source_prefixes",
        "product_index_seed_queries",
        "product_index_category_queries",
        "product_index_brand_queries",
        mode="before",
    )
    @classmethod
    def parse_product_index_seed_queries(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
