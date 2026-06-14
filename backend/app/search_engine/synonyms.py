from __future__ import annotations

import json
from pathlib import Path

from app.normalizer.text import clean_text
from app.search.synonyms import search_key


class SearchSynonymExpander:
    def __init__(self, path: Path):
        self._path = path
        self._entries = self._load(path)

    def expand(self, query: str, *, limit: int = 12) -> list[str]:
        query_text = clean_text(query)
        query_key = search_key(query_text)
        if not query_text or not query_key:
            return []

        terms: list[str] = []
        seen: set[str] = {query_key}
        for key, values in self._entries.items():
            entry_key = search_key(key)
            if not entry_key:
                continue
            if entry_key in query_key or query_key in entry_key:
                for value in values:
                    value_text = clean_text(value)
                    value_key = search_key(value_text)
                    if not value_text or not value_key or value_key in seen:
                        continue
                    seen.add(value_key)
                    terms.append(value_text)
                    if len(terms) >= limit:
                        return terms
        return terms

    @staticmethod
    def _load(path: Path) -> dict[str, list[str]]:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        entries: dict[str, list[str]] = {}
        for key, values in payload.items():
            if not isinstance(key, str) or not isinstance(values, list):
                continue
            entries[key] = [value for value in values if isinstance(value, str)]
        return entries
