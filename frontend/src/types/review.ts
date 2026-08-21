// Mirrors backend/app/models/review.py (milestone 4). Keep field names and
// nullability in sync with that file, not the other way around.

export type MatchReviewState = "verified" | "pending_review" | "rejected" | "invalid";

export type MatchOfferSummary = {
  source: string;
  source_label?: string | null;
  source_url: string;
  source_product_id?: string | null;
  price?: number | null;
  image_url?: string | null;
  sold_out?: boolean | null;
  updated_at?: string | null;
};

export type MatchTargetSummary = {
  canonical_product_id: string;
  brand_ko?: string | null;
  brand_en?: string | null;
  product_name_ko?: string | null;
  product_name_display_ko?: string | null;
  image_url?: string | null;
};

export type MatchEvidenceItem = {
  type: string;
  value?: string | null;
  weight?: number | null;
};

export type PendingMatchSummary = {
  match_id: string;
  id: number;
  canonical_product_id: string;
  confidence: number;
  match_method: string;
  created_at: string;
  offer: MatchOfferSummary;
  target?: MatchTargetSummary | null;
};

export type PendingMatchListResponse = {
  items: PendingMatchSummary[];
  next_after_id?: number | null;
};

export type MatchReviewEvent = {
  previous_review_state: string;
  new_review_state: string;
  reviewer: string;
  note?: string | null;
  created_at: string;
};

export type MatchDetail = {
  match_id: string;
  canonical_product_id: string;
  review_state: MatchReviewState;
  confidence: number;
  match_method: string;
  evidence: MatchEvidenceItem[];
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  created_at: string;
  updated_at: string;
  offer: MatchOfferSummary;
  target?: MatchTargetSummary | null;
  history: MatchReviewEvent[];
};

export type MatchReviewDecision = "verified" | "rejected";

export type MatchReviewRequest = {
  decision: MatchReviewDecision;
  reviewer: string;
  note?: string | null;
  expected_updated_at?: string | null;
};

export type MatchReviewResponse = {
  match_id: string;
  review_state: MatchReviewState;
  reviewed_by: string;
  reviewed_at: string;
  updated_at: string;
  idempotent: boolean;
};
