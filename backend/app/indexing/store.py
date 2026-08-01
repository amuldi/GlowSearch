from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from app.indexing._libsql_compat import LibsqlConnection, Row
from app.models.product import ProductSourceRecord
from app.normalizer.brand import BrandAlias
from app.search.synonyms import search_key


@dataclass(frozen=True)
class CatalogIngestionJob:
    id: int
    job_key: str
    kind: str
    query: str
    normalized_query: str
    priority: int
    status: str
    attempt_count: int
    max_attempts: int
    last_error: str | None = None


class ProductIndexStore(Protocol):
    async def search(self, query: str, limit: int) -> list[ProductSourceRecord]: ...

    async def search_mapped(self, query: str, limit: int) -> list[ProductSourceRecord]: ...

    async def upsert_brand_aliases(self, aliases: list[BrandAlias]) -> None: ...

    async def upsert_search_results(
        self,
        query: str,
        records: list[ProductSourceRecord],
    ) -> None: ...

    async def record_search_gap(self, query: str, result_count: int, reason: str) -> None: ...

    async def recent_search_gaps(self, limit: int = 20) -> list[dict[str, int | str | None]]: ...

    async def enqueue_catalog_jobs(
        self,
        queries: list[str],
        *,
        kind: str = "oliveyoung-search",
        priority: int = 100,
        max_attempts: int = 3,
    ) -> int: ...

    async def claim_catalog_jobs(
        self,
        *,
        limit: int,
        kind: str | None = None,
    ) -> list[CatalogIngestionJob]: ...

    async def complete_catalog_job(
        self,
        job_id: int,
        *,
        status: str,
        product_count: int = 0,
        error: str | None = None,
    ) -> None: ...

    async def reset_stale_catalog_jobs(
        self,
        *,
        older_than_minutes: int,
        kind: str | None = None,
    ) -> int: ...

    async def catalog_job_stats(self) -> dict[str, int | str | None]: ...

    async def recent_catalog_jobs(self, limit: int = 20) -> list[dict[str, int | str | None]]: ...

    async def record_editor_confirmed_mapping(
        self,
        *,
        raw_text: str,
        normalized_query: str,
        source: str,
        source_url: str | None = None,
        source_product_id: str | None = None,
        canonical_product_id: str | None = None,
        brand_ko: str | None = None,
        brand_en: str | None = None,
        product_name_ko: str | None = None,
        product_name_en: str | None = None,
        shade: str | None = None,
    ) -> bool: ...

    async def stats(self) -> dict[str, int | str | None]: ...

    async def all_products(self, limit: int | None = None) -> list[ProductSourceRecord]: ...

    async def close(self) -> None: ...


