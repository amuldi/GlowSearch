from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from typing import Deque

from app.normalizer.text import clean_text
from app.search.synonyms import search_key


@dataclass(frozen=True)
class SearchAnalyticsSnapshot:
    popular: list[str]
    recent: list[str]
    trending: list[str]


class InMemorySearchAnalytics:
    def __init__(self, *, recent_limit: int = 50):
        self._recent: Deque[str] = deque(maxlen=max(recent_limit, 1))
        self._counts: Counter[str] = Counter()
        self._labels: dict[str, str] = {}

    def record(self, query: str) -> None:
        text = clean_text(query)
        key = search_key(text)
        if not text or not key:
            return
        self._recent.appendleft(text)
        self._counts[key] += 1
        self._labels[key] = text

    def snapshot(self, *, limit: int = 10) -> SearchAnalyticsSnapshot:
        popular = [
            self._labels[key]
            for key, _count in self._counts.most_common(max(limit, 1))
            if key in self._labels
        ]
        recent = _dedupe_recent(self._recent, limit=max(limit, 1))
        return SearchAnalyticsSnapshot(
            popular=popular,
            recent=recent,
            trending=popular,
        )


def _dedupe_recent(values: Deque[str], *, limit: int) -> list[str]:
    recent: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = search_key(value)
        if not key or key in seen:
            continue
        seen.add(key)
        recent.append(value)
        if len(recent) >= limit:
            return recent
    return recent
