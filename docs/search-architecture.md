# GlowSearch Search Architecture

## Goal

GlowSearch should treat global cosmetics search as an indexing problem. A request-time live scrape can supplement results, but it should not be the primary way to answer every search.

## APIs And Adapters

The backend keeps the existing `ProductCollector.search(keyword, limit)` contract and adds adapter metadata in `app/source_adapters`.

- Managed scraping: `ApifyOliveYoungCollector` remains supported, and `BrightDataSerpCollector` can discover candidate product pages through Bright Data SERP when enabled.
- Product/source discovery: `SerpApiShoppingCollector`, `BingWebSearchCollector`, and `GoogleProgrammableSearchCollector` return attributed product/source candidates from search APIs.
- Barcode/GTIN lookup: `OpenBeautyFactsCollector`, `BarcodeLookupCollector`, and `UPCItemDBCollector` map barcode payloads into `ProductSourceRecord`.
- Brand-owned ingestion: `OfficialBrandSiteCollector` continues to use brand registry source URLs and generic product HTML parsing.

All adapters preserve the `source` and `source_url` fields. They may leave brand, price, or image empty when the provider does not verify the field.

## Agents And Modules

- `SourceDiscoveryAgent`: runs discovery adapters under per-source timeouts and dedupes candidate URLs.
- `ProductIngestionAgent`: runs product collectors/adapters under strict source budgets.
- `NormalizationAgent`: normalizes raw records, resolves brands, and dedupes products without inventing fields.
- `SearchOrchestratorAgent`: compatibility wrapper around request-time `SearchService`.
- `EvalAgent`: aggregates latency, result count, source failure, and reliability metrics for benchmarks.

## Request-Time Flow

```text
GET /search
  -> SearchService
  -> JsonProductIndexStore lookup
  -> return fresh indexed results immediately when present
  -> return stale indexed results immediately and revalidate in background when allowed
  -> otherwise run fast collectors in parallel with per-source timeouts
  -> use browser fallback only if fast collectors return no records
  -> normalize, filter, rank, cache, and upsert product index
```

The current local store is `JsonProductIndexStore`. It is useful for local/dev and small deployments. For production scale, replace the same `ProductIndexStore` protocol with Postgres plus full-text search first. Add Meilisearch, Typesense, or OpenSearch only when ranking, typo tolerance, or faceting outgrow Postgres.

## Persistent Index Plan

Recommended Postgres tables:

- `products`: canonical product identity, brand id, display name, normalized tokens, first seen, last refreshed.
- `product_sources`: source-specific URL, external id, price, currency, image, raw source payload hash, source priority, freshness timestamps.
- `brands`: official name, aliases, country/region hints, official site URLs.
- `ingestion_jobs`: source, query/url/barcode, status, retries, started/finished timestamps, error summary.

Use Postgres full-text search over canonical product names, aliases, source titles, and barcode/GTIN fields. Keep `product_sources` separate so conflicting fields remain attributable.

## Refresh And Dedupe

- Incremental refresh uses `freshness_expires_at` and `last_seen_at`.
- Stale-while-revalidate returns known data first, then refreshes asynchronously.
- Dedupe uses source product id when present, then source URL, then normalized brand + product name.
- Source priority favors verified cache/barcode/retailer sources over generic web discovery.
- Normalization rejects unverifiable core fields instead of guessing.

## Rollout Plan

1. Keep `JsonProductIndexStore` enabled with the verified catalog seed.
2. Enable one paid discovery adapter at a time, starting with SerpAPI Google Shopping or Bright Data SERP.
3. Add barcode lookup for exact GTIN searches with Open Beauty Facts first, then paid barcode APIs if recall is too low.
4. Move the store to Postgres FTS before increasing ingestion volume.
5. Run `scripts/benchmark_search.py` for every adapter rollout and track p50, p95, recall proxy, duplicate rate, source failures, and relevance samples.
