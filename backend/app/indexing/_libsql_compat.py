"""sqlite3.Row-compatible wrapper around the `libsql` driver.

`libsql.connect()` is a near drop-in replacement for `sqlite3.connect()` (same
file format, same FTS5 support) that also supports Turso's embedded-replica
mode: a local file kept in sync with a remote durable database via
`sync_url`/`auth_token`. The one real gap is `row_factory` — libsql cursors
only return plain tuples, but the rest of the store (60+ call sites) indexes
rows by column name (`row["col"]`). This module closes that gap without
touching any of those call sites.

Per Turso's docs (docs.turso.tech/features/embedded-replicas/introduction),
when `sync_url` is set, writes go straight to the remote primary and are
reflected back to the local replica automatically ("read your own writes") —
so there is nothing to push after `commit()`. `sync()` is only needed to
*pull* the remote state down into a fresh/empty local replica, which we do
once on connect (matters after a Render restart wipes the local disk) and
optionally on an interval via `sync_interval`.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any

import libsql

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT_SECONDS = 15.0


class Row:
    __slots__ = ("_columns", "_values")

    def __init__(self, columns: tuple[str, ...], values: tuple[Any, ...]):
        self._columns = columns
        self._values = values

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, str):
            return self._values[self._columns.index(key)]
        return self._values[key]

    def keys(self) -> list[str]:
        return list(self._columns)

    def __repr__(self) -> str:
        return f"Row({dict(zip(self._columns, self._values))!r})"


class _CursorProxy:
    def __init__(self, cursor: Any):
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def _columns(self) -> tuple[str, ...]:
        description = self._cursor.description
        return tuple(column[0] for column in description) if description else ()

    def fetchall(self) -> list[Row]:
        columns = self._columns()
        return [Row(columns, row) for row in self._cursor.fetchall()]

    def fetchone(self) -> Row | None:
        row = self._cursor.fetchone()
        if row is None:
            return None
        return Row(self._columns(), row)


class LibsqlConnection:
    """Wraps a libsql connection so it behaves like sqlite3.connect(..., row_factory=sqlite3.Row)."""

    def __init__(
        self,
        database: str,
        *,
        sync_url: str | None = None,
        auth_token: str | None = None,
        sync_interval_seconds: float | None = None,
        remote_only: bool = False,
    ):
        if remote_only:
            # Pure HTTP connection to Turso Cloud, no local file at all — used
            # by app/indexing/turso_backup.py for background backup/restore,
            # which must never touch (or block behind) the live local index
            # connection. Callers are responsible for running this off the
            # event loop (e.g. via asyncio.to_thread), since connecting here
            # is a blocking network call with no reliable way to bound it
            # from Python (see _try_connect_with_sync's docstring).
            self._connection = libsql.connect(database=database, auth_token=auth_token or "")
            return
        connection = None
        if sync_url:
            connection = self._try_connect_with_sync(
                database,
                sync_url=sync_url,
                auth_token=auth_token or "",
                sync_interval_seconds=sync_interval_seconds,
            )
        self._connection = connection or libsql.connect(database)

    @staticmethod
    def _try_connect_with_sync(
        database: str,
        *,
        sync_url: str,
        auth_token: str,
        sync_interval_seconds: float | None,
    ) -> Any | None:
        """Connects with Turso sync in a worker thread with a best-effort
        timeout, so a failed/unreachable Turso endpoint degrades to a plain
        local connection instead of crashing (or, previously, hanging) app
        startup. Note: libsql's connect+sync is a blocking Rust call that does
        not reliably yield the GIL, so `future.result(timeout=...)` can't
        actually preempt it early — in practice a bad sync_url still takes as
        long as the OS-level TCP timeout (~75s) to fail. This still matters
        because it converts that eventual failure into a graceful fallback
        instead of an uncaught exception."""

        def connect_and_sync() -> Any:
            kwargs: dict[str, Any] = {"sync_url": sync_url, "auth_token": auth_token}
            if sync_interval_seconds:
                kwargs["sync_interval"] = sync_interval_seconds
            conn = libsql.connect(database, **kwargs)
            conn.sync()
            return conn

        # Deliberately not a context manager: ThreadPoolExecutor.__exit__ calls
        # shutdown(wait=True), which would block on exactly the hung call
        # we're trying to time out. If the future never completes, this
        # executor (and its one worker thread) is simply abandoned.
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(connect_and_sync)
        try:
            return future.result(timeout=_CONNECT_TIMEOUT_SECONDS)
        except FutureTimeoutError:
            logger.warning(
                "Turso sync timed out after %ss; falling back to local-only index",
                _CONNECT_TIMEOUT_SECONDS,
            )
            return None
        except Exception:
            logger.warning("Turso connect/sync failed; falling back to local-only index", exc_info=True)
            return None
        finally:
            executor.shutdown(wait=False)

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> _CursorProxy:
        return _CursorProxy(self._connection.execute(sql, params))

    def commit(self) -> None:
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()
