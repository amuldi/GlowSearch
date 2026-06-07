from __future__ import annotations

import asyncio
import re
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from app.models.product import ProductSourceRecord
from app.normalizer.text import clean_text


class ProductIndexStore(Protocol):
    async def search(self, query: str, limit: int) -> list[ProductSourceRecord]: ...

    async def upsert_search_results(
        self,
        query: str,
        records: list[ProductSourceRecord],
    ) -> None: ...

    async def stats(self) -> dict[str, int | str | None]: ...

    async def close(self) -> None: ...


class SQLiteProductIndexStore:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self._db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = asyncio.Lock()
        self._ensure_schema()

    async def search(self, query: str, limit: int) -> list[ProductSourceRecord]:
        query_key = _key(query)
        if not query_key or limit <= 0:
            return []
        async with self._lock:
            mapped_rows = self._connection.execute(
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
            records = [_row_to_record(row) for row in mapped_rows]
            if len(records) >= limit:
                return records

            seen = {_record_key(record) for record in records}
            fallback_rows = self._connection.execute(
                """
                SELECT *
                FROM products
                WHERE search_text LIKE ?
                ORDER BY last_seen_at DESC, id DESC
                LIMIT ?
                """,
                (f"%{query_key}%", limit * 3),
            ).fetchall()
            for row in fallback_rows:
                record = _row_to_record(row)
                record_key = _record_key(record)
                if record_key in seen:
                    continue
                seen.add(record_key)
                records.append(record)
                if len(records) >= limit:
                    break
            return records

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
        return {
            "product_count": int(product_count or 0),
            "query_count": int(query_count or 0),
            "last_refreshed_at": last_refreshed_at,
        }

    def _ensure_schema(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_key TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                source_product_id TEXT,
                source_brand_name TEXT,
                product_name_ko TEXT,
                regular_price INTEGER,
                original_price INTEGER,
                sale_price INTEGER,
                discount_rate INTEGER,
                currency TEXT,
                shade TEXT,
                image_url TEXT,
                source_url TEXT,
                search_text TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                last_refreshed_at TEXT NOT NULL
            )
            """
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
        self._connection.commit()

    def _upsert_product(self, record: ProductSourceRecord, now: str) -> int:
        record_key = _record_key(record)
        search_text = _search_text(record)
        self._connection.execute(
            """
            INSERT INTO products(
                record_key,
                source,
                source_product_id,
                source_brand_name,
                product_name_ko,
                regular_price,
                original_price,
                sale_price,
                discount_rate,
                currency,
                shade,
                image_url,
                source_url,
                search_text,
                first_seen_at,
                last_seen_at,
                last_refreshed_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(record_key) DO UPDATE SET
                source = excluded.source,
                source_product_id = COALESCE(excluded.source_product_id, products.source_product_id),
                source_brand_name = COALESCE(excluded.source_brand_name, products.source_brand_name),
                product_name_ko = COALESCE(excluded.product_name_ko, products.product_name_ko),
                regular_price = COALESCE(excluded.regular_price, products.regular_price),
                original_price = COALESCE(excluded.original_price, products.original_price),
                sale_price = excluded.sale_price,
                discount_rate = excluded.discount_rate,
                currency = COALESCE(excluded.currency, products.currency),
                shade = COALESCE(excluded.shade, products.shade),
                image_url = COALESCE(excluded.image_url, products.image_url),
                source_url = COALESCE(excluded.source_url, products.source_url),
                search_text = excluded.search_text,
                last_seen_at = excluded.last_seen_at,
                last_refreshed_at = excluded.last_refreshed_at
            """,
            (
                record_key,
                record.source,
                record.source_product_id,
                record.source_brand_name,
                record.product_name_ko,
                record.regular_price,
                record.original_price,
                record.sale_price,
                record.discount_rate,
                record.currency,
                record.shade,
                record.image_url,
                record.source_url,
                search_text,
                now,
                now,
                now,
            ),
        )
        row = self._connection.execute(
            "SELECT id FROM products WHERE record_key = ?",
            (record_key,),
        ).fetchone()
        return int(row["id"])


def _row_to_record(row: sqlite3.Row) -> ProductSourceRecord:
    return ProductSourceRecord(
        source_brand_name=row["source_brand_name"],
        product_name_ko=row["product_name_ko"],
        regular_price=row["regular_price"],
        original_price=row["original_price"],
        sale_price=row["sale_price"],
        discount_rate=row["discount_rate"],
        currency=row["currency"],
        shade=row["shade"],
        image_url=row["image_url"],
        source=row["source"],
        source_url=row["source_url"],
        source_product_id=row["source_product_id"],
    )


def _search_text(record: ProductSourceRecord) -> str:
    return _key(
        " ".join(
            value
            for value in [
                record.source_brand_name,
                record.product_name_ko,
                record.shade,
                record.source_product_id,
            ]
            if value
        )
    )


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
    text = clean_text(value)
    if text is None:
        return ""
    text = _replace_aliases(text.casefold())
    return re.sub(r"[\s\-_./|+&'():\[\],]+", "", text)


def _replace_aliases(value: str) -> str:
    replacements: Iterable[tuple[str, str]] = (
        ("브러쉬", "브러시"),
        ("brush", "브러시"),
        ("eyeliner", "아이라이너"),
        ("eye shadow", "아이섀도"),
        ("쉐딩", "섀딩"),
        ("셰딩", "섀딩"),
        ("gray", "그레이"),
        ("grey", "그레이"),
    )
    text = value
    for source, target in replacements:
        text = text.replace(source, target)
    return text
