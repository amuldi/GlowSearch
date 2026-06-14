from __future__ import annotations

import json
from pathlib import Path

from app.normalizer.text import clean_text
from app.search.synonyms import search_key


class SearchIntentExpander:
    def __init__(self, path: Path):
        self._path = path
        self._intents = self._load(path)

    def expand(self, query: str, *, limit: int = 12) -> list[str]:
        query_text = clean_text(query)
        query_key = search_key(query_text)
        if not query_text or not query_key:
            return []

        terms: list[str] = []
        seen: set[str] = {query_key}
        for intent in self._intents:
            label_keys = [search_key(label) for label in intent["labels"]]
            if not any(label_key and (label_key in query_key or query_key in label_key) for label_key in label_keys):
                continue
            for value in intent["terms"]:
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
    def _load(path: Path) -> list[dict[str, list[str]]]:
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return []
        intents: list[dict[str, list[str]]] = []
        for value in payload.values():
            if not isinstance(value, dict):
                continue
            labels = value.get("labels")
            terms = value.get("terms")
            if not isinstance(labels, list) or not isinstance(terms, list):
                continue
            intents.append(
                {
                    "labels": [item for item in labels if isinstance(item, str)],
                    "terms": [item for item in terms if isinstance(item, str)],
                }
            )
        return intents
