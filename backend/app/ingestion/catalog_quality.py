from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from app.data_collector.local_catalog import LocalVerifiedCatalogCollector
from app.models.product import ProductSearchResult
from app.normalizer.brand import BrandResolver
from app.normalizer.product import ProductNormalizer

IssueSeverity = Literal["required", "enrichment", "display"]

DIRTY_DISPLAY_MARKERS = (
    "[",
    "]",
    "기획",
    "단품",
    "택1",
    "Colors",
    "colors",
    "종",
    "(",
    ")",
)


@dataclass(frozen=True)
class CatalogQualityIssue:
    severity: IssueSeverity
    issue: str
    source: str
    source_product_id: str | None
    canonical_product_id: str | None
    brand_ko: str | None
    brand_en: str | None
    product_name_ko: str | None
    product_name_display_ko: str | None
    detail: str


@dataclass(frozen=True)
class CatalogQualityReport:
    catalog_path: str
    total: int
    source_counts: dict[str, int]
    required_issue_count: int
    enrichment_issue_count: int
    display_issue_count: int
    product_name_en_count: int
    display_cleaned_count: int
    product_name_display_ko_override_count: int
    product_name_display_en_override_count: int
    average_quality_score: float
    enrichment_missing_fields: dict[str, int]
    issues: list[CatalogQualityIssue]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["issues"] = [asdict(issue) for issue in self.issues]
        return payload


async def build_catalog_quality_report(
    *,
    catalog_path: Path,
    registry_path: Path,
    base_url: str,
    max_issues: int | None = 50,
) -> CatalogQualityReport:
    collector = LocalVerifiedCatalogCollector(catalog_path)
    normalizer = ProductNormalizer(BrandResolver(registry_path), base_url=base_url)
    try:
        records = await collector.all_records()
        source_counts: Counter[str] = Counter()
        enrichment_missing_fields: Counter[str] = Counter()
        issues: list[CatalogQualityIssue] = []
        product_name_en_count = 0
        display_cleaned_count = 0
        product_name_display_ko_override_count = 0
        product_name_display_en_override_count = 0
        quality_score_total = 0

        for record in records:
            product = normalizer.normalize(record)
            source_counts[product.source.split(":", 1)[0]] += 1
            quality_score_total += product.quality_score
            if product.product_name_en:
                product_name_en_count += 1
            if (
                product.product_name_ko
                and product.product_name_display_ko
                and product.product_name_ko != product.product_name_display_ko
            ):
                display_cleaned_count += 1
            if record.product_name_display_ko:
                product_name_display_ko_override_count += 1
            if record.product_name_display_en:
                product_name_display_en_override_count += 1
            enrichment_missing_fields.update(product.enrichment_missing_fields)
            issues.extend(_required_issues(product))
            issues.extend(_display_issues(product))
            issues.extend(_enrichment_issues(product))

        sorted_issues = sorted(issues, key=_issue_sort_key)
        if max_issues is not None and max_issues >= 0:
            sorted_issues = sorted_issues[:max_issues]
        total = len(records)
        return CatalogQualityReport(
            catalog_path=str(catalog_path),
            total=total,
            source_counts=dict(sorted(source_counts.items())),
            required_issue_count=sum(1 for issue in issues if issue.severity == "required"),
            enrichment_issue_count=sum(1 for issue in issues if issue.severity == "enrichment"),
            display_issue_count=sum(1 for issue in issues if issue.severity == "display"),
            product_name_en_count=product_name_en_count,
            display_cleaned_count=display_cleaned_count,
            product_name_display_ko_override_count=product_name_display_ko_override_count,
            product_name_display_en_override_count=product_name_display_en_override_count,
            average_quality_score=round(quality_score_total / total, 2) if total else 0.0,
            enrichment_missing_fields=dict(sorted(enrichment_missing_fields.items())),
            issues=sorted_issues,
        )
    finally:
        normalizer.close()


def _required_issues(product: ProductSearchResult) -> list[CatalogQualityIssue]:
    issues: list[CatalogQualityIssue] = []
    if not product.product_name_ko and not product.product_name_en:
        issues.append(_issue(product, "required", "missing_product_name", "product_name_ko/product_name_en missing"))
    if not product.source:
        issues.append(_issue(product, "required", "missing_source", "source missing"))
    if not product.source_url and not product.source_product_id:
        issues.append(_issue(product, "required", "missing_source_locator", "source_url/source_product_id missing"))
    return issues


def _display_issues(product: ProductSearchResult) -> list[CatalogQualityIssue]:
    display_name = product.product_name_display_ko
    if not display_name:
        return []
    if any(marker in display_name for marker in DIRTY_DISPLAY_MARKERS):
        return [_issue(product, "display", "dirty_display_name", display_name)]
    return []


def _enrichment_issues(product: ProductSearchResult) -> list[CatalogQualityIssue]:
    issues: list[CatalogQualityIssue] = []
    for field in product.enrichment_missing_fields:
        issues.append(_issue(product, "enrichment", f"missing_{field}", field))
    return issues


def _issue(
    product: ProductSearchResult,
    severity: IssueSeverity,
    issue: str,
    detail: str,
) -> CatalogQualityIssue:
    return CatalogQualityIssue(
        severity=severity,
        issue=issue,
        source=product.source,
        source_product_id=product.source_product_id,
        canonical_product_id=product.canonical_product_id,
        brand_ko=product.brand_ko,
        brand_en=product.brand_en,
        product_name_ko=product.product_name_ko,
        product_name_display_ko=product.product_name_display_ko,
        detail=detail,
    )


def _issue_sort_key(issue: CatalogQualityIssue) -> tuple[int, str, str, str]:
    severity_rank = {"required": 0, "display": 1, "enrichment": 2}
    return (
        severity_rank[issue.severity],
        issue.issue,
        issue.source,
        issue.product_name_display_ko or "",
    )
