from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from app.ingestion.catalog_quality import DIRTY_DISPLAY_MARKERS
from app.models.product import ProductSearchResult, ProductSourceRecord
from app.normalizer.brand import BrandResolver
from app.normalizer.product import ProductNormalizer
from app.normalizer.text import clean_text, parse_krw_price

IssueSeverity = Literal["required", "brand", "display", "enrichment"]


@dataclass(frozen=True)
class ExportQualityIssue:
    severity: IssueSeverity
    issue: str
    source: str
    source_product_id: str | None
    source_brand_name: str | None
    brand_ko: str | None
    brand_en: str | None
    product_name_ko: str | None
    product_name_display_ko: str | None
    detail: str


@dataclass(frozen=True)
class ExportQualityReport:
    export_path: str
    total: int
    source_counts: dict[str, int]
    source_brand_counts: dict[str, int]
    required_issue_count: int
    brand_issue_count: int
    display_issue_count: int
    enrichment_issue_count: int
    brand_corrected_count: int
    display_cleaned_count: int
    product_name_en_count: int
    records_with_rating: int
    records_with_review_count: int
    records_with_options: int
    sold_out_count: int
    average_quality_score: float
    enrichment_missing_fields: dict[str, int]
    issues: list[ExportQualityIssue]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["issues"] = [asdict(issue) for issue in self.issues]
        return payload


def build_export_quality_report(
    *,
    export_path: Path,
    registry_path: Path,
    base_url: str,
    max_issues: int | None = 80,
) -> ExportQualityReport:
    normalizer = ProductNormalizer(BrandResolver(registry_path), base_url=base_url)
    try:
        products: list[tuple[ProductSourceRecord, ProductSearchResult]] = []
        with export_path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                record = _record_from_row(row)
                products.append((record, normalizer.normalize(record)))

        source_counts: Counter[str] = Counter()
        source_brand_counts: Counter[str] = Counter()
        enrichment_missing_fields: Counter[str] = Counter()
        issues: list[ExportQualityIssue] = []
        brand_corrected_count = 0
        display_cleaned_count = 0
        product_name_en_count = 0
        records_with_rating = 0
        records_with_review_count = 0
        records_with_options = 0
        sold_out_count = 0
        quality_score_total = 0

        for record, product in products:
            source_counts[product.source.split(":", 1)[0]] += 1
            if record.source_brand_name:
                source_brand_counts[record.source_brand_name] += 1
            quality_score_total += product.quality_score
            if product.product_name_en:
                product_name_en_count += 1
            if product.rating is not None:
                records_with_rating += 1
            if product.review_count is not None:
                records_with_review_count += 1
            if product.options:
                records_with_options += 1
            if product.sold_out is True:
                sold_out_count += 1
            if _is_brand_corrected(record, product):
                brand_corrected_count += 1
            if (
                product.product_name_ko
                and product.product_name_display_ko
                and product.product_name_ko != product.product_name_display_ko
            ):
                display_cleaned_count += 1
            enrichment_missing_fields.update(product.enrichment_missing_fields)
            issues.extend(_required_issues(record, product))
            issues.extend(_brand_issues(record, product))
            issues.extend(_display_issues(record, product))
            issues.extend(_enrichment_issues(record, product))

        sorted_issues = sorted(issues, key=_issue_sort_key)
        if max_issues is not None and max_issues >= 0:
            sorted_issues = sorted_issues[:max_issues]
        total = len(products)
        return ExportQualityReport(
            export_path=str(export_path),
            total=total,
            source_counts=dict(sorted(source_counts.items())),
            source_brand_counts=dict(source_brand_counts.most_common(40)),
            required_issue_count=sum(1 for issue in issues if issue.severity == "required"),
            brand_issue_count=sum(1 for issue in issues if issue.severity == "brand"),
            display_issue_count=sum(1 for issue in issues if issue.severity == "display"),
            enrichment_issue_count=sum(1 for issue in issues if issue.severity == "enrichment"),
            brand_corrected_count=brand_corrected_count,
            display_cleaned_count=display_cleaned_count,
            product_name_en_count=product_name_en_count,
            records_with_rating=records_with_rating,
            records_with_review_count=records_with_review_count,
            records_with_options=records_with_options,
            sold_out_count=sold_out_count,
            average_quality_score=round(quality_score_total / total, 2) if total else 0.0,
            enrichment_missing_fields=dict(sorted(enrichment_missing_fields.items())),
            issues=sorted_issues,
        )
    finally:
        normalizer.close()


