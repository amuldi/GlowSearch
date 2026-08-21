"""Request/response models for the admin-only match review API (milestone 4).

Mirrors app/models/editor.py's pattern of a feature-specific model file
separate from app/models/product.py.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.models.product import MatchReviewState, PriceValue


class MatchOfferSummary(BaseModel):
    source: str
    source_label: str | None = None
    source_url: str
    source_product_id: str | None = None
    price: PriceValue | None = None
    image_url: str | None = None
    sold_out: bool | None = None
    updated_at: str | None = None


class MatchTargetSummary(BaseModel):
    """No dedicated canonical-product table exists yet, so this is a snapshot
    of one representative `products` row sharing the same canonical_product_id
    (highest quality_score, most recently seen) — a pragmatic stand-in for
    "the product this offer is being matched against" until a real product
    entity exists."""

    canonical_product_id: str
    brand_ko: str | None = None
    brand_en: str | None = None
    product_name_ko: str | None = None
    product_name_display_ko: str | None = None
    image_url: str | None = None


class MatchEvidenceItem(BaseModel):
    type: str
    value: str | None = None
    weight: float | None = None


class PendingMatchSummary(BaseModel):
    match_id: str
    id: int
    canonical_product_id: str
    confidence: float
    match_method: str
    created_at: str
    offer: MatchOfferSummary
    target: MatchTargetSummary | None = None


class PendingMatchListResponse(BaseModel):
    items: list[PendingMatchSummary] = Field(default_factory=list)
    next_after_id: int | None = None


class MatchReviewEvent(BaseModel):
    previous_review_state: str
    new_review_state: str
    reviewer: str
    note: str | None = None
    created_at: str


class MatchDetail(BaseModel):
    match_id: str
    canonical_product_id: str
    review_state: MatchReviewState
    confidence: float
    match_method: str
    evidence: list[MatchEvidenceItem] = Field(default_factory=list)
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    created_at: str
    updated_at: str
    offer: MatchOfferSummary
    target: MatchTargetSummary | None = None
    history: list[MatchReviewEvent] = Field(default_factory=list)


class MatchReviewRequest(BaseModel):
    # 'invalid' is deliberately not settable through this API — it's reserved
    # for a future automated integrity check, not a human review decision.
    decision: Literal["verified", "rejected"]
    reviewer: str = Field(min_length=1)
    note: str | None = None
    # Optimistic concurrency: pass the updated_at you last observed. If it no
    # longer matches, the request is rejected with 409 rather than silently
    # overwriting a change you haven't seen. Omit to skip the check.
    expected_updated_at: str | None = None


class MatchReviewResponse(BaseModel):
    match_id: str
    review_state: MatchReviewState
    reviewed_by: str
    reviewed_at: str
    updated_at: str
    # True if the request's decision already matched the current review_state
    # — nothing was changed and no audit event was recorded, but the request
    # is still treated as a successful (idempotent) outcome.
    idempotent: bool = False
