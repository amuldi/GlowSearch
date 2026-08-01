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

from typing import Any

import libsql


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
    ):
        kwargs: dict[str, Any] = {}
        if sync_url:
            kwargs["sync_url"] = sync_url
            kwargs["auth_token"] = auth_token or ""
            if sync_interval_seconds:
                kwargs["sync_interval"] = sync_interval_seconds
        self._connection = libsql.connect(database, **kwargs)
        if sync_url:
            self._connection.sync()

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> _CursorProxy:
        return _CursorProxy(self._connection.execute(sql, params))

    def commit(self) -> None:
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()
