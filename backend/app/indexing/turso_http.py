"""Turso backup/restore over plain HTTPS (Hrana v2 pipeline API).

Deliberately does NOT use the `libsql` package: its blocking network calls
do not release the GIL, so any use of it — even wrapped in
asyncio.to_thread — freezes the entire process (confirmed live in
production; see git history for app/indexing/turso_backup.py, now unused).

httpx.AsyncClient is a well-behaved async library that integrates properly
with the event loop: a slow/unreachable Turso endpoint only delays the
coroutine awaiting it, bounded by an explicit, honored `timeout`. Nothing
else — other requests, health checks — is ever affected.

This module keeps a deliberately simple, flat mirror of the local products
table (record_key as primary key, no FTS5, no query_products mapping): the
goal is only "don't lose already-discovered products across a restart", not
full parity. Restore feeds pulled records back through the local store's
normal upsert_search_results, which already handles FTS5/associations.

API reference: https://docs.turso.tech/sdk/http/reference
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings
from app.indexing.store import (
    SQLiteProductIndexStore,
    _options_from_json,
    _options_json,
    _record_key,
)
from app.models.product import ProductSourceRecord

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 20.0
_BATCH_SIZE = 200
_RESTORE_QUERY_KEY = "turso-restore"
_DEFAULT_INTERVAL_SECONDS = 1800.0

_COLUMNS = [
    "record_key",
    "canonical_product_id",
    "source",
    "source_product_id",
    "category",
    "source_brand_name",
    "source_brand_name_en",
    "product_name_ko",
    "product_name_en",
    "product_name_display_ko",
    "product_name_display_en",
    "regular_price",
    "original_price",
    "sale_price",
    "discount_rate",
    "rating",
    "review_count",
    "currency",
    "shade",
    "image_url",
    "description",
    "options_json",
    "search_keywords_json",
    "sold_out",
    "source_url",
    "updated_at",
]

# A dedicated, deliberately unique table name: earlier attempts tonight
# (the now-deleted libsql-based turso_backup.py, and manual debugging via
# `turso db shell`) may have left a `products` table on the remote database
# with a different, incompatible schema. CREATE TABLE IF NOT EXISTS silently
# no-ops against a pre-existing table, so reusing that name would appear to
# work right up until a query referenced a column that isn't actually there
# (which is exactly what happened - "no such column: updated_at"). Rather
# than guess at or DROP whatever is already on the database, just don't
# collide with it.
_TABLE_NAME = "glowsearch_products_backup"

_CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {_TABLE_NAME} (
    {", ".join(f"{col} TEXT" if col != "record_key" else f"{col} TEXT PRIMARY KEY" for col in _COLUMNS)}
)
"""

_UPSERT_SQL = f"""
INSERT INTO {_TABLE_NAME}({", ".join(_COLUMNS)})
VALUES({", ".join("?" for _ in _COLUMNS)})
ON CONFLICT(record_key) DO UPDATE SET
{", ".join(f"{col} = excluded.{col}" for col in _COLUMNS if col != "record_key")}
"""


def _http_base_url(turso_database_url: str) -> str:
    if turso_database_url.startswith("libsql://"):
        return "https://" + turso_database_url[len("libsql://") :]
    if turso_database_url.startswith("turso://"):
        return "https://" + turso_database_url[len("turso://") :]
    return turso_database_url


