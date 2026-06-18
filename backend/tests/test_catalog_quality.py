import json
from pathlib import Path

import pytest

from app.ingestion.catalog_quality import build_catalog_quality_report


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
                        "product_name_ko": "제품 [기획]",
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

    issue_keys = {(issue.severity, issue.issue) for issue in report.issues}
    assert ("required", "missing_source_locator") in issue_keys
    assert ("display", "dirty_display_name") in issue_keys
    assert ("enrichment", "missing_product_name_en") in issue_keys


@pytest.mark.asyncio
async def test_project_catalog_quality_has_no_required_or_dirty_display_issues() -> None:
    report = await build_catalog_quality_report(
        catalog_path=Path(__file__).resolve().parents[1] / "data" / "verified_products.json",
        registry_path=Path(__file__).resolve().parents[1] / "data" / "brand_registry.json",
        base_url="https://www.oliveyoung.co.kr",
    )

    assert report.required_issue_count == 0
    assert report.display_issue_count == 0
    assert report.total >= 39
