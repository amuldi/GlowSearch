"""One-time migration (milestone 3): create `product_matches` rows for the
verified relationships that already exist today, before any automatic
matcher runs.

Two sources, both idempotent (safe to re-run):

1. Every `product_offers` row (milestone 2) already originates from a
   canonical_product_id-bearing record, which today only ever comes from
   verified_products.json — so each becomes a 'verified' match with
   match_method='verified_catalog'.
2. Every `editor_confirmed_mappings` row that has canonical_product_id,
   source_url, and source_product_id all populated represents a human's
   explicit confirm action — each becomes a 'verified' match with
   match_method='editor_confirmed'. Rows missing any of those fields are
   skipped (no identifier is fabricated for them).

Without --apply this only reports counts (dry run). Nothing is written
unless --apply is passed.
"""

from __future__ import annotations

# ruff: noqa: E402

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import Settings
from app.indexing.store import SQLiteProductIndexStore


@dataclass(frozen=True)
class BackfillMatchesSummary:
    index_path: str
    applied: bool
    actor: str
    eligible_offers: int
    eligible_editor_mappings: int
    verified_catalog_matches_processed: int | None
    editor_confirmed_matches_processed: int | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill product_matches from existing verified relationships "
            "(product_offers + editor_confirmed_mappings). Dry run by default."
        )
    )
    parser.add_argument(
        "--index-path",
        type=Path,
        default=None,
        help="SQLite product index path. Defaults to Settings().product_index_path.",
    )
    parser.add_argument(
        "--actor",
        default="migration_script",
        help=(
            "Value recorded as reviewed_by for every backfilled match — this migration "
            "stands in for a human curator's prior approval of the source data, so the "
            "actor name should say so (e.g. 'verified_catalog_migration_2026-08-21')."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the backfill. Without this flag the command only reports counts.",
    )
    return parser.parse_args()


async def build_summary(*, index_path: Path, actor: str, apply: bool) -> BackfillMatchesSummary:
    store = SQLiteProductIndexStore(index_path)
    try:
        stats = await store.stats()
        eligible_offers = int(stats.get("offer_count") or 0)
        eligible_editor_mappings = await _count_eligible_editor_mappings(store)
        verified_processed: int | None = None
        editor_processed: int | None = None
        if apply:
            verified_processed = await store.backfill_verified_catalog_matches(actor=actor)
            editor_processed = await store.backfill_editor_confirmed_matches(actor=actor)
        return BackfillMatchesSummary(
            index_path=str(index_path),
            applied=apply,
            actor=actor,
            eligible_offers=eligible_offers,
            eligible_editor_mappings=eligible_editor_mappings,
            verified_catalog_matches_processed=verified_processed,
            editor_confirmed_matches_processed=editor_processed,
        )
    finally:
        await store.close()


async def _count_eligible_editor_mappings(store: SQLiteProductIndexStore) -> int:
    # Read-only dry-run preview using the store's own connection/lock, mirroring
    # the WHERE clause backfill_editor_confirmed_matches uses to select rows.
    async with store._lock:  # noqa: SLF001 - script-only, read-only preview query
        row = store._connection.execute(  # noqa: SLF001
            """
            SELECT COUNT(*) AS count FROM editor_confirmed_mappings
            WHERE canonical_product_id IS NOT NULL AND canonical_product_id != ''
              AND source_url IS NOT NULL AND source_url != ''
              AND source_product_id IS NOT NULL AND source_product_id != ''
            """
        ).fetchone()
    return int(row["count"] or 0)


async def main() -> int:
    args = parse_args()
    settings = Settings()
    summary = await build_summary(
        index_path=args.index_path or settings.product_index_path,
        actor=args.actor,
        apply=args.apply,
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
