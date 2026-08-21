"""Operator CLI (milestone 5): register pending_review match candidates from
an operator-approved CSV/JSONL file.

This tool NEVER creates a 'verified' match — it only ever calls
store.record_candidate_match(), whose SQL hard-codes review_state as
'pending_review' (there is no code path here, or in that method, that can
write 'verified'). An already-reviewed match (verified/rejected/invalid) is
never overwritten — record_candidate_match's own ON CONFLICT ... WHERE
review_state = 'pending_review' guard leaves it untouched. Final confirmation
always goes through the milestone 4 admin review API
(POST /index/matches/{match_id}/review), operated by a human.

No network I/O anywhere in this script: source_url is only checked for a
plausible http(s) shape, never fetched.

Without --apply this only validates and reports counts (dry run). Nothing is
written unless --apply is passed.
"""

from __future__ import annotations

# ruff: noqa: E402

import argparse
import asyncio
import csv
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import Settings
from app.indexing.store import SQLiteProductIndexStore

REQUIRED_FIELDS = (
    "canonical_product_id",
    "source",
    "source_product_id",
    "source_url",
    "match_method",
    "confidence",
)
OPTIONAL_NUMERIC_FIELDS = ("original_price", "sale_price")
OPTIONAL_FIELDS = ("currency", "image_url", "sold_out", "evidence_note")


@dataclass(frozen=True)
class ValidRow:
    line: int
    canonical_product_id: str
    source: str
    source_product_id: str
    source_url: str
    match_method: str
    confidence: float
    original_price: float | None = None
    sale_price: float | None = None
    currency: str | None = None
    image_url: str | None = None
    sold_out: bool | None = None
    evidence_note: str | None = None


@dataclass(frozen=True)
class RowError:
    line: int
    reason: str


