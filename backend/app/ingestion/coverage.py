from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.core.config import Settings
from app.indexing.store import ProductIndexStore
from app.normalizer.text import clean_text
from app.search.synonyms import search_key


@dataclass(frozen=True)
class CoverageQueryOptions:
    custom_queries: Iterable[str] = field(default_factory=tuple)
    include_default_seeds: bool = True
    extra_seed_queries: Iterable[str] = field(default_factory=tuple)
    coverage_pairs: int = 300
    include_gaps: bool = True
    gap_limit: int = 100
    max_queries: int | None = None


async def build_coverage_queries(
    settings: Settings,
    store: ProductIndexStore,
    options: CoverageQueryOptions,
) -> list[str]:
    queries: list[str] = []
    queries.extend(options.custom_queries)

    if options.include_default_seeds:
        queries.extend(settings.product_index_seed_queries)
        queries.extend(settings.product_index_category_queries)
        queries.extend(settings.product_index_brand_queries)

    queries.extend(options.extra_seed_queries)

    if options.coverage_pairs > 0:
        queries.extend(
            coverage_pair_queries(
                settings.product_index_brand_queries,
                settings.product_index_category_queries,
                options.coverage_pairs,
            )
        )

    if options.include_gaps:
        gaps = await store.recent_search_gaps(limit=max(options.gap_limit, 1))
        queries.extend(str(gap["query"]) for gap in gaps if gap.get("query"))

    deduped = dedupe_queries(queries)
    if options.max_queries is not None and options.max_queries >= 0:
        return deduped[: options.max_queries]
    return deduped


def coverage_pair_queries(
    brand_queries: Iterable[str],
    category_queries: Iterable[str],
    limit: int,
) -> list[str]:
    pairs: list[str] = []
    seen: set[str] = set()
    for brand in brand_queries:
        clean_brand = clean_text(brand)
        if not clean_brand:
            continue
        for category in category_queries:
            clean_category = clean_text(category)
            if not clean_category:
                continue
            query = f"{clean_brand} {clean_category}"
            key = search_key(query)
            if not key or key in seen:
                continue
            seen.add(key)
            pairs.append(query)
            if len(pairs) >= max(limit, 0):
                return pairs
    return pairs


def dedupe_queries(queries: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for query in queries:
        text = clean_text(query)
        key = search_key(text)
        if not text or not key or key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped
