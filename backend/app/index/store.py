from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from app.models.product import ProductSourceRecord
from app.normalizer.text import clean_text


@dataclass(frozen=True)
class IndexedSearchResult:
    records: list[ProductSourceRecord]
    is_stale: bool = False


class ProductIndexStore(Protocol):
    async def search(self, queries: list[str], limit: int) -> IndexedSearchResult:
        ...

    async def upsert(
        self,
        records: list[ProductSourceRecord],
        *,
        queries: list[str],
        source_priorities: dict[str, int] | None = None,
    ) -> None:
        ...


class _IndexedProductEntry(BaseModel):
    key: str
    record: ProductSourceRecord
    indexed_queries: list[str] = Field(default_factory=list)
    first_seen_at: datetime
    last_seen_at: datetime
    refreshed_at: datetime
    freshness_expires_at: datetime | None = None
    source_priority: int = 100


class _IndexPayload(BaseModel):
    version: int = 1
    products: list[_IndexedProductEntry] = Field(default_factory=list)


class JsonProductIndexStore:
    """Small local index used as a fast path before live collection.

    This is intentionally simple. It gives local/dev deployments a persistent cache while keeping
    the production path open for Postgres full-text search or a dedicated search engine.
    """

    def __init__(
        self,
        index_path: Path,
        *,
        seed_catalog_path: Path | None = None,
        fresh_ttl_seconds: int = 3600,
        stale_ttl_seconds: int = 604800,
        source_priorities: dict[str, int] | None = None,
    ):
        self._index_path = index_path
        self._fresh_ttl = timedelta(seconds=max(fresh_ttl_seconds, 0))
        self._stale_ttl = timedelta(seconds=max(stale_ttl_seconds, fresh_ttl_seconds, 0))
        self._source_priorities = source_priorities or {}
        self._lock = asyncio.Lock()
        self._entries: dict[str, _IndexedProductEntry] = {}
        self._load_index()
        if seed_catalog_path is not None:
            self._load_verified_catalog(seed_catalog_path)

    async def search(self, queries: list[str], limit: int) -> IndexedSearchResult:
        cleaned_queries = [query for query in (clean_text(query) for query in queries) if query]
        if not cleaned_queries or limit <= 0:
            return IndexedSearchResult(records=[])

        now = datetime.now(timezone.utc)
        async with self._lock:
            scored: list[tuple[bool, int, int, float, _IndexedProductEntry]] = []
            for entry in self._entries.values():
                if self._is_expired(entry, now):
                    continue
                score = max(self._match_score(entry, query) for query in cleaned_queries)
                if score <= 0:
                    continue
                is_stale = self._is_stale(entry, now)
                scored.append(
                    (
                        is_stale,
                        entry.source_priority,
                        -score,
                        -entry.refreshed_at.timestamp(),
                        entry,
                    )
                )

            scored.sort(key=lambda item: item[:4])
            selected = [entry for *_sort, entry in scored[:limit]]

        return IndexedSearchResult(
            records=[entry.record for entry in selected],
            is_stale=any(self._is_stale(entry, now) for entry in selected),
        )

    async def upsert(
        self,
        records: list[ProductSourceRecord],
        *,
        queries: list[str],
        source_priorities: dict[str, int] | None = None,
    ) -> None:
        if not records:
            return

        now = datetime.now(timezone.utc)
        priorities = {**self._source_priorities, **(source_priorities or {})}
        indexed_queries = self._dedupe_text([query for query in queries if clean_text(query)])

        async with self._lock:
            changed = False
            for record in records:
                key = self._record_key(record)
                if not key:
                    continue
                existing = self._entries.get(key)
                priority = priorities.get(record.source, 100)
                if existing is None:
                    self._entries[key] = _IndexedProductEntry(
                        key=key,
                        record=record,
                        indexed_queries=indexed_queries,
                        first_seen_at=now,
                        last_seen_at=now,
                        refreshed_at=now,
                        freshness_expires_at=now + self._fresh_ttl,
                        source_priority=priority,
                    )
                else:
                    self._entries[key] = existing.model_copy(
                        update={
                            "record": self._merge_records(existing.record, record),
                            "indexed_queries": self._dedupe_text(
                                [*existing.indexed_queries, *indexed_queries]
                            ),
                            "last_seen_at": now,
                            "refreshed_at": now,
                            "freshness_expires_at": now + self._fresh_ttl,
                            "source_priority": min(existing.source_priority, priority),
                        }
                    )
                changed = True

            if changed:
                self._persist_locked()

    def _load_index(self) -> None:
        if not self._index_path.exists():
            return
        try:
            payload = _IndexPayload.model_validate(
                json.loads(self._index_path.read_text(encoding="utf-8"))
            )
        except (OSError, ValueError):
            return
        self._entries = {entry.key: entry for entry in payload.products if entry.key}

    def _load_verified_catalog(self, catalog_path: Path) -> None:
        if not catalog_path.exists():
            return
        try:
            payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return

        now = datetime.now(timezone.utc)
        for item in payload.get("products", []):
            if not isinstance(item, dict):
                continue
            record = ProductSourceRecord(
                source_brand_name=clean_text(item.get("brand_ko") or item.get("brand_en")),
                product_name_ko=clean_text(item.get("product_name_ko")),
                regular_price=item.get("price"),
                currency=clean_text(item.get("currency")) or "KRW",
                shade=clean_text(item.get("shade")),
                image_url=clean_text(item.get("image_url")),
                source=clean_text(item.get("source")) or "oliveyoung:verified-cache",
                source_url=clean_text(item.get("source_url")),
                source_product_id=clean_text(item.get("goods_no")),
            )
            key = self._record_key(record)
            if not key:
                continue
            indexed_queries = self._dedupe_text(
                [
                    item.get("brand_ko"),
                    item.get("brand_en"),
                    item.get("product_name_ko"),
                    *(item.get("keywords", []) if isinstance(item.get("keywords"), list) else []),
                ]
            )
            self._entries.setdefault(
                key,
                _IndexedProductEntry(
                    key=key,
                    record=record,
                    indexed_queries=indexed_queries,
                    first_seen_at=now,
                    last_seen_at=now,
                    refreshed_at=now,
                    freshness_expires_at=None,
                    source_priority=self._source_priorities.get(record.source, 0),
                ),
            )

    def _persist_locked(self) -> None:
        payload = _IndexPayload(products=list(self._entries.values()))
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._index_path.with_suffix(f"{self._index_path.suffix}.tmp")
        temp_path.write_text(
            json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self._index_path)

    def _is_stale(self, entry: _IndexedProductEntry, now: datetime) -> bool:
        return entry.freshness_expires_at is not None and entry.freshness_expires_at <= now

    def _is_expired(self, entry: _IndexedProductEntry, now: datetime) -> bool:
        if entry.freshness_expires_at is None:
            return False
        return entry.freshness_expires_at + self._stale_ttl <= now

    @classmethod
    def _match_score(cls, entry: _IndexedProductEntry, query: str) -> int:
        query_key = cls._key(query)
        if not query_key:
            return 0

        haystack = cls._key(
            " ".join(
                value
                for value in [
                    entry.record.source_brand_name,
                    entry.record.product_name_ko,
                    entry.record.shade,
                    entry.record.source_url,
                    " ".join(entry.indexed_queries),
                ]
                if value
            )
        )
        if not haystack:
            return 0
        if query_key in haystack:
            return 100 + len(query_key)

        token_keys = [cls._key(token) for token in cls._tokens(query)]
        token_keys = [token for token in token_keys if token]
        if token_keys and all(token in haystack for token in token_keys):
            return 10 * len(token_keys)
        if token_keys and any(token in haystack for token in token_keys):
            return len([token for token in token_keys if token in haystack])
        return 0

    @classmethod
    def _record_key(cls, record: ProductSourceRecord) -> str:
        if record.source and record.source_product_id:
            return f"{record.source}:{record.source_product_id}"
        if record.source_url:
            return f"url:{cls._key(record.source_url)}"
        brand_key = cls._key(record.source_brand_name)
        name_key = cls._key(record.product_name_ko)
        if brand_key and name_key:
            return f"product:{brand_key}:{name_key}"
        return ""

    @staticmethod
    def _merge_records(
        existing: ProductSourceRecord,
        incoming: ProductSourceRecord,
    ) -> ProductSourceRecord:
        return existing.model_copy(
            update={
                "source_brand_name": incoming.source_brand_name or existing.source_brand_name,
                "product_name_ko": incoming.product_name_ko or existing.product_name_ko,
                "regular_price": (
                    incoming.regular_price
                    if incoming.regular_price is not None
                    else existing.regular_price
                ),
                "currency": incoming.currency or existing.currency,
                "shade": incoming.shade or existing.shade,
                "image_url": incoming.image_url or existing.image_url,
                "source_url": incoming.source_url or existing.source_url,
                "source_product_id": incoming.source_product_id or existing.source_product_id,
            }
        )

    @classmethod
    def _dedupe_text(cls, values: list[object]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = clean_text(str(value)) if value is not None else None
            key = cls._key(text)
            if not text or not key or key in seen:
                continue
            seen.add(key)
            deduped.append(text)
        return deduped

    @staticmethod
    def _tokens(value: str | None) -> list[str]:
        text = clean_text(value)
        if text is None:
            return []
        return re.findall(r"[0-9A-Za-z가-힣]+", text)

    @staticmethod
    def _key(value: str | None) -> str:
        text = clean_text(value)
        if text is None:
            return ""
        text = text.casefold()
        text = (
            text.replace("브러쉬", "브러시")
            .replace("brush", "브러시")
            .replace("eyeliner", "아이라이너")
            .replace("eye shadow", "아이섀도")
            .replace("glowy", "글로이")
            .replace("tear", "티어")
            .replace("gray", "그레이")
            .replace("grey", "그레이")
            .replace("쉐딩", "섀딩")
            .replace("셰딩", "섀딩")
            .replace("비타민씨", "비타")
            .replace("여백살롱", "여백카롱")
            .replace("및서재", "밑서재")
            .replace("플로팅", "플러팅")
            .replace("이즈핏", "이지핏")
            .replace("땡큐요엠핑크", "요염핑")
        )
        return re.sub(r"[\s\-_./|+&'():\[\],]+", "", text)