@dataclass(frozen=True)
class ImportSummary:
    file: str
    format: str
    imported_by: str
    applied: bool
    strict: bool
    total_rows: int
    valid_rows: int
    created_offers: int
    offer_conflicts_skipped: int
    matches_created: int
    matches_updated_pending: int
    matches_preserved_already_reviewed: int
    unknown_canonical_product_ids: list[str] = field(default_factory=list)
    invalid_rows: list[RowError] = field(default_factory=list)
    strict_skipped_unknown_canonical: int = 0

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["invalid_rows"] = [asdict(row) for row in self.invalid_rows]
        return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Register pending_review match candidates from an operator-approved "
            "CSV/JSONL file. Never creates a verified match — dry run by default."
        )
    )
    parser.add_argument("--file", type=Path, required=True, help="CSV or JSONL input file.")
    parser.add_argument(
        "--format",
        choices=["csv", "jsonl"],
        default=None,
        help="Overrides format auto-detection from the file extension.",
    )
    parser.add_argument(
        "--imported-by",
        required=True,
        help=(
            "Who is running this import. Recorded in evidence_json as provenance — "
            "never written to product_matches.reviewed_by, which only a human clicking "
            "through the milestone 4 review API can set."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Skip rows whose canonical_product_id has no matching indexed product, instead of just warning.",
    )
    parser.add_argument(
        "--index-path",
        type=Path,
        default=None,
        help="SQLite product index path. Defaults to Settings().product_index_path.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the import. Without this flag the command only validates and reports counts.",
    )
    return parser.parse_args()


def _detect_format(path: Path, override: str | None) -> str:
    if override:
        return override
    if path.suffix.lower() == ".jsonl":
        return "jsonl"
    return "csv"


def _load_raw_rows(path: Path, file_format: str) -> list[tuple[int, dict[str, object]]]:
    rows: list[tuple[int, dict[str, object]]] = []
    if file_format == "csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for line_number, raw in enumerate(reader, start=2):  # header is line 1
                rows.append((line_number, dict(raw)))
        return rows
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            rows.append((line_number, json.loads(line)))
    return rows


def _validate_row(line: int, raw: dict[str, object]) -> ValidRow | RowError:
    for field_name in REQUIRED_FIELDS:
        value = raw.get(field_name)
        if value is None or (isinstance(value, str) and not value.strip()):
            return RowError(line=line, reason=f"missing required field: {field_name}")

    source_url = str(raw["source_url"]).strip()
    if not source_url.startswith(("http://", "https://")):
        return RowError(line=line, reason=f"source_url does not look like a URL: {source_url!r}")

    try:
        confidence = float(raw["confidence"])
    except (TypeError, ValueError):
        return RowError(line=line, reason=f"confidence is not a number: {raw['confidence']!r}")
    if not (0.0 <= confidence <= 1.0):
        return RowError(line=line, reason=f"confidence out of range [0.0, 1.0]: {confidence}")

    original_price = _optional_float(raw.get("original_price"))
    sale_price = _optional_float(raw.get("sale_price"))
    sold_out = _optional_bool(raw.get("sold_out"))

    return ValidRow(
        line=line,
        canonical_product_id=str(raw["canonical_product_id"]).strip(),
        source=str(raw["source"]).strip(),
        source_product_id=str(raw["source_product_id"]).strip(),
        source_url=source_url,
        match_method=str(raw["match_method"]).strip(),
        confidence=confidence,
        original_price=original_price,
        sale_price=sale_price,
        currency=_optional_str(raw.get("currency")),
        image_url=_optional_str(raw.get("image_url")),
        sold_out=sold_out,
        evidence_note=_optional_str(raw.get("evidence_note")),
    )


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_bool(value: object) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


async def build_import_summary(
    *,
    index_path: Path,
    file_path: Path,
    file_format: str | None,
    imported_by: str,
    strict: bool,
    apply: bool,
) -> ImportSummary:
    resolved_format = _detect_format(file_path, file_format)
    raw_rows = _load_raw_rows(file_path, resolved_format)

    valid_rows: list[ValidRow] = []
    invalid_rows: list[RowError] = []
    for line, raw in raw_rows:
        result = _validate_row(line, raw)
        if isinstance(result, RowError):
            invalid_rows.append(result)
        else:
            valid_rows.append(result)

    store = SQLiteProductIndexStore(index_path)
    created_offers = 0
    offer_conflicts_skipped = 0
    matches_created = 0
    matches_updated_pending = 0
    matches_preserved = 0
    unknown_canonical: list[str] = []
    strict_skipped_unknown = 0
    try:
        for row in valid_rows:
            known = await _canonical_product_id_is_known(store, row.canonical_product_id)
            if not known and row.canonical_product_id not in unknown_canonical:
                unknown_canonical.append(row.canonical_product_id)
            if not known and strict:
                strict_skipped_unknown += 1
                continue

            if not apply:
                continue

            offer_already_existed = await _offer_exists(
                store, row.source, row.source_product_id, row.canonical_product_id
            )
            offer_id = await store.ensure_offer(
                canonical_product_id=row.canonical_product_id,
                source=row.source,
                source_product_id=row.source_product_id,
                source_url=row.source_url,
                original_price=row.original_price,
                sale_price=row.sale_price,
                currency=row.currency,
                image_url=row.image_url,
                sold_out=row.sold_out,
            )
            if offer_id is None:
                offer_conflicts_skipped += 1
                continue
            if not offer_already_existed:
                created_offers += 1

            match_id = f"match:{row.canonical_product_id}:{row.source}:{row.source_product_id}"
            existing_match = await store.get_match_detail(match_id)
            existing_state = existing_match["review_state"] if existing_match else None

            evidence: list[dict[str, object]] = [
                {
                    "type": "operator_import_source",
                    "value": f"{imported_by}:{file_path.name}",
                }
            ]
            if row.evidence_note:
                evidence.append({"type": "operator_note", "value": row.evidence_note})

            await store.record_candidate_match(
                canonical_product_id=row.canonical_product_id,
                offer_id=offer_id,
                confidence=row.confidence,
                match_method=row.match_method,
                evidence=evidence,
            )

            if existing_state is None:
                matches_created += 1
            elif existing_state == "pending_review":
                matches_updated_pending += 1
            else:
                matches_preserved += 1
    finally:
        await store.close()

    return ImportSummary(
        file=str(file_path),
        format=resolved_format,
        imported_by=imported_by,
        applied=apply,
        strict=strict,
        total_rows=len(raw_rows),
        valid_rows=len(valid_rows),
        created_offers=created_offers,
        offer_conflicts_skipped=offer_conflicts_skipped,
        matches_created=matches_created,
        matches_updated_pending=matches_updated_pending,
        matches_preserved_already_reviewed=matches_preserved,
        unknown_canonical_product_ids=unknown_canonical,
        invalid_rows=invalid_rows,
        strict_skipped_unknown_canonical=strict_skipped_unknown,
    )


async def _canonical_product_id_is_known(
    store: SQLiteProductIndexStore, canonical_product_id: str
) -> bool:
    records = await store.search(canonical_product_id, 1)
    if any(record.canonical_product_id == canonical_product_id for record in records):
        return True
    # search() is keyword-oriented and may miss an exact id lookup; fall back
    # to a direct check via all_products is too expensive for large indexes,
    # so this is a best-effort signal only (see plan: warn, don't block by
    # default). A store-level exact lookup can be added later if this proves
    # too noisy in practice.
    return False


async def _offer_exists(
    store: SQLiteProductIndexStore,
    source: str,
    source_product_id: str,
    canonical_product_id: str,
) -> bool:
    existing = await store.get_offers([canonical_product_id])
    return any(
        offer.source == source and offer.source_product_id == source_product_id
        for offer in existing.get(canonical_product_id, [])
    )


async def main() -> int:
    args = parse_args()
    settings = Settings()
    summary = await build_import_summary(
        index_path=args.index_path or settings.product_index_path,
        file_path=args.file,
        file_format=args.format,
        imported_by=args.imported_by,
        strict=args.strict,
        apply=args.apply,
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
