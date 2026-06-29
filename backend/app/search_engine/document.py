from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.product import PriceValue


class SearchDocument(BaseModel):
    id: str
    name: str
    name_en: str | None = None
    brand: str | None = None
    brand_en: str | None = None
    category: str | None = None
    shade: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    ingredients: list[str] = Field(default_factory=list)
    review_keywords: list[str] = Field(default_factory=list)
    rating: float | None = None
    review_count: int | None = None
    sales_count: int | None = None
    image_url: str | None = None
    price: PriceValue | None = None
    source: str
    source_url: str | None = None
    source_product_id: str | None = None
    quality_score: int = 0
    score: float | None = None
