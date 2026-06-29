from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from app.ingestion.source_evidence import ProductImageEvidence, ProductPriceEvidence


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_catalog_enrichment_sources.py"


def _load_audit_module():
    spec = importlib.util.spec_from_file_location("audit_catalog_enrichment_sources_script", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_catalog_enrichment_source_audit_treats_only_positive_prices_as_usable() -> None:
    module = _load_audit_module()

    assert module._is_positive_price("16,000")
    assert module._is_positive_price("₩16,000")
    assert module._is_positive_price("14.9")
    assert not module._is_positive_price("0")
    assert not module._is_positive_price("0.0")
    assert not module._is_positive_price("")
    assert not module._is_positive_price("price unavailable")


def test_catalog_enrichment_source_audit_picks_first_positive_price() -> None:
    module = _load_audit_module()

    price = module._first_usable_price(
        [
            ProductPriceEvidence(source="json_ld_offer_price", price="0.0", currency="KRW"),
            ProductPriceEvidence(source="meta:product:price:amount", price="16,000", currency="KRW"),
        ]
    )

    assert price == ProductPriceEvidence(
        source="meta:product:price:amount",
        price="16,000",
        currency="KRW",
    )


def test_catalog_enrichment_source_audit_csv_marks_target_field_usability() -> None:
    module = _load_audit_module()

    csv_output = module._render_rows(
        [
            {
                "priority": "1",
                "field": "price",
                "canonical_product_id": "canonical:example",
                "source": "official",
                "source_product_id": "example",
                "product_name_display_ko": "예시 상품",
                "source_url": "https://brand.example/product",
                "candidate_name": "",
                "candidate_language": "",
                "candidate_source": "",
                "usable_for_product_name_en": "false",
                "usable_for_target_field": "true",
                "candidate_image_url": "",
                "candidate_price": "16,000",
                "candidate_currency": "KRW",
                "candidate_rejection_reason": "",
                "evidence_count": "0",
                "evidence_names": "",
                "evidence_languages": "",
                "error": "",
            }
        ],
        output_format="csv",
    )

    assert "usable_for_target_field" in csv_output
    assert "false,true" in csv_output


def test_catalog_enrichment_source_audit_rejects_broken_image_urls() -> None:
    module = _load_audit_module()

    assert module._is_usable_image_url("https://image.example/product.jpg")
    assert module._is_usable_image_url("http://image.example/product.jpg")
    assert not module._is_usable_image_url("https:https://image.example/product.jpg")
    assert not module._is_usable_image_url("//image.example/product.jpg")
    assert not module._is_usable_image_url("")


def test_catalog_enrichment_source_audit_reports_invalid_image_url_reason() -> None:
    module = _load_audit_module()

    reason = module._candidate_rejection_reason_for_target(
        "image_url",
        existing_reason="",
        error="",
        evidence=[],
        image_evidence=[
            ProductImageEvidence(source="meta:og:image", url="https:https://image.example/product.jpg")
        ],
        price_evidence=[],
    )

    assert reason == "invalid_image_url_evidence"
