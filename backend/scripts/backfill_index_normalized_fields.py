from __future__ import annotations

# ruff: noqa: E402

import argparse
import asyncio
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import Settings
from app.indexing.store import _record_key
from app.indexing.store import _search_terms
from app.indexing.store import _search_text
from app.indexing.store import SQLiteProductIndexStore
from app.models.product import ProductSourceRecord
from app.normalizer.brand import BrandResolver
from app.normalizer.product import ProductNormalizer

NORMALIZED_COLUMNS = (
    "source_brand_name",
    "source_brand_name_en",
    "product_name_en",
    "product_name_display_ko",
    "product_name_display_en",
    "source_url",
    "image_url",
    "currency",
)


@dataclass(frozen=True)
class BackfillSample:
    source: str
    source_product_id: str | None
    source_url: str | None
    changes: dict[str, dict[str, str | None]]


@dataclass(frozen=True)
class BackfillSummary:
    index_path: str
    scanned: int
    changed: int
    applied: bool
    changed_fields: dict[str, int]
    samples: list[BackfillSample]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["samples"] = [asdict(sample) for sample in self.samples]
        return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill normalized brand/display fields in the SQLite product index after normalizer or registry updates."
    )
    parser.add_argument(
        "--index-path",
        type=Path,
        default=None,
        help="SQLite product index path. Defaults to Settings().product_index_path.",
    )
    parser.add_argument(
        "--registry-path",
        type=Path,
        default=None,
        help="brand_registry.json path. Defaults to Settings().brand_registry_path.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Base URL used for relative source/image URLs. Defaults to Settings().oliveyoung_base_url.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of recent indexed products to scan. Defaults to all products.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=12,
        help="Maximum number of changed row samples to include in output.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates. Without this flag the command only reports a dry run.",
    )
    parser.add_argument(
        "--recompute-display-names",
        action="store_true",
        help=(
            "Ignore currently stored display names and recompute them from raw source product names. "
            "Use after display-name cleanup rule changes."
        ),
    )
    parser.add_argument(
        "--source-prefix",
        action="append",
        default=[],
        help=(
            "Only scan records whose source matches this prefix. Can be repeated. "
            "Useful for recomputing retail source display names without touching verified official records."
        ),
    )
    return parser.parse_args()


async def build_backfill_summary(
    *,
    index_path: Path,
    registry_path: Path,
    base_url: str,
    limit: int | None,
    sample_limit: int,
    apply: bool,
    recompute_display_names: bool = False,
    source_prefixes: list[str] | None = None,
) -> BackfillSummary:
    store = SQLiteProductIndexStore(index_path)
    normalizer = ProductNormalizer(BrandResolver(registry_path), base_url=base_url)
    try:
        records = await store.all_products(limit=limit)
        changes: list[tuple[ProductSourceRecord, ProductSourceRecord, dict[str, dict[str, str | None]]]] = []
        changed_fields: dict[str, int] = {}
        allowed_source_prefixes = tuple(prefix for prefix in source_prefixes or [] if prefix)
        scanned = 0
        for record in records:
            if allowed_source_prefixes and not record.source.startswith(allowed_source_prefixes):
                continue
            scanned += 1
            normalized = _normalized_source_record(
                normalizer,
                record,
                recompute_display_names=recompute_display_names,
            )
            row_changes = _field_changes(record, normalized)
            if not row_changes:
                continue
            changes.append((record, normalized, row_changes))
            for field in row_changes:
                changed_fields[field] = changed_fields.get(field, 0) + 1
        if apply and changes:
            _apply_changes(index_path, [(record, normalized) for record, normalized, _row_changes in changes])
        samples = [
            BackfillSample(
                source=record.source,
                source_product_id=record.source_product_id,
                source_url=record.source_url,
                changes=row_changes,
            )
            for record, _normalized, row_changes in changes[: max(sample_limit, 0)]
        ]
        return BackfillSummary(
            index_path=str(index_path),
            scanned=scanned,
            changed=len(changes),
            applied=apply,
            changed_fields=dict(sorted(changed_fields.items())),
            samples=samples,
        )
    finally:
        normalizer.close()
        await store.close()


