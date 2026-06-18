export type ProductOffer = {
  source: string;
  source_label?: string | null;
  source_priority?: number | null;
  source_url: string;
  source_product_id?: string | null;
  price?: number | null;
  original_price?: number | null;
  sale_price?: number | null;
  currency?: string | null;
  image_url?: string | null;
  sold_out?: boolean | null;
  updated_at?: string | null;
};

export type Product = {
  canonical_product_id?: string | null;
  brand_ko: string | null;
  brand_en: string | null;
  product_name_ko: string | null;
  product_name_en: string | null;
  product_name_display_ko?: string | null;
  product_name_display_en?: string | null;
  category?: string | null;
  price: number | null;
  original_price?: number | null;
  sale_price?: number | null;
  discount_rate?: number | null;
  rating?: number | null;
  review_count?: number | null;
  currency?: string | null;
  shade: string | null;
  image_url: string | null;
  description?: string | null;
  options?: string[] | null;
  sold_out?: boolean | null;
  source_url: string | null;
  source_product_id?: string | null;
  source: string;
  source_label?: string | null;
  source_priority?: number | null;
  quality_score?: number;
  enrichment_missing_fields?: string[];
  offers?: ProductOffer[];
  updated_at?: string | null;
};

export type SearchResponse = {
  query: string;
  count: number;
  results: Product[];
  source_errors: string[];
};

export type SuggestionResponse = {
  query: string;
  suggestions: string[];
};

export type AdapterReadiness = {
  enabled: boolean;
  configured: boolean;
  base_url_configured: boolean;
  reason: string;
};

export type DiagnosticsResponse = {
  adapter_readiness?: Record<string, AdapterReadiness>;
  config?: {
    musinsa_api_enabled?: boolean;
    oliveyoung_global_api_enabled?: boolean;
    official_brand_api_enabled?: boolean;
    global_discovery_api_enabled?: boolean;
  };
  index?: {
    product_count?: number;
    search_gap_count?: number;
    last_refreshed_at?: string | null;
  };
  verified_catalog?: {
    total?: number;
    canonical_product_id?: number;
    product_name_en?: number;
    source_counts?: Record<string, number>;
  };
  search_gaps?: Array<{
    query?: string | null;
    normalized_query?: string | null;
    result_count?: number;
    miss_count?: number;
    last_reason?: string | null;
    last_seen_at?: string | null;
  }>;
  catalog_jobs?: {
    stats?: {
      total?: number;
      pending?: number;
      running?: number;
      completed?: number;
      failed?: number;
      skipped?: number;
      last_finished_at?: string | null;
      last_error?: string | null;
    };
    recent?: Array<{
      query?: string | null;
      normalized_query?: string | null;
      priority?: number;
      status?: string | null;
      attempt_count?: number;
      max_attempts?: number;
      product_count?: number | null;
      last_error?: string | null;
      updated_at?: string | null;
    }>;
  };
};

export type SearchParams = {
  query: string;
  limit?: number;
};

export type EditorParsedLine = {
  raw_text: string;
  brand_query: string | null;
  brand_en: string | null;
  product_query: string | null;
  shade_query: string | null;
  shade_code: string | null;
  shade_name: string | null;
  normalized_query: string;
};

export type EditorProductCandidate = {
  product: Product;
  match_score: number;
  match_reasons?: string[];
};

export type EditorBatchItem = {
  raw_text: string;
  parsed: EditorParsedLine;
  status: "확인됨" | "후보 있음" | "수동 확인 필요";
  candidates: EditorProductCandidate[];
};

export type EditorBatchResponse = {
  count: number;
  items: EditorBatchItem[];
};

export type EditorBatchProgress = {
  completed: number;
  total: number;
  response: EditorBatchResponse;
};

export type EditorConfirmRequest = {
  raw_text: string;
  normalized_query: string;
  source: string;
  source_url?: string | null;
  source_product_id?: string | null;
  canonical_product_id?: string | null;
  brand_ko?: string | null;
  brand_en?: string | null;
  product_name_ko?: string | null;
  product_name_en?: string | null;
  shade?: string | null;
};

export type EditorConfirmResponse = {
  saved: boolean;
};
