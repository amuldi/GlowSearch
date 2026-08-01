"""sqlite3.Row-compatible wrapper around the `libsql` driver.

`libsql.connect()` is a near drop-in replacement for `sqlite3.connect()`
(same file format, same FTS5 support). The one real gap is `row_factory` —
libsql cursors only return plain tuples, but the rest of the store (60+
call sites) indexes rows by column name (`row["col"]`). This module closes
that gap without touching any of those call sites.

Deliberately local-file-only. An earlier version of this module also
supported connecting with Turso's `sync_url` (embedded replicas), but that
was removed after it caused a real production outage: libsql's blocking
network calls do not release the GIL, so even a background-thread sync
attempt froze the entire process, health checks included, for as long as
Turso took to respond. Turso backup/restore now lives in
app/indexing/turso_http.py instead, built on httpx (a well-behaved async
library) rather than this driver.
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

    def __init__(self, database: str):
        self._connection = libsql.connect(database)

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> _CursorProxy:
        return _CursorProxy(self._connection.execute(sql, params))

    def commit(self) -> None:
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()
