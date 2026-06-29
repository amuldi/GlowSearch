from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

from app.indexing.store import SQLiteProductIndexStore
from app.models.product import ProductSourceRecord


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "backfill_index_normalized_fields.py"


def _load_backfill_module():
    spec = importlib.util.spec_from_file_location("backfill_index_normalized_fields_script", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_backfill_index_normalized_fields_reports_and_applies_changes(tmp_path) -> None:
    module = _load_backfill_module()
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"BEGINS BY JUNGSAEMMOOL","aliases":["비긴스 바이 정샘물","비긴스"],"sources":[]}]}',
        encoding="utf-8",
    )
    index_path = tmp_path / "product_index.sqlite3"
    store = SQLiteProductIndexStore(index_path)
    try:
        await store.upsert_search_results(
            "비긴스 수분세럼",
            [
                ProductSourceRecord(
                    source_brand_name="비긴스",
                    product_name_ko="[10만나노히알]비긴스바이정샘물 블루 수국 히알 수분세럼 30ml",
                    source="oliveyoung",
                    source_url="https://oliveyoung.example/item",
                    source_product_id="A001",
                )
            ],
        )
    finally:
        await store.close()

    dry_run = await module.build_backfill_summary(
        index_path=index_path,
        registry_path=registry_path,
        base_url="https://www.oliveyoung.co.kr",
        limit=None,
        sample_limit=5,
        apply=False,
    )

    assert dry_run.scanned == 1
    assert dry_run.changed == 1
    assert dry_run.applied is False
    assert dry_run.changed_fields["source_brand_name"] == 1
    assert dry_run.changed_fields["source_brand_name_en"] == 1
    assert dry_run.changed_fields["product_name_display_ko"] == 1

    applied = await module.build_backfill_summary(
        index_path=index_path,
        registry_path=registry_path,
        base_url="https://www.oliveyoung.co.kr",
        limit=None,
        sample_limit=5,
        apply=True,
    )

    assert applied.applied is True
    assert applied.changed == 1

    store = SQLiteProductIndexStore(index_path)
    try:
        records = await store.all_products()
    finally:
        await store.close()

    assert records[0].source_brand_name == "비긴스 바이 정샘물"
    assert records[0].source_brand_name_en == "BEGINS BY JUNGSAEMMOOL"
    assert records[0].product_name_display_ko == "블루 수국 히알 수분세럼"


@pytest.mark.asyncio
async def test_backfill_index_normalized_fields_can_recompute_existing_display_names(
    tmp_path,
) -> None:
    module = _load_backfill_module()
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"TOCOBO","aliases":["토코보"],"sources":[]}]}',
        encoding="utf-8",
    )
    index_path = tmp_path / "product_index.sqlite3"
    store = SQLiteProductIndexStore(index_path)
    try:
        await store.upsert_search_results(
            "토코보 선크림",
            [
                ProductSourceRecord(
                    source_brand_name="토코보",
                    product_name_ko="[수분선크림/화잘먹] 토코보 바이오 워터리 선크림 50mL SPF50+ PA++++",
                    product_name_display_ko="바이오 워터리 선크림 50mL SPF50+ PA++++",
                    source="oliveyoung",
                    source_url="https://oliveyoung.example/sun",
                    source_product_id="A002",
                )
            ],
        )
    finally:
        await store.close()

    dry_run_without_recompute = await module.build_backfill_summary(
        index_path=index_path,
        registry_path=registry_path,
        base_url="https://www.oliveyoung.co.kr",
        limit=None,
        sample_limit=5,
        apply=False,
    )
    assert "product_name_display_ko" not in dry_run_without_recompute.samples[0].changes

    dry_run = await module.build_backfill_summary(
        index_path=index_path,
        registry_path=registry_path,
        base_url="https://www.oliveyoung.co.kr",
        limit=None,
        sample_limit=5,
        apply=False,
        recompute_display_names=True,
    )
    assert dry_run.changed == 1
    assert dry_run.changed_fields["product_name_display_ko"] == 1
    assert dry_run.samples[0].changes["product_name_display_ko"] == {
        "before": "바이오 워터리 선크림 50mL SPF50+ PA++++",
        "after": "바이오 워터리 선크림",
    }

    await module.build_backfill_summary(
        index_path=index_path,
        registry_path=registry_path,
        base_url="https://www.oliveyoung.co.kr",
        limit=None,
        sample_limit=5,
        apply=True,
        recompute_display_names=True,
    )

    connection = sqlite3.connect(index_path)
    try:
        row = connection.execute(
            "SELECT product_name_display_ko, search_text FROM products WHERE source_product_id = 'A002'"
        ).fetchone()
    finally:
        connection.close()

    assert row[0] == "바이오 워터리 선크림"
    assert "바이오워터리선크림" in row[1]
