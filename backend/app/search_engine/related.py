from __future__ import annotations

from collections.abc import Iterable

from app.normalizer.text import clean_text
from app.search.synonyms import related_query_expansions, search_key
from app.search_engine.intent import SearchIntentExpander
from app.search_engine.synonyms import SearchSynonymExpander


class RelatedKeywordService:
    def __init__(
        self,
        synonym_expander: SearchSynonymExpander,
        intent_expander: SearchIntentExpander,
    ):
        self._synonym_expander = synonym_expander
        self._intent_expander = intent_expander

    def expand_query(self, query: str, *, limit: int = 12) -> list[str]:
        return _dedupe(
            [
                *self._synonym_expander.expand(query, limit=limit),
                *self._intent_expander.expand(query, limit=limit),
                *related_query_expansions(query),
            ],
            limit=limit,
            exclude={search_key(query)},
        )

    def related(self, query: str, *, limit: int = 10) -> list[str]:
        return self.expand_query(query, limit=limit)


def _dedupe(
    values: Iterable[str | None],
    *,
    limit: int,
    exclude: set[str] | None = None,
) -> list[str]:
    excluded = exclude or set()
    terms: list[str] = []
    seen: set[str] = set(excluded)
    for value in values:
        text = clean_text(value)
        key = search_key(text)
        if not text or not key or key in seen:
            continue
        seen.add(key)
        terms.append(text)
        if len(terms) >= limit:
            return terms
    return terms