def _record_from_row(row: dict[str, str]) -> ProductSourceRecord:
    price = parse_krw_price(row.get("price"))
    discount_price = parse_krw_price(row.get("discount_price"))
    sale_price = discount_price if discount_price is not None and discount_price != price else None
    return ProductSourceRecord(
        category=clean_text(row.get("category")),
        source_brand_name=clean_text(row.get("brand_name")),
        product_name_ko=clean_text(row.get("product_name")),
        regular_price=price,
        original_price=price,
        sale_price=sale_price,
        rating=_parse_float(row.get("rating")),
        review_count=_parse_int(row.get("review_count")),
        image_url=clean_text(row.get("image_url")),
        description=clean_text(row.get("description")),
        options=_parse_options(row.get("options")),
        sold_out=_parse_bool(row.get("sold_out")),
        source=clean_text(row.get("source")) or "unknown",
        source_url=clean_text(row.get("product_url")),
        source_product_id=clean_text(row.get("product_id")),
        updated_at=clean_text(row.get("updated_at")),
    )


def _required_issues(
    record: ProductSourceRecord,
    product: ProductSearchResult,
) -> list[ExportQualityIssue]:
    issues: list[ExportQualityIssue] = []
    if not product.product_name_ko and not product.product_name_en:
        issues.append(_issue(record, product, "required", "missing_product_name", "product_name"))
    if not product.source:
        issues.append(_issue(record, product, "required", "missing_source", "source"))
    if not product.source_url and not product.source_product_id:
        issues.append(_issue(record, product, "required", "missing_source_locator", "source_url/source_product_id"))
    return issues


def _brand_issues(
    record: ProductSourceRecord,
    product: ProductSearchResult,
) -> list[ExportQualityIssue]:
    issues: list[ExportQualityIssue] = []
    if not product.brand_ko:
        issues.append(_issue(record, product, "brand", "missing_brand_ko", "brand_ko"))
    if not product.brand_en:
        issues.append(_issue(record, product, "brand", "missing_brand_en", "brand_en"))
    if _is_brand_corrected(record, product):
        issues.append(
            _issue(
                record,
                product,
                "brand",
                "corrected_source_brand",
                f"{record.source_brand_name} -> {product.brand_ko}",
            )
        )
    return issues


def _display_issues(
    record: ProductSourceRecord,
    product: ProductSearchResult,
) -> list[ExportQualityIssue]:
    display_name = product.product_name_display_ko
    if not display_name:
        return []
    if any(marker in display_name for marker in DIRTY_DISPLAY_MARKERS):
        return [_issue(record, product, "display", "dirty_display_name", display_name)]
    return []


def _enrichment_issues(
    record: ProductSourceRecord,
    product: ProductSearchResult,
) -> list[ExportQualityIssue]:
    issues: list[ExportQualityIssue] = []
    for field in product.enrichment_missing_fields:
        issues.append(_issue(record, product, "enrichment", f"missing_{field}", field))
    return issues


def _issue(
    record: ProductSourceRecord,
    product: ProductSearchResult,
    severity: IssueSeverity,
    issue: str,
    detail: str,
) -> ExportQualityIssue:
    return ExportQualityIssue(
        severity=severity,
        issue=issue,
        source=product.source,
        source_product_id=product.source_product_id,
        source_brand_name=record.source_brand_name,
        brand_ko=product.brand_ko,
        brand_en=product.brand_en,
        product_name_ko=product.product_name_ko,
        product_name_display_ko=product.product_name_display_ko,
        detail=detail,
    )


def _is_brand_corrected(record: ProductSourceRecord, product: ProductSearchResult) -> bool:
    source_brand = clean_text(record.source_brand_name)
    if not source_brand or not product.brand_ko:
        return False
    return source_brand != product.brand_ko


def _parse_options(value: object) -> list[str] | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = [item.strip() for item in text.split("|")]
    if not isinstance(parsed, list):
        return None
    options = [option for item in parsed if (option := clean_text(item))]
    return options or None


def _parse_bool(value: object) -> bool | None:
    text = clean_text(value)
    if not text:
        return None
    normalized = text.casefold()
    if normalized in {"true", "t", "1", "yes", "y", "sold_out", "soldout"}:
        return True
    if normalized in {"false", "f", "0", "no", "n", "available", "in_stock", "instock"}:
        return False
    return None


def _parse_float(value: object) -> float | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _parse_int(value: object) -> int | None:
    parsed = _parse_float(value)
    if parsed is None:
        return None
    return int(parsed)


def _issue_sort_key(issue: ExportQualityIssue) -> tuple[int, str, str, str]:
    severity_rank = {"required": 0, "display": 1, "brand": 2, "enrichment": 3}
    return (
        severity_rank[issue.severity],
        issue.issue,
        issue.source,
        issue.product_name_display_ko or "",
    )
