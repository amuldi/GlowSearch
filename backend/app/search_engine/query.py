from __future__ import annotations

from pydantic import BaseModel, Field

from app.search_engine.document import SearchDocument


class SearchQuery(BaseModel):
    text: str
    limit: int = Field(default=24, ge=1, le=480)
    brand: str | None = None
    min_price: int | None = Field(default=None, ge=0)
    max_price: int | None = Field(default=None, ge=0)
    has_shade: bool | None = None
    expanded_terms: list[str] = Field(default_factory=list)


class SearchResultPage(BaseModel):
    query: str
    expanded_terms: list[str] = Field(default_factory=list)
    count: int
    results: list[SearchDocument] = Field(default_factory=list)
    provider: str
    source_errors: list[str] = Field(default_factory=list)
