from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from app.indexing.store import SQLiteProductIndexStore
from app.models.product import ProductSourceRecord

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "import_pending_matches.py"


def _load_import_module():
    spec = importlib.util.spec_from_file_location("import_pending_matches_script", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def _seed_known_canonical(store: SQLiteProductIndexStore, canonical_product_id: str) -> None:
    await store.upsert_search_results(
        "테스트 상품",
        [
            ProductSourceRecord(
                canonical_product_id=canonical_product_id,
                source_brand_name="브랜드",
                product_name_ko="테스트 상품",
                source="oliveyoung",
                source_product_id="oy-known",
                source_url="https://oy.example/known",
            )
        ],
    )


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    import csv

    fieldnames = [
        "canonical_product_id",
        "source",
        "source_product_id",
        "source_url",
        "match_method",
        "confidence",
        "original_price",
        "sale_price",
        "currency",
        "image_url",
        "sold_out",
        "evidence_note",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    import json

    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


_BASE_ROW = {
    "canonical_product_id": "verified-import-1",
    "source": "musinsa",
    "source_product_id": "ms-1",
    "source_url": "https://musinsa.example/1",
    "match_method": "operator_import",
    "confidence": "0.8",
}


@pytest.mark.asyncio
async def test_dry_run_reports_counts_without_writing(tmp_path) -> None:
    module = _load_import_module()
    index_path = tmp_path / "index.sqlite3"
    store = SQLiteProductIndexStore(index_path)
    await _seed_known_canonical(store, "verified-import-1")
    await store.close()

    csv_path = tmp_path / "rows.csv"
    _write_csv(csv_path, [_BASE_ROW])

    summary = await module.build_import_summary(
        index_path=index_path,
        file_path=csv_path,
        file_format=None,
        imported_by="alice",
        strict=False,
        apply=False,
    )

    assert summary.applied is False
    assert summary.total_rows == 1
    assert summary.valid_rows == 1
    assert summary.matches_created == 0

    store2 = SQLiteProductIndexStore(index_path)
    offers = await store2.get_offers(["verified-import-1"])
    await store2.close()
    assert not any(offer.source == "musinsa" for offer in offers.get("verified-import-1", []))


@pytest.mark.asyncio
async def test_apply_creates_offer_and_pending_match(tmp_path) -> None:
    module = _load_import_module()
    index_path = tmp_path / "index.sqlite3"
    store = SQLiteProductIndexStore(index_path)
    await _seed_known_canonical(store, "verified-import-1")
    await store.close()

    csv_path = tmp_path / "rows.csv"
    _write_csv(csv_path, [_BASE_ROW])

    summary = await module.build_import_summary(
        index_path=index_path,
        file_path=csv_path,
        file_format=None,
        imported_by="alice",
        strict=False,
        apply=True,
    )

    assert summary.created_offers == 1
    assert summary.matches_created == 1

    store2 = SQLiteProductIndexStore(index_path)
    offers = await store2.get_offers(["verified-import-1"])
    await store2.close()
    musinsa_offer = next(o for o in offers["verified-import-1"] if o.source == "musinsa")
    assert musinsa_offer.review_state == "pending_review"


@pytest.mark.asyncio
async def test_jsonl_format_produces_same_result_as_csv(tmp_path) -> None:
    module = _load_import_module()
    index_path = tmp_path / "index.sqlite3"
    store = SQLiteProductIndexStore(index_path)
    await _seed_known_canonical(store, "verified-import-1")
    await store.close()

    jsonl_path = tmp_path / "rows.jsonl"
    _write_jsonl(jsonl_path, [_BASE_ROW])

    summary = await module.build_import_summary(
        index_path=index_path,
        file_path=jsonl_path,
        file_format=None,
        imported_by="alice",
        strict=False,
        apply=True,
    )

    assert summary.format == "jsonl"
    assert summary.matches_created == 1
    store2 = SQLiteProductIndexStore(index_path)
    offers = await store2.get_offers(["verified-import-1"])
    await store2.close()
    assert any(
        o.source == "musinsa" and o.review_state == "pending_review"
        for o in offers["verified-import-1"]
    )


@pytest.mark.asyncio
async def test_missing_required_field_skips_only_that_row(tmp_path) -> None:
    module = _load_import_module()
    index_path = tmp_path / "index.sqlite3"
    store = SQLiteProductIndexStore(index_path)
    await _seed_known_canonical(store, "verified-import-1")
    await store.close()

    bad_row = dict(_BASE_ROW)
    bad_row["canonical_product_id"] = ""  # missing
    csv_path = tmp_path / "rows.csv"
    _write_csv(csv_path, [bad_row, _BASE_ROW])

    summary = await module.build_import_summary(
        index_path=index_path,
        file_path=csv_path,
        file_format=None,
        imported_by="alice",
        strict=False,
        apply=True,
    )

    assert summary.total_rows == 2
    assert summary.valid_rows == 1
    assert len(summary.invalid_rows) == 1
    assert "canonical_product_id" in summary.invalid_rows[0].reason
    assert summary.matches_created == 1


@pytest.mark.asyncio
async def test_confidence_out_of_range_is_skipped(tmp_path) -> None:
    module = _load_import_module()
    index_path = tmp_path / "index.sqlite3"
    store = SQLiteProductIndexStore(index_path)
    await _seed_known_canonical(store, "verified-import-1")
    await store.close()

    bad_row = dict(_BASE_ROW)
    bad_row["confidence"] = "1.5"
    csv_path = tmp_path / "rows.csv"
    _write_csv(csv_path, [bad_row])

    summary = await module.build_import_summary(
        index_path=index_path,
        file_path=csv_path,
        file_format=None,
        imported_by="alice",
        strict=False,
        apply=True,
    )

    assert summary.valid_rows == 0
    assert len(summary.invalid_rows) == 1
    assert summary.matches_created == 0


@pytest.mark.asyncio
async def test_reimporting_same_row_is_idempotent(tmp_path) -> None:
    module = _load_import_module()
    index_path = tmp_path / "index.sqlite3"
    store = SQLiteProductIndexStore(index_path)
    await _seed_known_canonical(store, "verified-import-1")
    await store.close()

    csv_path = tmp_path / "rows.csv"
    _write_csv(csv_path, [_BASE_ROW])

    await module.build_import_summary(
        index_path=index_path,
        file_path=csv_path,
        file_format=None,
        imported_by="alice",
        strict=False,
        apply=True,
    )
    second = await module.build_import_summary(
        index_path=index_path,
        file_path=csv_path,
        file_format=None,
        imported_by="alice",
        strict=False,
        apply=True,
    )

    assert second.created_offers == 0
    assert second.matches_created == 0
    assert second.matches_updated_pending == 1  # still pending, refreshed in place

    store2 = SQLiteProductIndexStore(index_path)
    count = store2._connection.execute(  # noqa: SLF001 - test-only direct row count
        "SELECT COUNT(*) AS c FROM product_matches"
    ).fetchone()["c"]
    await store2.close()
    assert count == 1  # no duplicate row


@pytest.mark.asyncio
async def test_already_reviewed_match_is_preserved_not_overwritten(tmp_path) -> None:
    module = _load_import_module()
    index_path = tmp_path / "index.sqlite3"
    store = SQLiteProductIndexStore(index_path)
    await _seed_known_canonical(store, "verified-import-1")
    await store.close()

    csv_path = tmp_path / "rows.csv"
    _write_csv(csv_path, [_BASE_ROW])

    await module.build_import_summary(
        index_path=index_path,
        file_path=csv_path,
        file_format=None,
        imported_by="alice",
        strict=False,
        apply=True,
    )

    # A human reviews it via the milestone 4 API path (store.review_match).
    store2 = SQLiteProductIndexStore(index_path)
    match_id = "match:verified-import-1:musinsa:ms-1"
    outcome = await store2.review_match(match_id, decision="rejected", reviewer="bob")
    assert outcome.status == "updated"
    await store2.close()

    # Re-importing the same file must not resurrect it back to pending.
    second = await module.build_import_summary(
        index_path=index_path,
        file_path=csv_path,
        file_format=None,
        imported_by="alice",
        strict=False,
        apply=True,
    )
    assert second.matches_preserved_already_reviewed == 1
    assert second.matches_updated_pending == 0

    store3 = SQLiteProductIndexStore(index_path)
    offers = await store3.get_offers(["verified-import-1"])
    await store3.close()
    musinsa_offer = next(o for o in offers["verified-import-1"] if o.source == "musinsa")
    assert musinsa_offer.review_state == "rejected"


@pytest.mark.asyncio
async def test_unknown_canonical_product_id_warns_by_default_but_still_processes(tmp_path) -> None:
    module = _load_import_module()
    index_path = tmp_path / "index.sqlite3"
    store = SQLiteProductIndexStore(index_path)
    await store.close()  # no seeded products at all

    csv_path = tmp_path / "rows.csv"
    _write_csv(csv_path, [_BASE_ROW])

    summary = await module.build_import_summary(
        index_path=index_path,
        file_path=csv_path,
        file_format=None,
        imported_by="alice",
        strict=False,
        apply=True,
    )

    assert summary.unknown_canonical_product_ids == ["verified-import-1"]
    assert summary.matches_created == 1  # still processed


@pytest.mark.asyncio
async def test_unknown_canonical_product_id_skipped_when_strict(tmp_path) -> None:
    module = _load_import_module()
    index_path = tmp_path / "index.sqlite3"
    store = SQLiteProductIndexStore(index_path)
    await store.close()

    csv_path = tmp_path / "rows.csv"
    _write_csv(csv_path, [_BASE_ROW])

    summary = await module.build_import_summary(
        index_path=index_path,
        file_path=csv_path,
        file_format=None,
        imported_by="alice",
        strict=True,
        apply=True,
    )

    assert summary.strict_skipped_unknown_canonical == 1
    assert summary.matches_created == 0


@pytest.mark.asyncio
async def test_offer_conflict_is_skipped_and_existing_link_preserved(tmp_path) -> None:
    module = _load_import_module()
    index_path = tmp_path / "index.sqlite3"
    store = SQLiteProductIndexStore(index_path)
    await _seed_known_canonical(store, "verified-import-1")
    # Existing offer for (musinsa, ms-1) already linked to a DIFFERENT canonical product.
    await store.upsert_search_results(
        "다른 상품",
        [
            ProductSourceRecord(
                canonical_product_id="verified-other-product",
                source="musinsa",
                source_product_id="ms-1",
                source_url="https://musinsa.example/1",
                original_price=9000,
            )
        ],
    )
    await store.close()

    csv_path = tmp_path / "rows.csv"
    _write_csv(csv_path, [_BASE_ROW])  # claims ms-1 for verified-import-1 instead

    summary = await module.build_import_summary(
        index_path=index_path,
        file_path=csv_path,
        file_format=None,
        imported_by="alice",
        strict=False,
        apply=True,
    )

    assert summary.offer_conflicts_skipped == 1
    assert summary.matches_created == 0
