from pydantic import BaseModel, Field


class ProductSourceRecord(BaseModel):
    source_brand_name: str | None = None
    product_name_ko: str | None = None
    regular_price: int | None = None
    shade: str | None = None
    image_url: str | None = None
    source: str
    source_url: str | None = None
    source_product_id: str | None = None


class ProductSearchResult(BaseModel):
    brand_en: str | None = Field(default=None)
    product_name_ko: str | None = Field(default=None)
    price: int | None = Field(default=None)
    shade: str | None = Field(default=None)
    image_url: str | None = Field(default=None)
    source_url: str | None = Field(default=None)
    source: str


class SearchResponse(BaseModel):
    query: str
    count: int
    results: list[ProductSearchResult]
    source_errors: list[str] = Field(default_factory=list)
