export type Product = {
  brand_ko: string | null;
  brand_en: string | null;
  product_name_ko: string | null;
  price: number | null;
  original_price?: number | null;
  sale_price?: number | null;
  discount_rate?: number | null;
  currency?: string | null;
  shade: string | null;
  image_url: string | null;
  source_url: string | null;
  source: string;
};

export type SearchResponse = {
  query: string;
  count: number;
  results: Product[];
  source_errors: string[];
};

export type SearchParams = {
  query: string;
  limit?: number;
};
