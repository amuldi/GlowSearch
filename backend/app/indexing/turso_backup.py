"""Background Turso backup/restore for the product index.

Deliberately decoupled from the live local index connection used by
SearchService: connecting to Turso is a blocking network call that has been
observed (from Render's network) to take minutes with no reliable way to
bound it from Python (see _libsql_compat.py). Doing that inline during app
startup blocked the whole app from serving traffic; doing it against the
live connection risks the file-corruption Turso's docs warn about when a
sync is in flight.

Correctness note learned the hard way: it is not enough to thread just the
*connection* step. SQLiteProductIndexStore's methods (all_products,
upsert_search_results) are async only for their asyncio.Lock — the actual
`self._connection.execute(...)` calls inside them are synchronous, and for a
`for_remote()` store each one is a blocking HTTP round-trip to Turso. Awaiting
them directly on the app's event loop (with WEB_CONCURRENCY=1 in production)
blocked every other request — including /health — until Render's own health
check killed and restarted the instance. So every read/write against a
remote store must happen inside the *same* asyncio.to_thread call as the
connect, via a synchronous helper that drives its own throwaway event loop
with asyncio.run(). Nothing here ever touches the live local connection that
SearchService serves requests from.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.core.config import Settings
from app.indexing.store import SQLiteProductIndexStore
from app.models.product import ProductSourceRecord

logger = logging.getLogger(__name__)

_RESTORE_QUERY_KEY = "turso-restore"
_BACKUP_QUERY_KEY = "turso-backup"
_DEFAULT_INTERVAL_SECONDS = 1800.0


def _fetch_all_from_remote(url: str, auth_token: str | None) -> list[ProductSourceRecord]:
    """Synchronous, self-contained: connect, read, close. Must only ever be
    called via asyncio.to_thread — never awaited directly."""

    async def _run() -> list[ProductSourceRecord]:
        remote = SQLiteProductIndexStore.for_remote(url, auth_token)
        try:
            return await remote.all_products()
        finally:
            await remote.close()

    return asyncio.run(_run())


def _push_all_to_remote(
    url: str,
    auth_token: str | None,
    records: list[ProductSourceRecord],
) -> None:
    """Synchronous, self-contained: connect, write, close."""

    async def _run() -> None:
        remote = SQLiteProductIndexStore.for_remote(url, auth_token)
        try:
            await remote.upsert_search_results(_BACKUP_QUERY_KEY, records)
        finally:
            await remote.close()

    asyncio.run(_run())


async def restore_from_turso(db_path: Path, settings: Settings) -> int:
    """Pulls whatever products Turso already has into the local index. Meant
    to run once, early, after a fresh/empty boot — but never blocks it."""
    if not settings.turso_database_url:
        return 0
    try:
        records = await asyncio.to_thread(
            _fetch_all_from_remote, settings.turso_database_url, settings.turso_auth_token
        )
    except Exception:
        logger.warning("Turso restore: could not read from remote", exc_info=True)
        return 0
    if not records:
        return 0
    local = SQLiteProductIndexStore(db_path)
    try:
        await local.upsert_search_results(_RESTORE_QUERY_KEY, records)
    finally:
        await local.close()
    logger.info("Turso restore: pulled %d products into local index", len(records))
    return len(records)


async def backup_to_turso(db_path: Path, settings: Settings) -> int:
    """Pushes the current local product set up to Turso."""
    if not settings.turso_database_url:
        return 0
    local = SQLiteProductIndexStore(db_path)
    try:
        records = await local.all_products()
    finally:
        await local.close()
    if not records:
        return 0
    try:
        await asyncio.to_thread(
            _push_all_to_remote, settings.turso_database_url, settings.turso_auth_token, records
        )
    except Exception:
        logger.warning("Turso backup: could not write to remote", exc_info=True)
        return 0
    logger.info("Turso backup: pushed %d products", len(records))
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
