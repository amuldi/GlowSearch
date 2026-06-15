from typing import Literal

from pydantic import BaseModel, Field

from app.models.product import ProductSearchResult


EditorMatchStatus = Literal["확인됨", "후보 있음", "수동 확인 필요"]


class EditorBatchRequest(BaseModel):
    text: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=5)


class EditorParsedLine(BaseModel):
    raw_text: str
    brand_query: str | None = None
    product_query: str | None = None
    shade_query: str | None = None
    shade_code: str | None = None
    shade_name: str | None = None
    normalized_query: str


class EditorProductCandidate(BaseModel):
    product: ProductSearchResult
    match_score: int


class EditorBatchItem(BaseModel):
    raw_text: str
    parsed: EditorParsedLine
    status: EditorMatchStatus
    candidates: list[EditorProductCandidate] = Field(default_factory=list)


class EditorBatchResponse(BaseModel):
    count: int
    items: list[EditorBatchItem] = Field(default_factory=list)
