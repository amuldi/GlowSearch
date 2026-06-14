from pydantic import BaseModel, Field


class ProductSourceRecord(BaseModel):
    category: str | None = None
    source_brand_name: str | None = None
    source_brand_name_en: str | None = None
    product_name_ko: str | None = None
    product_name_en: str | None = None
    regular_price: int | None = None
    original_price: int | None = None
    sale_price: int | None = None
    discount_rate: int | None = None
    rating: float | None = None
    review_count: int | None = None
    currency: str | None = "KRW"
    shade: str | None = None
    image_url: str | None = None
    description: str | None = None
    options: list[str] | None = None
    sold_out: bool | None = None
    source: str
    source_url: str | None = None
    source_product_id: str | None = None
    updated_at: str | None = None


class ProductSearchResult(BaseModel):
    brand_ko: str | None = Field(default=None)
    brand_en: str | None = Field(default=None)
    product_name_ko: str | None = Field(default=None)
    product_name_en: str | None = Field(default=None)
    category: str | None = Field(default=None)
    price: int | None = Field(default=None)
    original_price: int | None = Field(default=None)
    sale_price: int | None = Field(default=None)
    discount_rate: int | None = Field(default=None)
    rating: float | None = Field(default=None)
    review_count: int | None = Field(default=None)
    currency: str | None = Field(default="KRW")
    shade: str | None = Field(default=None)
    image_url: str | None = Field(default=None)
    description: str | None = Field(default=None)
    options: list[str] | None = Field(default=None)
    sold_out: bool | None = Field(default=None)
    source_url: str | None = Field(default=None)
    source_product_id: str | None = Field(default=None)
    source: str
    source_label: str | None = Field(default=None)
    source_priority: int | None = Field(default=None)
    quality_score: int = Field(default=0)
    enrichment_missing_fields: list[str] = Field(default_factory=list)
    updated_at: str | None = Field(default=None)


class SearchResponse(BaseModel):
    query: str
    count: int
    results: list[ProductSearchResult]
    source_errors: list[str] = Field(default_factory=list)


class SuggestionResponse(BaseModel):
    query: str
    suggestions: list[str] = Field(default_factory=list)
