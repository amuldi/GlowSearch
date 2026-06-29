import json
from pathlib import Path

import pytest

from app.ingestion.catalog_quality import (
    build_index_quality_report,
    build_catalog_quality_report,
    enrichment_target_export_rows,
    filter_enrichment_targets,
)
from app.indexing.store import SQLiteProductIndexStore
from app.models.product import ProductSourceRecord


@pytest.mark.asyncio
async def test_catalog_quality_report_splits_required_display_and_enrichment_issues(tmp_path) -> None:
    catalog_path = tmp_path / "verified_products.json"
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "official_en": "peripera",
                        "aliases": ["페리페라", "PERIPERA"],
                        "sources": [],
                    },
                    {
                        "official_en": "CLIO",
                        "aliases": ["클리오"],
                        "sources": [],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    catalog_path.write_text(
        json.dumps(
            {
                "products": [
                    {
                        "canonical_product_id": "verified:peripera-brow",
                        "brand_ko": "페리페라",
                        "brand_en": "peripera",
                        "product_name_ko": "[6월 올영픽] 페리페라 스피디 스키니 브로우 8 Colors (단품/더블)",
                        "product_name_en": "[PERIPERA] Speedy Skinny Brow",
                        "product_name_display_ko": "스피디 스키니 브로우",
                        "product_name_display_en": "Speedy Skinny Brow",
                        "source": "oliveyoung",
                        "source_url": "https://oliveyoung.example/peripera",
                        "goods_no": "A001",
                        "image_url": "https://image.example/peripera.jpg",
                        "price": 5700,
                    },
                    {
                        "canonical_product_id": "verified:dirty",
                        "brand_ko": "브랜드",
                        "product_name_ko": "제품 [테스트",
                        "source": "official",
                    },
                    {
                        "canonical_product_id": "verified:clio",
                        "brand_ko": "클리오",
                        "brand_en": "CLIO",
                        "product_name_ko": "(클리오X국가유산청) 프로 아이 팔레트 에어",
                        "source": "glowpick",
                        "source_url": "https://glowpick.example/clio",
                        "goods_no": "G001",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    report = await build_catalog_quality_report(
        catalog_path=catalog_path,
        registry_path=registry_path,
        base_url="https://www.oliveyoung.co.kr",
    )

    assert report.total == 3
    assert report.source_counts == {"glowpick": 1, "official": 1, "oliveyoung": 1}
    assert report.product_name_en_count == 1
    assert report.display_cleaned_count == 2
    assert report.product_name_display_ko_override_count == 1
    assert report.product_name_display_en_override_count == 1
    assert report.required_issue_count == 1
    assert report.display_issue_count == 1
    assert report.enrichment_missing_fields["product_name_en"] == 2
    assert report.product_name_en_target_count == 2
    assert report.product_name_en_targets[0].canonical_product_id == "verified:clio"
    assert report.product_name_en_targets[0].source_url == "https://glowpick.example/clio"

    issue_keys = {(issue.severity, issue.issue) for issue in report.issues}
    assert ("required", "missing_source_locator") in issue_keys
    assert ("display", "dirty_display_name") in issue_keys
    assert ("enrichment", "missing_product_name_en") in issue_keys


@pytest.mark.asyncio
async def test_index_quality_report_audits_sqlite_product_index(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "official_en": "peripera",
                        "aliases": ["페리페라", "PERIPERA"],
                        "sources": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    index_path = tmp_path / "product_index.sqlite3"
    store = SQLiteProductIndexStore(index_path)
    try:
        await store.upsert_search_results(
            "페리페라 브로우",
            [
                ProductSourceRecord(
                    canonical_product_id="verified:peripera-brow",
                    source_brand_name="페리페라",
                    product_name_ko="[6월 올영픽] 페리페라 스피디 스키니 브로우 8 Colors (단품/더블)",
                    product_name_display_ko="[6월 올영픽] 페리페라 스피디 스키니 브로우",
                    source="oliveyoung",
                    source_url="https://oliveyoung.example/peripera",
                    source_product_id="A001",
                    image_url="https://image.example/peripera.jpg",
                    regular_price=5700,
                )
            ],
        )
    finally:
        await store.close()

    report = await build_index_quality_report(
        index_path=index_path,
        registry_path=registry_path,
        base_url="https://www.oliveyoung.co.kr",
    )

    assert report.catalog_path == str(index_path)
    assert report.total == 1
    assert report.source_counts == {"oliveyoung": 1}
    assert report.display_issue_count == 1
    assert report.product_name_en_target_count == 1
    assert report.enrichment_missing_fields["product_name_en"] == 1
    assert report.issues[0].issue == "dirty_display_name"


@pytest.mark.asyncio
async def test_index_quality_report_flags_trailing_display_suffix_noise(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "official_en": "TOCOBO",
                        "aliases": ["토코보"],
                        "sources": [],
                    },
                    {
                        "official_en": "Anua",
                        "aliases": ["아누아"],
                        "sources": [],
                    },
                    {
                        "official_en": "Avene",
                        "aliases": ["아벤느"],
                        "sources": [],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    index_path = tmp_path / "product_index.sqlite3"
    store = SQLiteProductIndexStore(index_path)
    try:
        await store.upsert_search_results(
            "display noise",
            [
                ProductSourceRecord(
                    source_brand_name="토코보",
                    product_name_ko="토코보 블러 피니쉬 선 쿠션 SPF50+ PA++++13g 2종",
                    product_name_display_ko="블러 피니쉬 선 쿠션 SPF50+ PA++++13g",
                    source="oliveyoung",
                    source_url="https://oliveyoung.example/tocobo",
                    source_product_id="A101",
                ),
                ProductSourceRecord(
                    source_brand_name="아누아",
                    product_name_ko="아누아 피디알엔 히알루론산 캡슐 100 세럼 1ml*10ea",
                    product_name_display_ko="피디알엔 히알루론산 캡슐 100 세럼 1ml*10ea",
                    source="oliveyoung",
                    source_url="https://oliveyoung.example/anua",
                    source_product_id="A102",
                ),
                ProductSourceRecord(
                    source_brand_name="아벤느",
                    product_name_ko="아벤느 클리낭스 클렌징 젤 200ml*피지잡는 *약산성클렌저",
                    product_name_display_ko="클리낭스 클렌징 젤 200ml*피지잡는 *약산성클렌저",
                    source="oliveyoung",
                    source_url="https://oliveyoung.example/avene",
                    source_product_id="A103",
                ),
            ],
        )
    finally:
        await store.close()

    report = await build_index_quality_report(
        index_path=index_path,
        registry_path=registry_path,
        base_url="https://www.oliveyoung.co.kr",
    )

    issue_names = {issue.issue for issue in report.issues if issue.severity == "display"}
    assert report.display_issue_count == 3
    assert issue_names == {
        "dirty_display_bundle_suffix",
        "dirty_display_sun_protection_suffix",
        "dirty_display_volume_descriptor_suffix",
    }


@pytest.mark.asyncio
async def test_catalog_quality_skips_product_name_en_target_when_canonical_group_has_english(
    tmp_path,
) -> None:
    catalog_path = tmp_path / "verified_products.json"
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "official_en": "KISS ME",
                        "aliases": ["키스미"],
                        "sources": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    catalog_path.write_text(
        json.dumps(
            {
                "products": [
                    {
                        "canonical_product_id": "verified:kissme-brow",
                        "brand_ko": "키스미",
                        "brand_en": "KISS ME",
                        "product_name_ko": "[1등브로우]키스미 헤비로테이션 컬러링 아이브로우 EX 6종",
                        "product_name_display_ko": "헤비로테이션 컬러링 아이브로우 EX",
                        "source": "oliveyoung",
                        "source_url": "https://oliveyoung.example/kissme",
                        "goods_no": "A001",
                    },
                    {
                        "canonical_product_id": "verified:kissme-brow",
                        "brand_ko": "키스미",
                        "brand_en": "KISS ME",
                        "product_name_en": "COLORING EYEBROW EX",
                        "product_name_display_en": "COLORING EYEBROW EX",
                        "source": "official",
                        "source_url": "https://official.example/kissme",
                        "goods_no": "official-1",
                    },
                    {
                        "canonical_product_id": "verified:needs-english",
                        "brand_ko": "브랜드",
                        "brand_en": "Brand",
                        "product_name_ko": "브랜드 제품",
                        "product_name_display_ko": "제품",
                        "source": "official",
                        "source_url": "https://official.example/needs-english",
                        "goods_no": "official-2",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    report = await build_catalog_quality_report(
        catalog_path=catalog_path,
        registry_path=registry_path,
        base_url="https://www.oliveyoung.co.kr",
    )

    assert report.enrichment_missing_fields["product_name_en"] == 2
    assert report.product_name_en_target_count == 1
    assert report.product_name_en_targets[0].canonical_product_id == "verified:needs-english"


@pytest.mark.asyncio
async def test_catalog_quality_flags_brand_prefixed_display_name(tmp_path) -> None:
    catalog_path = tmp_path / "verified_products.json"
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "official_en": "peripera",
                        "aliases": ["페리페라", "PERIPERA"],
                        "sources": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    catalog_path.write_text(
        json.dumps(
            {
                "products": [
                    {
                        "canonical_product_id": "verified:peripera-brow",
                        "brand_ko": "페리페라",
                        "brand_en": "peripera",
                        "product_name_ko": "[6월 올영픽] 페리페라 스피디 스키니 브로우 8 Colors (단품/더블)",
                        "product_name_display_ko": "페리페라 스피디 스키니 브로우",
                        "source": "oliveyoung",
                        "source_url": "https://oliveyoung.example/peripera",
                        "goods_no": "A001",
                    },
                    {
                        "canonical_product_id": "verified:peripera-clean",
                        "brand_ko": "페리페라",
                        "brand_en": "peripera",
                        "product_name_ko": "[6월 올영픽] 페리페라 스피디 스키니 브로우 8 Colors (단품/더블)",
                        "product_name_display_ko": "스피디 스키니 브로우",
                        "source": "oliveyoung",
                        "source_url": "https://oliveyoung.example/peripera-clean",
                        "goods_no": "A002",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    report = await build_catalog_quality_report(
        catalog_path=catalog_path,
        registry_path=registry_path,
        base_url="https://www.oliveyoung.co.kr",
    )

    brand_prefix_issues = [
        issue for issue in report.issues if issue.issue == "brand_prefixed_display_name"
    ]
    assert report.display_issue_count == 1
    assert len(brand_prefix_issues) == 1
    assert brand_prefix_issues[0].canonical_product_id == "verified:peripera-brow"
    assert brand_prefix_issues[0].detail == "페리페라 스피디 스키니 브로우"


@pytest.mark.asyncio
async def test_catalog_quality_deduplicates_product_name_en_targets_by_canonical_id(
    tmp_path,
) -> None:
    catalog_path = tmp_path / "verified_products.json"
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "official_en": "mude",
                        "aliases": ["뮤드"],
                        "sources": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    catalog_path.write_text(
        json.dumps(
            {
                "products": [
                    {
                        "canonical_product_id": "verified:mude-brow-cara",
                        "brand_ko": "뮤드",
                        "brand_en": "mude",
                        "product_name_ko": "[NEW컬러] 뮤드 인스파이어 스키니 브로우 카라 10종",
                        "product_name_display_ko": "인스파이어 스키니 브로우 카라",
                        "source": "oliveyoung",
                        "source_url": "https://oliveyoung.example/mude",
                        "goods_no": "A001",
                    },
                    {
                        "canonical_product_id": "verified:mude-brow-cara",
                        "brand_ko": "뮤드",
                        "brand_en": "mude",
                        "product_name_ko": "뮤드 인스파이어 스키니 브로우카라",
                        "product_name_display_ko": "인스파이어 스키니 브로우 카라",
                        "source": "official",
                        "source_url": "https://official.example/mude",
                        "goods_no": "official-1",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    report = await build_catalog_quality_report(
        catalog_path=catalog_path,
        registry_path=registry_path,
        base_url="https://www.oliveyoung.co.kr",
    )

    assert report.enrichment_missing_fields["product_name_en"] == 2
    assert report.product_name_en_target_count == 1
    assert report.product_name_en_targets[0].canonical_product_id == "verified:mude-brow-cara"
    assert report.product_name_en_targets[0].source == "official"
    assert report.product_name_en_targets[0].source_url == "https://official.example/mude"


@pytest.mark.asyncio
async def test_catalog_quality_exports_batchable_enrichment_target_rows(tmp_path) -> None:
    catalog_path = tmp_path / "verified_products.json"
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "official_en": "mude",
                        "aliases": ["뮤드"],
                        "sources": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    catalog_path.write_text(
        json.dumps(
            {
                "products": [
                    {
                        "canonical_product_id": "verified:mude-brow-cara",
                        "brand_ko": "뮤드",
                        "brand_en": "mude",
                        "product_name_ko": "뮤드 인스파이어 스키니 브로우카라",
                        "product_name_display_ko": "인스파이어 스키니 브로우 카라",
                        "source": "official",
                        "source_url": "https://official.example/mude",
                        "goods_no": "official-1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = await build_catalog_quality_report(
        catalog_path=catalog_path,
        registry_path=registry_path,
        base_url="https://www.oliveyoung.co.kr",
    )
    rows = enrichment_target_export_rows(report.product_name_en_targets)

    assert rows == [
        {
            "priority": "1",
            "field": "product_name_en",
            "canonical_product_id": "verified:mude-brow-cara",
            "source": "official",
            "source_product_id": "official-1",
            "brand_ko": "뮤드",
            "brand_en": "mude",
            "product_name_display_ko": "인스파이어 스키니 브로우 카라",
            "source_url": "https://official.example/mude",
            "search_query": "mude 뮤드 인스파이어 스키니 브로우 카라",
            "reason": "product_name_en missing, source_url available, brand_en available",
        }
    ]


@pytest.mark.asyncio
async def test_catalog_quality_filters_enrichment_targets_by_source_prefix_and_field(tmp_path) -> None:
    catalog_path = tmp_path / "verified_products.json"
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "official_en": "mude",
                        "aliases": ["뮤드"],
                        "sources": [],
                    },
                    {
                        "official_en": "romand",
                        "aliases": ["롬앤"],
                        "sources": [],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    catalog_path.write_text(
        json.dumps(
            {
                "products": [
                    {
                        "canonical_product_id": "verified:mude-brow-cara",
                        "brand_ko": "뮤드",
                        "brand_en": "mude",
                        "product_name_ko": "뮤드 인스파이어 스키니 브로우카라",
                        "product_name_display_ko": "인스파이어 스키니 브로우 카라",
                        "source": "official",
                        "source_url": "https://official.example/mude",
                        "goods_no": "official-1",
                    },
                    {
                        "canonical_product_id": "verified:romand-contour",
                        "brand_ko": "롬앤",
                        "brand_en": "romand",
                        "product_name_ko": "롬앤 베러 댄 쉐이프",
                        "product_name_display_ko": "베러 댄 쉐이프",
                        "source": "musinsa:beauty",
                        "source_url": "https://musinsa.example/romand",
                        "goods_no": "musinsa-1",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    report = await build_catalog_quality_report(
        catalog_path=catalog_path,
        registry_path=registry_path,
        base_url="https://www.oliveyoung.co.kr",
    )

    official_targets = filter_enrichment_targets(report.product_name_en_targets, sources={"official"})
    musinsa_targets = filter_enrichment_targets(
        report.product_name_en_targets,
        sources={"musinsa"},
        fields={"product_name_en"},
    )
    missing_field_targets = filter_enrichment_targets(
        report.product_name_en_targets,
        fields={"brand_en"},
    )

    assert [target.canonical_product_id for target in official_targets] == ["verified:mude-brow-cara"]
    assert [target.canonical_product_id for target in musinsa_targets] == ["verified:romand-contour"]
    assert missing_field_targets == []


@pytest.mark.asyncio
async def test_catalog_quality_exports_image_and_price_enrichment_targets(tmp_path) -> None:
    catalog_path = tmp_path / "verified_products.json"
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "official_en": "CLIO",
                        "aliases": ["클리오"],
                        "sources": [],
                    },
                    {
                        "official_en": "HERA",
                        "aliases": ["헤라"],
                        "sources": [],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    catalog_path.write_text(
        json.dumps(
            {
                "products": [
                    {
                        "canonical_product_id": "verified:clio-palette",
                        "brand_ko": "클리오",
                        "brand_en": "CLIO",
                        "product_name_ko": "클리오 프로 아이 팔레트 에어",
                        "product_name_en": "[CLIO] Pro Eye Palette Air",
                        "product_name_display_ko": "프로 아이 팔레트 에어",
                        "product_name_display_en": "Pro Eye Palette Air",
                        "price": 34000,
                        "source": "glowpick",
                        "source_url": "https://glowpick.example/clio",
                        "goods_no": "G001",
                    },
                    {
                        "canonical_product_id": "verified:hera-powder",
                        "brand_ko": "헤라",
                        "brand_en": "HERA",
                        "product_name_ko": "헤라 소프트 피니시 루스 파우더 15g",
                        "product_name_en": "SOFT FINISH LOOSE POWDER",
                        "product_name_display_ko": "소프트 피니시 루스 파우더",
                        "product_name_display_en": "SOFT FINISH LOOSE POWDER",
                        "image_url": "https://image.example/hera.jpg",
                        "source": "official",
                        "source_url": "https://official.example/hera",
                        "goods_no": "official-1",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    report = await build_catalog_quality_report(
        catalog_path=catalog_path,
        registry_path=registry_path,
        base_url="https://www.oliveyoung.co.kr",
    )

    image_targets = filter_enrichment_targets(report.enrichment_targets, fields={"image_url"})
    price_targets = filter_enrichment_targets(report.enrichment_targets, fields={"price"})
    rows = enrichment_target_export_rows(image_targets + price_targets)

    assert report.product_name_en_target_count == 0
    assert [target.canonical_product_id for target in image_targets] == ["verified:clio-palette"]
    assert [target.reason for target in image_targets] == [
        "image_url missing, source_url available, source_product_id available"
    ]
    assert [target.canonical_product_id for target in price_targets] == ["verified:hera-powder"]
    assert rows == [
        {
            "priority": "1",
            "field": "image_url",
            "canonical_product_id": "verified:clio-palette",
            "source": "glowpick",
            "source_product_id": "G001",
            "brand_ko": "클리오",
            "brand_en": "CLIO",
            "product_name_display_ko": "프로 아이 팔레트 에어",
            "source_url": "https://glowpick.example/clio",
            "search_query": "CLIO 클리오 프로 아이 팔레트 에어",
            "reason": "image_url missing, source_url available, source_product_id available",
        },
        {
            "priority": "2",
            "field": "price",
            "canonical_product_id": "verified:hera-powder",
            "source": "official",
            "source_product_id": "official-1",
            "brand_ko": "헤라",
            "brand_en": "HERA",
            "product_name_display_ko": "소프트 피니시 루스 파우더",
            "source_url": "https://official.example/hera",
            "search_query": "HERA 헤라 소프트 피니시 루스 파우더",
            "reason": "price missing, source_url available, source_product_id available",
        },
    ]


@pytest.mark.asyncio
async def test_project_catalog_quality_has_no_required_or_dirty_display_issues() -> None:
    report = await build_catalog_quality_report(
        catalog_path=Path(__file__).resolve().parents[1] / "data" / "verified_products.json",
        registry_path=Path(__file__).resolve().parents[1] / "data" / "brand_registry.json",
        base_url="https://www.oliveyoung.co.kr",
    )

    assert report.required_issue_count == 0
    assert report.display_issue_count == 0
    assert report.product_name_en_target_count >= 15
    assert report.total >= 39
