"""Background Turso backup/restore for the product index.

Deliberately decoupled from the live local index connection used by
SearchService: connecting to Turso is a blocking network call that has been
observed (from Render's network) to take minutes with no reliable way to
bound it from Python (see _libsql_compat.py). Doing that inline during app
startup blocked the whole app from serving traffic; doing it against the
live connection risks the file-corruption Turso's docs warn about when a
sync is in flight.

Instead this module always operates through a *separate* pure-remote
connection (SQLiteProductIndexStore.for_remote — no local file at all) and a
short-lived local connection of its own, run entirely inside
asyncio.to_thread / a background asyncio task that is created (never
awaited) from the app lifespan. However long Turso takes, it can never
delay startup or a request — worst case, a given restore/backup cycle is
just late.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.core.config import Settings
from app.indexing.store import SQLiteProductIndexStore

logger = logging.getLogger(__name__)

_RESTORE_QUERY_KEY = "turso-restore"
_BACKUP_QUERY_KEY = "turso-backup"
_DEFAULT_INTERVAL_SECONDS = 1800.0


async def restore_from_turso(db_path: Path, settings: Settings) -> int:
    """Pulls whatever products Turso already has into the local index. Meant
    to run once, early, after a fresh/empty boot — but never blocks it."""
    if not settings.turso_database_url:
        return 0
    try:
        remote = await asyncio.to_thread(
            SQLiteProductIndexStore.for_remote,
            settings.turso_database_url,
            settings.turso_auth_token,
        )
    except Exception:
        logger.warning("Turso restore: could not connect", exc_info=True)
        return 0
    try:
        records = await remote.all_products()
    except Exception:
        logger.warning("Turso restore: could not read products", exc_info=True)
        return 0
    finally:
        await asyncio.to_thread(remote.close)
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
        remote = await asyncio.to_thread(
            SQLiteProductIndexStore.for_remote,
            settings.turso_database_url,
            settings.turso_auth_token,
        )
    except Exception:
        logger.warning("Turso backup: could not connect", exc_info=True)
        return 0
    try:
        await remote.upsert_search_results(_BACKUP_QUERY_KEY, records)
    except Exception:
        logger.warning("Turso backup: could not write products", exc_info=True)
        return 0
    finally:
        await asyncio.to_thread(remote.close)
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
