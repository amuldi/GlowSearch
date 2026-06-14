from __future__ import annotations

import math
import re

from app.search.synonyms import search_key
from app.search_engine.document import SearchDocument
from app.search_engine.query import SearchQuery


def rank_documents(
    documents: list[SearchDocument],
    query: SearchQuery,
) -> list[SearchDocument]:
    scored = [
        (score_document(document, query, index), document)
        for index, document in enumerate(documents)
    ]
    ranked = sorted(scored, key=lambda item: item[0], reverse=True)
    return [
        document.model_copy(update={"score": round(score, 2)})
        for score, document in ranked
        if score > 0
    ]


def score_document(document: SearchDocument, query: SearchQuery, index: int = 0) -> float:
    query_text = query.text
    query_key = search_key(query_text)
    if not query_key:
        return 0.0

    expanded_terms = [term for term in query.expanded_terms if search_key(term)]
    name_key = search_key(document.name)
    brand_key = search_key(" ".join(value for value in [document.brand, document.brand_en] if value))
    category_key = search_key(document.category)
    description_key = search_key(document.description)
    tag_key = search_key(" ".join(document.tags))
    ingredient_key = search_key(" ".join(document.ingredients))
    review_key = search_key(" ".join(document.review_keywords))
    haystack_key = search_key(
        " ".join(
            value
            for value in [
                document.name,
                document.name_en,
                document.brand,
                document.brand_en,
                document.category,
                document.description,
                " ".join(document.tags),
                " ".join(document.ingredients),
                " ".join(document.review_keywords),
            ]
            if value
        )
    )
    if not haystack_key:
        return 0.0

    score = 0.0
    if query_key in name_key:
        score += 120
    if query_key in brand_key:
        score += 90
    if query_key in category_key:
        score += 45
    if query_key in tag_key:
        score += 50
    if query_key in ingredient_key:
        score += 35
    if query_key in review_key:
        score += 25
    if query_key in description_key:
        score += 20

    for token in _tokens(query_text):
        token_key = search_key(token)
        if len(token_key) >= 2 and token_key in haystack_key:
            score += 8

    for term in expanded_terms:
        term_key = search_key(term)
        if term_key and term_key in haystack_key:
            score += 18

    if document.rating is not None:
        score += min(max(document.rating, 0), 5) * 2
    if document.review_count is not None and document.review_count > 0:
        score += min(math.log10(document.review_count + 1) * 4, 16)
    if document.sales_count is not None and document.sales_count > 0:
        score += min(math.log10(document.sales_count + 1) * 3, 12)

    if score <= 0:
        return 0.0
    score += document.quality_score * 0.05
    return score - (index * 0.001)


def _tokens(value: str) -> list[str]:
    return re.findall(r"[0-9A-Za-z가-힣]+", value)
