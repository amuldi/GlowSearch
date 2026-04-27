export type Product = {
  brand_en: string | null;
  product_name_ko: string | null;
  price: number | null;
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
  brand?: string;
  minPrice?: string;
  maxPrice?: string;
  hasShade?: boolean;
  limit?: number;
};