def _normalized_source_record(
    normalizer: ProductNormalizer,
    record: ProductSourceRecord,
    *,
    recompute_display_names: bool = False,
) -> ProductSourceRecord:
    normalizer_input = (
        record.model_copy(update={"product_name_display_ko": None, "product_name_display_en": None})
        if recompute_display_names
        else record
    )
    result = normalizer.normalize(normalizer_input)
    return ProductSourceRecord(
        canonical_product_id=result.canonical_product_id,
        category=result.category,
        source_brand_name=result.brand_ko,
        source_brand_name_en=result.brand_en,
        product_name_ko=result.product_name_ko,
        product_name_en=result.product_name_en,
        product_name_display_ko=result.product_name_display_ko,
        product_name_display_en=result.product_name_display_en,
        regular_price=result.price,
        original_price=result.original_price,
        sale_price=result.sale_price,
        discount_rate=result.discount_rate,
        rating=result.rating,
        review_count=result.review_count,
        currency=result.currency,
        shade=result.shade,
        image_url=result.image_url,
        description=result.description,
        options=result.options,
        search_keywords=result.search_keywords,
        sold_out=result.sold_out,
        source=result.source,
        source_url=result.source_url,
        source_product_id=result.source_product_id,
        updated_at=result.updated_at,
    )


def _field_changes(
    record: ProductSourceRecord,
    normalized: ProductSourceRecord,
) -> dict[str, dict[str, str | None]]:
    changes: dict[str, dict[str, str | None]] = {}
    for field in NORMALIZED_COLUMNS:
        before = getattr(record, field)
        after = getattr(normalized, field)
        if before == after:
            continue
        if after is None:
            continue
        changes[field] = {"before": _string_or_none(before), "after": _string_or_none(after)}
    return changes


def _apply_changes(
    index_path: Path,
    records: list[tuple[ProductSourceRecord, ProductSourceRecord]],
) -> None:
    connection = sqlite3.connect(index_path)
    try:
        for original, normalized in records:
            connection.execute(
                """
                UPDATE products
                SET
                    source_brand_name = ?,
                    source_brand_name_en = ?,
                    product_name_en = ?,
                    product_name_display_ko = ?,
                    product_name_display_en = ?,
                    source_url = ?,
                    image_url = ?,
                    currency = ?,
                    search_text = ?
                WHERE record_key = ?
                """,
                (
                    normalized.source_brand_name,
                    normalized.source_brand_name_en,
                    normalized.product_name_en,
                    normalized.product_name_display_ko,
                    normalized.product_name_display_en,
                    normalized.source_url,
                    normalized.image_url,
                    normalized.currency,
                    _search_text(normalized),
                    _record_key(original),
                ),
            )
            _update_fts(connection, original, normalized)
        connection.commit()
    finally:
        connection.close()


def _update_fts(
    connection: sqlite3.Connection,
    original: ProductSourceRecord,
    normalized: ProductSourceRecord,
) -> None:
    try:
        record_key = _record_key(original)
        connection.execute("DELETE FROM products_fts WHERE record_key = ?", (record_key,))
        connection.execute(
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
                    for value in [normalized.source_brand_name, normalized.source_brand_name_en]
                    if value
                ),
                " ".join(
                    value
                    for value in [
                        normalized.product_name_ko,
                        normalized.product_name_en,
                        normalized.product_name_display_ko,
                        normalized.product_name_display_en,
                    ]
                    if value
                ),
                normalized.category,
                normalized.description,
                normalized.shade,
                " ".join(normalized.options or []),
                "",
                _search_terms(normalized),
            ),
        )
    except sqlite3.OperationalError:
        return


def _string_or_none(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)


async def main() -> int:
    args = parse_args()
    settings = Settings()
    summary = await build_backfill_summary(
        index_path=args.index_path or settings.product_index_path,
        registry_path=args.registry_path or settings.brand_registry_path,
        base_url=args.base_url or settings.oliveyoung_base_url,
        limit=args.limit,
        sample_limit=args.sample_limit,
        apply=args.apply,
        recompute_display_names=args.recompute_display_names,
        source_prefixes=args.source_prefix,
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
