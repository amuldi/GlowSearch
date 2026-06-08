export type Product = {
  brand_ko: string | null;
  brand_en: string | null;
  product_name_ko: string | null;
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
  source: string;
  source_label?: string | null;
  source_priority?: number | null;
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

export type SearchParams = {
  query: string;
  limit?: number;
};
