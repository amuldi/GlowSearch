from __future__ import annotations

from collections.abc import Iterable

from app.indexing.store import ProductIndexStore
from app.models.product import ProductSearchResult, ProductSourceRecord
from app.normalizer.product import ProductNormalizer
from app.normalizer.text import clean_text
from app.search.synonyms import search_key
from app.search_engine.document import SearchDocument
from app.search_engine.provider import SearchProvider
from app.search_engine.query import SearchQuery, SearchResultPage
from app.search_engine.ranking import rank_documents
from app.service.source_policy import SourcePolicy


class SQLiteSearchProvider(SearchProvider):
    name = "sqlite"

    def __init__(
        self,
        store: ProductIndexStore,
        normalizer: ProductNormalizer,
        *,
        source_policy: SourcePolicy | None = None,
    ):
        self._store = store
        self._normalizer = normalizer
        self._source_policy = source_policy or SourcePolicy()

    async def search(self, query: SearchQuery) -> SearchResultPage:
        records = await self._search_records(query)
        documents = [
            document
            for record in records
            if (document := self._document_from_record(record)) is not None
        ]
        documents = self._apply_filters(documents, query)
        ranked = rank_documents(documents, query)
        results = ranked[: query.limit]
        return SearchResultPage(
            query=query.text,
            expanded_terms=query.expanded_terms,
            count=len(results),
            results=results,
            provider=self.name,
        )

    async def autocomplete(self, prefix: str, limit: int) -> list[str]:
        text = clean_text(prefix)
        if not text:
            return []
        records = await self._store.search(text, max(limit, 1) * 4)
        suggestions: list[str] = []
        for record in records:
            suggestions.extend(
                value
                for value in [record.source_brand_name, record.product_name_ko, record.category]
                if value
            )
        return _dedupe_suggestions(suggestions, prefix=text, limit=limit)

    async def upsert_products(self, products: list[ProductSourceRecord]) -> None:
        if not products:
            return
        await self._store.upsert_search_results("provider-upsert", products)

    async def close(self) -> None:
        await self._store.close()

    async def _search_records(self, query: SearchQuery) -> list[ProductSourceRecord]:
        terms = _dedupe_terms([query.text, *query.expanded_terms])
        records: list[ProductSourceRecord] = []
        seen: set[str] = set()
        for term in terms:
            source_records = await self._store.search(term, max(query.limit * 3, 24))
            for record in source_records:
                key = _record_key(record)
                if key in seen:
                    continue
                seen.add(key)
                records.append(record)
        return records

    def _document_from_record(self, record: ProductSourceRecord) -> SearchDocument | None:
        product = self._normalizer.normalize(record)
        if not product.product_name_ko or not product.source:
            return None
        if not (product.source_url or product.source_product_id):
            return None
        if not self._source_policy.allows(product.source):
            return None
        return _document_from_product(record, product)

    @staticmethod
    def _apply_filters(
        documents: list[SearchDocument],
        query: SearchQuery,
    ) -> list[SearchDocument]:
        filtered = documents
        if query.brand:
            brand_key = search_key(query.brand)
            filtered = [
                document
                for document in filtered
                if brand_key
                and (
                    brand_key in search_key(document.brand)
                    or brand_key in search_key(document.brand_en)
                )
            ]
        if query.min_price is not None:
            filtered = [
                document
                for document in filtered
                if document.price is not None and document.price >= query.min_price
            ]
        if query.max_price is not None:
            filtered = [
                document
                for document in filtered
                if document.price is not None and document.price <= query.max_price
            ]
        if query.has_shade is True:
            filtered = [
                document
                for document in filtered
                if document.shade
                or any(
                    search_key(tag) and search_key(tag) != search_key(document.category)
                    for tag in document.tags
                )
            ]
        return filtered


def _document_from_product(
    record: ProductSourceRecord,
    product: ProductSearchResult,
) -> SearchDocument:
    return SearchDocument(
        id=_record_key(record),
        name=product.product_name_ko or "",
        name_en=product.product_name_en,
        brand=product.brand_ko,
        brand_en=product.brand_en,
        category=product.category,
        shade=product.shade,
        description=product.description,
        tags=_tags_from_record(record),
        ingredients=[],
        review_keywords=[],
        rating=product.rating,
        review_count=product.review_count,
        sales_count=None,
        image_url=product.image_url,
        price=product.price,
        source=product.source,
        source_url=product.source_url,
        source_product_id=product.source_product_id,
        quality_score=product.quality_score,
    )


def _tags_from_record(record: ProductSourceRecord) -> list[str]:
    values = [record.category, record.shade, *(record.options or []), *(record.search_keywords or [])]
    return [text for value in values if (text := clean_text(value))]


def _record_key(record: ProductSourceRecord) -> str:
    if record.source_product_id:
        return f"{record.source}:{record.source_product_id}"
    brand_key = search_key(record.source_brand_name)
    name_key = search_key(record.product_name_ko)
    if brand_key and name_key:
        return f"{record.source}:{brand_key}:{name_key}"
    return f"{record.source}:{search_key(record.source_url)}"


def _dedupe_terms(values: Iterable[str | None]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_text(value)
        key = search_key(text)
        if not text or not key or key in seen:
            continue
        seen.add(key)
        terms.append(text)
    return terms


def _dedupe_suggestions(values: Iterable[str], *, prefix: str, limit: int) -> list[str]:
    prefix_key = search_key(prefix)
    suggestions: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_text(value)
        key = search_key(text)
        if not text or not key or key in seen:
            continue
        if prefix_key and prefix_key not in key:
            continue
        seen.add(key)
        suggestions.append(text)
        if len(suggestions) >= max(limit, 1):
            return suggestions
    return suggestions