def _encode_arg(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": str(int(value))}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    return {"type": "text", "value": str(value)}


def _decode_value(typed: dict[str, Any] | None) -> Any:
    if typed is None:
        return None
    kind = typed.get("type")
    value = typed.get("value")
    if kind == "null" or value is None:
        return None
    if kind == "integer":
        return int(value)
    if kind == "float":
        return float(value)
    return value


def _record_to_args(record: ProductSourceRecord) -> list[dict[str, Any]]:
    values: dict[str, Any] = {
        "record_key": _record_key(record),
        "canonical_product_id": record.canonical_product_id,
        "source": record.source,
        "source_product_id": record.source_product_id,
        "category": record.category,
        "source_brand_name": record.source_brand_name,
        "source_brand_name_en": record.source_brand_name_en,
        "product_name_ko": record.product_name_ko,
        "product_name_en": record.product_name_en,
        "product_name_display_ko": record.product_name_display_ko,
        "product_name_display_en": record.product_name_display_en,
        "regular_price": record.regular_price,
        "original_price": record.original_price,
        "sale_price": record.sale_price,
        "discount_rate": record.discount_rate,
        "rating": record.rating,
        "review_count": record.review_count,
        "currency": record.currency,
        "shade": record.shade,
        "image_url": record.image_url,
        "description": record.description,
        "options_json": _options_json(record.options),
        "search_keywords_json": _options_json(record.search_keywords),
        "sold_out": record.sold_out,
        "source_url": record.source_url,
        "updated_at": record.updated_at,
    }
    return [_encode_arg(values[col]) for col in _COLUMNS]


def _row_to_record(cols: list[dict[str, Any]], row: list[dict[str, Any]]) -> ProductSourceRecord:
    values = {col["name"]: _decode_value(cell) for col, cell in zip(cols, row, strict=True)}
    return ProductSourceRecord(
        canonical_product_id=values.get("canonical_product_id"),
        source=values.get("source") or "oliveyoung",
        source_product_id=values.get("source_product_id"),
        category=values.get("category"),
        source_brand_name=values.get("source_brand_name"),
        source_brand_name_en=values.get("source_brand_name_en"),
        product_name_ko=values.get("product_name_ko"),
        product_name_en=values.get("product_name_en"),
        product_name_display_ko=values.get("product_name_display_ko"),
        product_name_display_en=values.get("product_name_display_en"),
        regular_price=values.get("regular_price"),
        original_price=values.get("original_price"),
        sale_price=values.get("sale_price"),
        discount_rate=values.get("discount_rate"),
        rating=values.get("rating"),
        review_count=values.get("review_count"),
        currency=values.get("currency") or "KRW",
        shade=values.get("shade"),
        image_url=values.get("image_url"),
        description=values.get("description"),
        options=_options_from_json(values.get("options_json")),
        search_keywords=_options_from_json(values.get("search_keywords_json")),
        sold_out=bool(values["sold_out"]) if values.get("sold_out") is not None else None,
        source_url=values.get("source_url"),
        updated_at=values.get("updated_at"),
    )


async def _pipeline(
    client: httpx.AsyncClient,
    base_url: str,
    auth_token: str,
    requests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    response = await client.post(
        f"{base_url}/v2/pipeline",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"requests": [*requests, {"type": "close"}]},
        timeout=_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    results = payload.get("results", [])
    for result in results:
        if result.get("type") == "error":
            error = result.get("error", {})
            raise RuntimeError(f"Turso error: {error.get('message', error)}")
    return results


async def backup_to_turso(db_path: Path, settings: Settings) -> int:
    if not settings.turso_database_url:
        return 0
    local = SQLiteProductIndexStore(db_path)
    try:
        records = await local.all_products()
    finally:
        await local.close()
    if not records:
        return 0

    base_url = _http_base_url(settings.turso_database_url)
    auth_token = settings.turso_auth_token or ""
    async with httpx.AsyncClient() as client:
        try:
            await _pipeline(
                client, base_url, auth_token, [{"type": "execute", "stmt": {"sql": _CREATE_TABLE_SQL}}]
            )
            for start in range(0, len(records), _BATCH_SIZE):
                batch = records[start : start + _BATCH_SIZE]
                requests = [
                    {
                        "type": "execute",
                        "stmt": {"sql": _UPSERT_SQL, "args": _record_to_args(record)},
                    }
                    for record in batch
                ]
                await _pipeline(client, base_url, auth_token, requests)
        except Exception:
            logger.warning("Turso backup: failed", exc_info=True)
            return 0
    logger.info("Turso backup: pushed %d products", len(records))
    return len(records)


async def restore_from_turso(db_path: Path, settings: Settings) -> int:
    if not settings.turso_database_url:
        return 0
    base_url = _http_base_url(settings.turso_database_url)
    auth_token = settings.turso_auth_token or ""
    async with httpx.AsyncClient() as client:
        try:
            await _pipeline(
                client, base_url, auth_token, [{"type": "execute", "stmt": {"sql": _CREATE_TABLE_SQL}}]
            )
            results = await _pipeline(
                client,
                base_url,
                auth_token,
                [
                    {
                        "type": "execute",
                        "stmt": {"sql": f"SELECT {', '.join(_COLUMNS)} FROM {_TABLE_NAME}"},
                    }
                ],
            )
        except Exception:
            logger.warning("Turso restore: failed", exc_info=True)
            return 0

    execute_result = results[0]["response"]["result"]
    cols = execute_result.get("cols", [])
    rows = execute_result.get("rows", [])
    if not rows:
        return 0
    records = [_row_to_record(cols, row) for row in rows]

    local = SQLiteProductIndexStore(db_path)
    try:
        await local.upsert_search_results(_RESTORE_QUERY_KEY, records)
    finally:
        await local.close()
    logger.info("Turso restore: pulled %d products into local index", len(records))
    return len(records)


async def run_periodic(db_path: Path, settings: Settings) -> None:
    """Restore once, then back up on an interval, for the life of the app.
    Intended to be launched with asyncio.create_task and never awaited."""
    if not settings.turso_database_url:
        return
    interval = settings.turso_sync_interval_seconds or _DEFAULT_INTERVAL_SECONDS
    try:
        await restore_from_turso(db_path, settings)
    except Exception:
        logger.warning("Turso restore cycle failed", exc_info=True)
    while True:
        try:
            await asyncio.sleep(interval)
            await backup_to_turso(db_path, settings)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Turso backup cycle failed", exc_info=True)