class SQLiteProductIndexStore:
    def __init__(
        self,
        db_path: Path,
        *,
        turso_sync_url: str | None = None,
        turso_auth_token: str | None = None,
        turso_sync_interval_seconds: float | None = None,
    ):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = LibsqlConnection(
            str(self._db_path),
            sync_url=turso_sync_url,
            auth_token=turso_auth_token,
            sync_interval_seconds=turso_sync_interval_seconds,
        )
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=NORMAL")
        self._lock = asyncio.Lock()
        self._fts_enabled = True
        self._ensure_schema()

    @classmethod
    def for_remote(cls, url: str, auth_token: str | None) -> "SQLiteProductIndexStore":
        """Pure-remote Turso instance (no local file, no PRAGMA calls that
        only make sense for a local file) for app/indexing/turso_backup.py.
        Reuses all the normal schema/upsert/read logic below unchanged."""
        instance = cls.__new__(cls)
        instance._db_path = None
        instance._connection = LibsqlConnection(url, auth_token=auth_token, remote_only=True)
        instance._lock = asyncio.Lock()
        instance._fts_enabled = True
        instance._ensure_schema()
        return instance

    async def search(self, query: str, limit: int) -> list[ProductSourceRecord]:
        query_key = _key(query)
        if not query_key or limit <= 0:
            return []
        async with self._lock:
            mapped_rows = self._search_mapped_rows_locked(query_key, limit)
            records = [_row_to_record(row) for row in mapped_rows]
            if len(records) >= limit:
                return records

            seen = {_record_key(record) for record in records}
            for row in self._search_fallback_rows(query, limit * 4):
                self._append_unique_record(records, seen, row)
                if len(records) >= limit:
                    break
            return records

    async def search_mapped(self, query: str, limit: int) -> list[ProductSourceRecord]:
        query_key = _key(query)
        if not query_key or limit <= 0:
            return []
        async with self._lock:
            rows = self._search_mapped_rows_locked(query_key, limit)
        return [_row_to_record(row) for row in rows]

    def _search_mapped_rows_locked(self, query_key: str, limit: int) -> list[Row]:
        return self._connection.execute(
            """
            SELECT p.*
            FROM query_products qp
            JOIN products p ON p.id = qp.product_id
            WHERE qp.query_key = ?
            ORDER BY qp.rank ASC, p.last_seen_at DESC
            LIMIT ?
            """,
            (query_key, limit),
        ).fetchall()

    async def upsert_brand_aliases(self, aliases: list[BrandAlias]) -> None:
        if not aliases:
            return
        async with self._lock:
            self._upsert_brand_aliases_locked(aliases)
            self._backfill_fts_if_needed_locked()
            self._connection.commit()

    def seed_brand_aliases(self, aliases: list[BrandAlias]) -> None:
        if not aliases:
            return
        self._upsert_brand_aliases_locked(aliases)
        self._backfill_fts_if_needed_locked()
        self._connection.commit()

    async def record_search_gap(self, query: str, result_count: int, reason: str) -> None:
        query_text = query.strip()
        query_key = _key(query_text)
        if not query_key:
            return
        now = datetime.now(tz=UTC).isoformat()
        async with self._lock:
            self._connection.execute(
                """
                INSERT INTO search_gaps(
                    query_key,
                    query,
                    normalized_query,
                    result_count,
                    miss_count,
                    last_reason,
                    first_seen_at,
                    last_seen_at
                )
                VALUES(?, ?, ?, ?, 1, ?, ?, ?)
                ON CONFLICT(query_key) DO UPDATE SET
                    query = excluded.query,
                    result_count = excluded.result_count,
                    miss_count = search_gaps.miss_count + 1,
                    last_reason = excluded.last_reason,
                    last_seen_at = excluded.last_seen_at
                """,
                (query_key, query_text, query_key, max(result_count, 0), reason, now, now),
            )
            self._connection.commit()

    async def recent_search_gaps(self, limit: int = 20) -> list[dict[str, int | str | None]]:
        async with self._lock:
            rows = self._connection.execute(
                """
                SELECT query, normalized_query, result_count, miss_count, last_reason, last_seen_at
                FROM search_gaps
                ORDER BY last_seen_at DESC
                LIMIT ?
                """,
                (max(limit, 1),),
            ).fetchall()
        return [
            {
                "query": row["query"],
                "normalized_query": row["normalized_query"],
                "result_count": int(row["result_count"] or 0),
                "miss_count": int(row["miss_count"] or 0),
                "last_reason": row["last_reason"],
                "last_seen_at": row["last_seen_at"],
            }
            for row in rows
        ]

    async def enqueue_catalog_jobs(
        self,
        queries: list[str],
        *,
        kind: str = "oliveyoung-search",
        priority: int = 100,
        max_attempts: int = 3,
    ) -> int:
        now = datetime.now(tz=UTC).isoformat()
        clean_kind = _clean_job_kind(kind)
        inserted_or_updated = 0
        async with self._lock:
            for query in _dedupe_texts(queries):
                query_key = _key(query)
                if not query_key:
                    continue
                job_key = f"{clean_kind}:{query_key}"
                cursor = self._connection.execute(
                    """
                    INSERT INTO catalog_jobs(
                        job_key,
                        kind,
                        query,
                        normalized_query,
                        priority,
                        status,
                        attempt_count,
                        max_attempts,
                        created_at,
                        updated_at
                    )
                    VALUES(?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?)
                    ON CONFLICT(job_key) DO UPDATE SET
                        query = excluded.query,
                        priority = MIN(catalog_jobs.priority, excluded.priority),
                        max_attempts = MAX(catalog_jobs.max_attempts, excluded.max_attempts),
                        status = CASE
                            WHEN catalog_jobs.status IN ('completed', 'running') THEN catalog_jobs.status
                            ELSE 'pending'
                        END,
                        updated_at = excluded.updated_at
                    """,
                    (
                        job_key,
                        clean_kind,
                        query,
                        query_key,
                        max(priority, 0),
                        max(max_attempts, 1),
                        now,
                        now,
                    ),
                )
                if cursor.rowcount > 0:
                    inserted_or_updated += 1
            self._connection.commit()
        return inserted_or_updated

    async def claim_catalog_jobs(
        self,
        *,
        limit: int,
        kind: str | None = None,
    ) -> list[CatalogIngestionJob]:
        if limit <= 0:
            return []
        clean_kind = _clean_job_kind(kind) if kind else None
        now = datetime.now(tz=UTC).isoformat()
        async with self._lock:
            params: tuple[object, ...]
            kind_clause = ""
            if clean_kind:
                kind_clause = "AND kind = ?"
                params = (clean_kind, limit)
            else:
                params = (limit,)
            rows = self._connection.execute(
                f"""
                SELECT *
                FROM catalog_jobs
                WHERE status IN ('pending', 'failed')
                  AND attempt_count < max_attempts
                  {kind_clause}
                ORDER BY priority ASC, COALESCE(last_seen_at, '') ASC, id ASC
                LIMIT ?
                """,
                params,
            ).fetchall()
            if not rows:
                return []
            job_ids = [int(row["id"]) for row in rows]
            placeholders = ",".join("?" for _ in job_ids)
            self._connection.execute(
                f"""
                UPDATE catalog_jobs
                SET status = 'running',
                    attempt_count = attempt_count + 1,
                    started_at = ?,
                    updated_at = ?
                WHERE id IN ({placeholders})
                """,
                (now, now, *job_ids),
            )
            claimed_rows = self._connection.execute(
                f"SELECT * FROM catalog_jobs WHERE id IN ({placeholders}) ORDER BY priority ASC, id ASC",
                tuple(job_ids),
            ).fetchall()
            self._connection.commit()
        return [_catalog_job_from_row(row) for row in claimed_rows]

    async def complete_catalog_job(
        self,
        job_id: int,
        *,
        status: str,
        product_count: int = 0,
        error: str | None = None,
    ) -> None:
        clean_status = status if status in {"completed", "failed", "skipped"} else "failed"
        now = datetime.now(tz=UTC).isoformat()
        async with self._lock:
            self._connection.execute(
                """
                UPDATE catalog_jobs
                SET status = ?,
                    product_count = ?,
                    last_error = ?,
                    finished_at = ?,
                    last_seen_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    clean_status,
                    max(product_count, 0),
                    error,
                    now,
                    now,
                    now,
                    job_id,
                ),
            )
            self._connection.commit()

    async def reset_stale_catalog_jobs(
        self,
        *,
        older_than_minutes: int,
        kind: str | None = None,
    ) -> int:
        cutoff = (
            datetime.now(tz=UTC) - timedelta(minutes=max(older_than_minutes, 1))
        ).isoformat()
        clean_kind = _clean_job_kind(kind) if kind else None
        now = datetime.now(tz=UTC).isoformat()
        error = f"stale running job reset after {max(older_than_minutes, 1)} minutes"
        async with self._lock:
            params: tuple[object, ...]
            kind_clause = ""
            if clean_kind:
                kind_clause = "AND kind = ?"
                params = (error, now, cutoff, clean_kind)
            else:
                params = (error, now, cutoff)
            cursor = self._connection.execute(
                f"""
                UPDATE catalog_jobs
                SET status = CASE
                        WHEN attempt_count < max_attempts THEN 'pending'
                        ELSE 'failed'
                    END,
                    last_error = ?,
                    updated_at = ?
                WHERE status = 'running'
                  AND started_at IS NOT NULL
                  AND started_at < ?
                  {kind_clause}
                """,
                params,
            )
            self._connection.commit()
            return int(cursor.rowcount or 0)

    async def catalog_job_stats(self) -> dict[str, int | str | None]:
        async with self._lock:
            rows = self._connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM catalog_jobs
                GROUP BY status
                """
            ).fetchall()
            total = self._connection.execute(
                "SELECT COUNT(*) AS count FROM catalog_jobs"
            ).fetchone()["count"]
            last_finished_at = self._connection.execute(
                "SELECT MAX(finished_at) AS value FROM catalog_jobs"
            ).fetchone()["value"]
            last_error = self._connection.execute(
                """
                SELECT last_error
                FROM catalog_jobs
                WHERE last_error IS NOT NULL
                ORDER BY updated_at DESC
                LIMIT 1
                """
            ).fetchone()
        status_counts = {row["status"]: int(row["count"] or 0) for row in rows}
        return {
            "total": int(total or 0),
            "pending": status_counts.get("pending", 0),
            "running": status_counts.get("running", 0),
            "completed": status_counts.get("completed", 0),
            "failed": status_counts.get("failed", 0),
            "skipped": status_counts.get("skipped", 0),
            "last_finished_at": last_finished_at,
            "last_error": last_error["last_error"] if last_error else None,
        }

    async def recent_catalog_jobs(self, limit: int = 20) -> list[dict[str, int | str | None]]:
        async with self._lock:
            rows = self._connection.execute(
                """
                SELECT
                    id,
                    kind,
                    query,
                    normalized_query,
                    priority,
                    status,
                    attempt_count,
                    max_attempts,
                    product_count,
                    last_error,
                    updated_at
                FROM catalog_jobs
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (max(limit, 1),),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "kind": row["kind"],
                "query": row["query"],
                "normalized_query": row["normalized_query"],
                "priority": int(row["priority"] or 0),
                "status": row["status"],
                "attempt_count": int(row["attempt_count"] or 0),
                "max_attempts": int(row["max_attempts"] or 0),
                "product_count": (
                    int(row["product_count"]) if row["product_count"] is not None else None
                ),
                "last_error": row["last_error"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    async def record_editor_confirmed_mapping(
        self,
        *,
        raw_text: str,
        normalized_query: str,
        source: str,
        source_url: str | None = None,
        source_product_id: str | None = None,
        canonical_product_id: str | None = None,
        brand_ko: str | None = None,
        brand_en: str | None = None,
        product_name_ko: str | None = None,
        product_name_en: str | None = None,
        shade: str | None = None,
    ) -> bool:
        if not raw_text.strip() or not normalized_query.strip() or not source.strip():
            return False
        now = datetime.now(tz=UTC).isoformat()
        async with self._lock:
            self._connection.execute(
                """
                INSERT INTO editor_confirmed_mappings(
                    raw_text,
                    normalized_query,
                    canonical_product_id,
                    source,
                    source_url,
                    source_product_id,
                    brand_ko,
                    brand_en,
                    product_name_ko,
                    product_name_en,
                    shade,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    raw_text.strip(),
                    normalized_query.strip(),
                    canonical_product_id,
                    source.strip(),
                    source_url,
                    source_product_id,
                    brand_ko,
                    brand_en,
                    product_name_ko,
                    product_name_en,
                    shade,
                    now,
                    now,
                ),
            )
            self._connection.commit()
        return True

    async def upsert_search_results(
        self,
        query: str,
        records: list[ProductSourceRecord],
    ) -> None:
        query_key = _key(query)
        if not query_key or not records:
            return
        now = datetime.now(tz=UTC).isoformat()
        async with self._lock:
            for rank, record in enumerate(records, start=1):
                product_id = self._upsert_product(record, now)
                self._connection.execute(
                    """
                    INSERT INTO query_products(query_key, product_id, rank, refreshed_at)
                    VALUES(?, ?, ?, ?)
                    ON CONFLICT(query_key, product_id) DO UPDATE SET
                        rank = excluded.rank,
                        refreshed_at = excluded.refreshed_at
                    """,
                    (query_key, product_id, rank, now),
                )
            self._connection.commit()

    async def close(self) -> None:
        async with self._lock:
            self._connection.close()

    async def stats(self) -> dict[str, int | str | None]:
        async with self._lock:
            product_count = self._connection.execute(
                "SELECT COUNT(*) AS count FROM products"
            ).fetchone()["count"]
            query_count = self._connection.execute(
                "SELECT COUNT(DISTINCT query_key) AS count FROM query_products"
            ).fetchone()["count"]
            last_refreshed_at = self._connection.execute(
                "SELECT MAX(last_refreshed_at) AS value FROM products"
            ).fetchone()["value"]
            alias_count = self._connection.execute(
                "SELECT COUNT(*) AS count FROM brand_aliases"
            ).fetchone()["count"]
            gap_count = self._connection.execute(
                "SELECT COUNT(*) AS count FROM search_gaps"
            ).fetchone()["count"]
            last_gap_at = self._connection.execute(
                "SELECT MAX(last_seen_at) AS value FROM search_gaps"
            ).fetchone()["value"]
        return {
            "product_count": int(product_count or 0),
            "query_count": int(query_count or 0),
            "brand_alias_count": int(alias_count or 0),
            "search_gap_count": int(gap_count or 0),
            "last_refreshed_at": last_refreshed_at,
            "last_search_gap_at": last_gap_at,
        }

    async def all_products(self, limit: int | None = None) -> list[ProductSourceRecord]:
        sql = "SELECT * FROM products ORDER BY last_seen_at DESC, id DESC"
        params: tuple[int, ...] = ()
        if limit is not None and limit > 0:
            sql = f"{sql} LIMIT ?"
            params = (limit,)
        async with self._lock:
            rows = self._connection.execute(sql, params).fetchall()
        return [_row_to_record(row) for row in rows]

    def _ensure_schema(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_key TEXT NOT NULL UNIQUE,
                canonical_product_id TEXT,
                source TEXT NOT NULL,
                source_product_id TEXT,
                category TEXT,
                source_brand_name TEXT,
                source_brand_name_en TEXT,
                product_name_ko TEXT,
                product_name_en TEXT,
                product_name_display_ko TEXT,
                product_name_display_en TEXT,
                regular_price REAL,
                original_price REAL,
                sale_price REAL,
                discount_rate INTEGER,
                rating REAL,
                review_count INTEGER,
                currency TEXT,
                shade TEXT,
                image_url TEXT,
                description TEXT,
                options_json TEXT,
                search_keywords_json TEXT,
                sold_out INTEGER,
                source_url TEXT,
                search_text TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                last_refreshed_at TEXT NOT NULL,
                source_updated_at TEXT
            )
            """
        )
        self._ensure_columns(
            "products",
            {
                "canonical_product_id": "TEXT",
                "category": "TEXT",
                "source_brand_name_en": "TEXT",
                "product_name_en": "TEXT",
                "product_name_display_ko": "TEXT",
                "product_name_display_en": "TEXT",
                "rating": "REAL",
                "review_count": "INTEGER",
                "description": "TEXT",
                "options_json": "TEXT",
                "search_keywords_json": "TEXT",
                "sold_out": "INTEGER",
                "source_updated_at": "TEXT",
            },
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS query_products (
                query_key TEXT NOT NULL,
                product_id INTEGER NOT NULL,
                rank INTEGER NOT NULL,
                refreshed_at TEXT NOT NULL,
                PRIMARY KEY(query_key, product_id),
                FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
            )
            """
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_products_search_text ON products(search_text)"
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_query_products_rank ON query_products(query_key, rank)"
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS brand_aliases (
                alias_key TEXT PRIMARY KEY,
                alias TEXT NOT NULL,
                official_en TEXT NOT NULL,
                source TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_brand_aliases_official ON brand_aliases(official_en)"
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS search_gaps (
                query_key TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                normalized_query TEXT NOT NULL,
                result_count INTEGER NOT NULL,
                miss_count INTEGER NOT NULL,
                last_reason TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS catalog_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_key TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL,
                query TEXT NOT NULL,
                normalized_query TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 100,
                status TEXT NOT NULL DEFAULT 'pending',
                attempt_count INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 3,
                product_count INTEGER,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                last_seen_at TEXT
            )
            """
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_catalog_jobs_status_priority ON catalog_jobs(status, priority, id)"
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_catalog_jobs_kind_status ON catalog_jobs(kind, status)"
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS editor_confirmed_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_text TEXT NOT NULL,
                normalized_query TEXT NOT NULL,
                canonical_product_id TEXT,
                source TEXT NOT NULL,
                source_url TEXT,
                source_product_id TEXT,
                brand_ko TEXT,
                brand_en TEXT,
                product_name_ko TEXT,
                product_name_en TEXT,
                shade TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_editor_confirmed_mappings_query
            ON editor_confirmed_mappings(normalized_query)
            """
        )
        self._ensure_fts_table()
        self._connection.commit()

    def _ensure_fts_table(self) -> None:
        try:
            self._connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS products_fts USING fts5(
                    record_key UNINDEXED,
                    source_brand_name,
                    product_name_ko,
                    category,
                    description,
                    shade,
                    options,
                    aliases,
                    search_terms,
                    tokenize='unicode61'
                )
                """
            )
        except (sqlite3.OperationalError, ValueError):
            self._fts_enabled = False

    def _ensure_columns(self, table: str, columns: dict[str, str]) -> None:
        existing = {
            row["name"]
            for row in self._connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for column, definition in columns.items():
            if column in existing:
                continue
            self._connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _upsert_brand_aliases_locked(self, aliases: list[BrandAlias]) -> None:
        now = datetime.now(tz=UTC).isoformat()
        for alias in aliases:
            alias_key = _key(alias.alias)
            official = alias.official_en.strip()
            alias_text = alias.alias.strip()
            if not alias_key or not official or not alias_text:
                continue
            self._connection.execute(
                """
                INSERT INTO brand_aliases(alias_key, alias, official_en, source, updated_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(alias_key) DO UPDATE SET
                    alias = excluded.alias,
                    official_en = excluded.official_en,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (alias_key, alias_text, official, alias.source, now),
            )

    def _upsert_product(self, record: ProductSourceRecord, now: str) -> int:
        record_key = _record_key(record)
        search_text = _search_text(record)
        options_json = _options_json(record.options)
        search_keywords_json = _options_json(record.search_keywords)
        source_updated_at = record.updated_at or now
        self._connection.execute(
            """
            INSERT INTO products(
                record_key,
                canonical_product_id,
                source,
                source_product_id,
                category,
                source_brand_name,
                source_brand_name_en,
                product_name_ko,
                product_name_en,
                product_name_display_ko,
                product_name_display_en,
                regular_price,
                original_price,
                sale_price,
                discount_rate,
                rating,
                review_count,
                currency,
                shade,
                image_url,
                description,
                options_json,
                search_keywords_json,
                sold_out,
                source_url,
                search_text,
                first_seen_at,
                last_seen_at,
                last_refreshed_at,
                source_updated_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(record_key) DO UPDATE SET
                canonical_product_id = COALESCE(excluded.canonical_product_id, products.canonical_product_id),
                source = excluded.source,
                source_product_id = COALESCE(excluded.source_product_id, products.source_product_id),
                category = COALESCE(excluded.category, products.category),
                source_brand_name = COALESCE(excluded.source_brand_name, products.source_brand_name),
                source_brand_name_en = COALESCE(excluded.source_brand_name_en, products.source_brand_name_en),
                product_name_ko = COALESCE(excluded.product_name_ko, products.product_name_ko),
                product_name_en = COALESCE(excluded.product_name_en, products.product_name_en),
                product_name_display_ko = COALESCE(excluded.product_name_display_ko, products.product_name_display_ko),
                product_name_display_en = COALESCE(excluded.product_name_display_en, products.product_name_display_en),
                regular_price = COALESCE(excluded.regular_price, products.regular_price),
                original_price = COALESCE(excluded.original_price, products.original_price),
                sale_price = excluded.sale_price,
                discount_rate = excluded.discount_rate,
                rating = COALESCE(excluded.rating, products.rating),
                review_count = COALESCE(excluded.review_count, products.review_count),
                currency = COALESCE(excluded.currency, products.currency),
                shade = COALESCE(excluded.shade, products.shade),
                image_url = COALESCE(excluded.image_url, products.image_url),
                description = COALESCE(excluded.description, products.description),
                options_json = COALESCE(excluded.options_json, products.options_json),
                search_keywords_json = COALESCE(excluded.search_keywords_json, products.search_keywords_json),
                sold_out = COALESCE(excluded.sold_out, products.sold_out),
                source_url = COALESCE(excluded.source_url, products.source_url),
                search_text = excluded.search_text,
                last_seen_at = excluded.last_seen_at,
                last_refreshed_at = excluded.last_refreshed_at,
                source_updated_at = COALESCE(excluded.source_updated_at, excluded.last_refreshed_at)
            """,
            (
                record_key,
                record.canonical_product_id,
                record.source,
                record.source_product_id,
                record.category,
                record.source_brand_name,
                record.source_brand_name_en,
                record.product_name_ko,
                record.product_name_en,
                record.product_name_display_ko,
                record.product_name_display_en,
                record.regular_price,
                record.original_price,
                record.sale_price,
                record.discount_rate,
                record.rating,
                record.review_count,
                record.currency,
                record.shade,
                record.image_url,
                record.description,
                options_json,
                search_keywords_json,
                _sqlite_bool(record.sold_out),
                record.source_url,
                search_text,
                now,
                now,
                now,
                source_updated_at,
            ),
        )
        row = self._connection.execute(
            "SELECT id FROM products WHERE record_key = ?",
            (record_key,),
        ).fetchone()
        self._upsert_product_fts(record_key, record)
        return int(row["id"])

    def _upsert_product_fts(self, record_key: str, record: ProductSourceRecord) -> None:
        if not self._fts_enabled:
            return
        try:
            self._connection.execute(
                "DELETE FROM products_fts WHERE record_key = ?",
                (record_key,),
            )
            self._connection.execute(
                """
                INSERT INTO products_fts(
                    record_key,
                    source_brand_name,
                    product_name_ko,
                    category,
                    description,
                    shade,
                    options,
                    aliases,
                    search_terms
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_key,
                    " ".join(
                        value
                        for value in [record.source_brand_name, record.source_brand_name_en]
                        if value
                    ),
                    " ".join(
                        value
                        for value in [
                            record.product_name_ko,
                            record.product_name_en,
                            record.product_name_display_ko,
                            record.product_name_display_en,
                        ]
                        if value
                    ),
                    record.category,
                    record.description,
                    record.shade,
                    " ".join(record.options or []),
                    " ".join(self._alias_terms_for_record(record)),
                    _search_terms(record),
                ),
            )
        except (sqlite3.OperationalError, ValueError):
            self._fts_enabled = False

    def _backfill_fts_if_needed_locked(self) -> None:
        if not self._fts_enabled:
            return
        try:
            product_count = self._connection.execute(
                "SELECT COUNT(*) AS count FROM products"
            ).fetchone()["count"]
            fts_count = self._connection.execute(
                "SELECT COUNT(*) AS count FROM products_fts"
            ).fetchone()["count"]
        except (sqlite3.OperationalError, ValueError):
            self._fts_enabled = False
            return
        if not product_count or fts_count >= product_count:
            return
        rows = self._connection.execute("SELECT * FROM products").fetchall()
        for row in rows:
            self._upsert_product_fts(row["record_key"], _row_to_record(row))

    def _search_fallback_rows(self, query: str, limit: int) -> list[Row]:
        rows: list[Row] = []
        seen_record_keys: set[str] = set()
        for candidate in self._fallback_queries(query):
            if self._fts_enabled:
                for row in self._search_fts_rows(candidate, limit):
                    record_key = row["record_key"]
                    if record_key in seen_record_keys:
                        continue
                    seen_record_keys.add(record_key)
                    rows.append(row)
                    if len(rows) >= limit:
                        return rows
            candidate_key = _key(candidate)
            if not candidate_key:
                continue
            like_rows = self._connection.execute(
                """
                SELECT *
                FROM products
                WHERE search_text LIKE ?
                ORDER BY last_seen_at DESC, id DESC
                LIMIT ?
                """,
                (f"%{candidate_key}%", limit),
            ).fetchall()
            for row in like_rows:
                record_key = row["record_key"]
                if record_key in seen_record_keys:
                    continue
                seen_record_keys.add(record_key)
                rows.append(row)
                if len(rows) >= limit:
                    return rows
        return rows

    def _search_fts_rows(self, query: str, limit: int) -> list[Row]:
        match_query = _fts_match_query(query)
        if not match_query:
            return []
        try:
            return self._connection.execute(
                """
                SELECT p.*, bm25(products_fts) AS fts_rank
                FROM products_fts
                JOIN products p ON p.record_key = products_fts.record_key
                WHERE products_fts MATCH ?
                ORDER BY fts_rank ASC, p.last_seen_at DESC, p.id DESC
                LIMIT ?
                """,
                (match_query, limit),
            ).fetchall()
        except (sqlite3.OperationalError, ValueError):
            self._fts_enabled = False
            return []

    def _fallback_queries(self, query: str) -> list[str]:
        candidates = [query]
        query_key = _key(query)
        if len(query_key) >= 2:
            rows = self._connection.execute(
                """
                SELECT DISTINCT official_en
                FROM brand_aliases
                WHERE alias_key = ?
                   OR alias_key LIKE ?
                   OR ? LIKE alias_key || '%'
                   OR instr(alias_key, ?) > 0
                ORDER BY length(alias_key) ASC
                LIMIT 8
                """,
                (query_key, f"{query_key}%", query_key, query_key),
            ).fetchall()
            for row in rows:
                alias_rows = self._connection.execute(
                    """
                    SELECT alias
                    FROM brand_aliases
                    WHERE official_en = ?
                    ORDER BY CASE WHEN alias GLOB '*[가-힣]*' THEN 0 ELSE 1 END, length(alias)
                    LIMIT 8
                    """,
                    (row["official_en"],),
                ).fetchall()
                candidates.extend(row["alias"] for row in alias_rows)
        return _dedupe_texts(candidates)

    def _alias_terms_for_record(self, record: ProductSourceRecord) -> list[str]:
        keys = {
            _key(record.source_brand_name),
            _key(record.source_brand_name_en),
            *[
                alias_key
                for alias_key in self._record_brand_alias_keys(record.product_name_ko)
            ],
            *[
                alias_key
                for alias_key in self._record_brand_alias_keys(record.product_name_en)
            ],
        }
        aliases: list[str] = []
        for key in keys:
            if not key:
                continue
            rows = self._connection.execute(
                """
                SELECT related.alias
                FROM brand_aliases seed
                JOIN brand_aliases related ON related.official_en = seed.official_en
                WHERE seed.alias_key = ?
                ORDER BY CASE WHEN related.alias GLOB '*[가-힣]*' THEN 0 ELSE 1 END, length(related.alias)
                """,
                (key,),
            ).fetchall()
            aliases.extend(row["alias"] for row in rows)
        return _dedupe_texts(aliases)

    def _record_brand_alias_keys(self, value: str | None) -> list[str]:
        text_key = _key(value)
        if len(text_key) < 2:
            return []
        rows = self._connection.execute(
            """
            SELECT alias_key
            FROM brand_aliases
            WHERE instr(?, alias_key) > 0
            ORDER BY length(alias_key) DESC
            LIMIT 8
            """,
            (text_key,),
        ).fetchall()
        return [row["alias_key"] for row in rows]

    @staticmethod
    def _append_unique_record(
        records: list[ProductSourceRecord],
        seen: set[str],
        row: Row,
    ) -> None:
        record = _row_to_record(row)
        record_key = _record_key(record)
        if record_key in seen:
            return
        seen.add(record_key)
        records.append(record)


def _row_to_record(row: Row) -> ProductSourceRecord:
    return ProductSourceRecord(
        canonical_product_id=row["canonical_product_id"],
        category=row["category"],
        source_brand_name=row["source_brand_name"],
        source_brand_name_en=row["source_brand_name_en"],
        product_name_ko=row["product_name_ko"],
        product_name_en=row["product_name_en"],
        product_name_display_ko=row["product_name_display_ko"],
        product_name_display_en=row["product_name_display_en"],
        regular_price=row["regular_price"],
        original_price=row["original_price"],
        sale_price=row["sale_price"],
        discount_rate=row["discount_rate"],
        rating=row["rating"],
        review_count=row["review_count"],
        currency=row["currency"],
        shade=row["shade"],
        image_url=row["image_url"],
        description=row["description"],
        options=_options_from_json(row["options_json"]),
        search_keywords=_options_from_json(row["search_keywords_json"]),
        sold_out=_bool_from_sqlite(row["sold_out"]),
        source=row["source"],
        source_url=row["source_url"],
        source_product_id=row["source_product_id"],
        updated_at=row["source_updated_at"] or row["last_refreshed_at"],
    )


def _catalog_job_from_row(row: Row) -> CatalogIngestionJob:
    return CatalogIngestionJob(
        id=int(row["id"]),
        job_key=row["job_key"],
        kind=row["kind"],
        query=row["query"],
        normalized_query=row["normalized_query"],
        priority=int(row["priority"] or 0),
        status=row["status"],
        attempt_count=int(row["attempt_count"] or 0),
        max_attempts=int(row["max_attempts"] or 0),
        last_error=row["last_error"],
    )


def _search_text(record: ProductSourceRecord) -> str:
    return _key(
        " ".join(
            value
            for value in [
                record.source_brand_name,
                record.source_brand_name_en,
                record.canonical_product_id,
                record.product_name_ko,
                record.product_name_en,
                record.product_name_display_ko,
                record.product_name_display_en,
                record.category,
                record.description,
                record.shade,
                record.source_product_id,
                " ".join(record.options or []),
                " ".join(record.search_keywords or []),
            ]
            if value
        )
    )


def _search_terms(record: ProductSourceRecord) -> str:
    values = [
        record.source_brand_name,
        record.source_brand_name_en,
        record.product_name_ko,
        record.product_name_en,
        record.product_name_display_ko,
        record.product_name_display_en,
        record.category,
        record.description,
        record.shade,
        record.source_product_id,
        " ".join(record.options or []),
        " ".join(record.search_keywords or []),
    ]
    terms: list[str] = []
    for value in values:
        text = value.strip() if isinstance(value, str) else ""
        if not text:
            continue
        terms.append(text.casefold())
        terms.extend(_tokens(text))
        terms.extend(_compact_ngrams(_key(text)))
    return " ".join(_dedupe_texts(terms))


def _fts_match_query(value: str | None) -> str:
    terms = [
        term
        for term in [
            *_tokens(value),
            _key(value),
            *_compact_ngrams(_key(value), min_size=2, max_size=4),
        ]
        if term and len(term) >= 2
    ]
    escaped = [_escape_fts_token(term) for term in _dedupe_texts(terms)[:32]]
    return " OR ".join(f'"{term}"' for term in escaped if term)


def _tokens(value: str | None) -> list[str]:
    if not value:
        return []
    return [token.casefold() for token in re.findall(r"[0-9A-Za-z가-힣]+", value)]


def _compact_ngrams(value: str | None, *, min_size: int = 2, max_size: int = 8) -> list[str]:
    key = _key(value)
    if len(key) < min_size:
        return []
    terms = [key]
    capped_max = min(max_size, len(key))
    for size in range(min_size, capped_max + 1):
        for start in range(0, len(key) - size + 1):
            terms.append(key[start : start + size])
    return terms


def _escape_fts_token(value: str) -> str:
    return value.replace('"', '""')


def _dedupe_texts(values: list[str] | tuple[str, ...]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = value.strip() if isinstance(value, str) else ""
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped


def _clean_job_kind(value: str | None) -> str:
    text = (value or "").strip().casefold()
    text = re.sub(r"[^0-9a-z가-힣:_-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "oliveyoung-search"


def _options_json(options: list[str] | None) -> str | None:
    cleaned = [option.strip() for option in options or [] if option and option.strip()]
    if not cleaned:
        return None
    return json.dumps(cleaned, ensure_ascii=False)


def _options_from_json(value: str | None) -> list[str] | None:
    if not value:
        return None
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list):
        return None
    options = [item for item in payload if isinstance(item, str) and item.strip()]
    return options or None


def _sqlite_bool(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def _bool_from_sqlite(value: object | None) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _record_key(record: ProductSourceRecord) -> str:
    if record.source_product_id and (
        record.source == "oliveyoung" or record.source.startswith("oliveyoung:")
    ):
        return f"oliveyoung:{record.source_product_id}"
    brand_key = _key(record.source_brand_name)
    name_key = _key(record.product_name_ko)
    if brand_key and name_key:
        return f"product:{brand_key}:{name_key}"
    if record.source_product_id:
        return f"{record.source}:{record.source_product_id}"
    return f"{record.source}:{_key(record.source_url)}"


def _key(value: str | None) -> str:
    return search_key(value)
