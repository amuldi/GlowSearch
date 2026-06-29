from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Literal

from app.data_collector.local_catalog import LocalVerifiedCatalogCollector
from app.indexing.store import SQLiteProductIndexStore
from app.models.product import ProductSearchResult
from app.models.product import ProductSourceRecord
from app.normalizer.brand import BrandResolver
from app.normalizer.product import ProductNormalizer

IssueSeverity = Literal["required", "enrichment", "display"]

ENRICHMENT_TARGET_EXPORT_FIELDS = (
    "priority",
    "field",
    "canonical_product_id",
    "source",
    "source_product_id",
    "brand_ko",
    "brand_en",
    "product_name_display_ko",
    "source_url",
    "search_query",
    "reason",
)

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

DIRTY_DISPLAY_PATTERNS = (
    (
        "dirty_display_sun_protection_suffix",
        re.compile(
            r"(?:^|\s)SPF\s*\d+\+?\s*,?(?:\s*/\s*PA\+{1,4}|\s+PA\+{1,4}|\s*,\s*PA\+{1,4})?(?:\s+\S.*)?$",
            flags=re.IGNORECASE,
        ),
    ),
    (
        "dirty_display_bundle_suffix",
        re.compile(
            r"\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s*(?:[*xX]\s*\d+\s*(?:ea|EA|입)?|\+\s*\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)(?:\s+\S.*)?|\+\s*\S+)\s*$",
            flags=re.IGNORECASE,
        ),
    ),
    (
        "dirty_display_volume_descriptor_suffix",
        re.compile(
            r"\d+(?:\.\d+)?\s*(?:g|ml|mL|ML)\s*(?:\*[A-Za-z가-힣0-9\s*]+|\s+증량)\s*$",
            flags=re.IGNORECASE,
        ),
    ),
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
class CatalogEnrichmentTarget:
    field: str
    source: str
    source_product_id: str | None
    canonical_product_id: str | None
    brand_ko: str | None
    brand_en: str | None
    product_name_display_ko: str | None
    source_url: str | None
    reason: str


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
    enrichment_target_count: int
    enrichment_targets: list[CatalogEnrichmentTarget]
    product_name_en_target_count: int
    product_name_en_targets: list[CatalogEnrichmentTarget]
    issues: list[CatalogQualityIssue]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["enrichment_targets"] = [asdict(target) for target in self.enrichment_targets]
        payload["product_name_en_targets"] = [asdict(target) for target in self.product_name_en_targets]
        payload["issues"] = [asdict(issue) for issue in self.issues]
        return payload


def enrichment_target_export_rows(
    targets: list[CatalogEnrichmentTarget],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for priority, target in enumerate(targets, start=1):
        rows.append(
            {
                "priority": str(priority),
                "field": target.field,
                "canonical_product_id": target.canonical_product_id or "",
                "source": target.source,
                "source_product_id": target.source_product_id or "",
                "brand_ko": target.brand_ko or "",
                "brand_en": target.brand_en or "",
                "product_name_display_ko": target.product_name_display_ko or "",
                "source_url": target.source_url or "",
                "search_query": _target_search_query(target),
                "reason": target.reason,
            }
        )
    return rows


def filter_enrichment_targets(
    targets: list[CatalogEnrichmentTarget],
    *,
    sources: set[str] | None = None,
    fields: set[str] | None = None,
) -> list[CatalogEnrichmentTarget]:
    source_filters = {_normalize_filter_value(source) for source in sources or set() if source.strip()}
    field_filters = {_normalize_filter_value(field) for field in fields or set() if field.strip()}
    return [
        target
        for target in targets
        if _target_matches_filters(target, sources=source_filters, fields=field_filters)
    ]


async def build_catalog_quality_report(
    *,
    catalog_path: Path,
    registry_path: Path,
    base_url: str,
    max_issues: int | None = 50,
    max_targets: int | None = 50,
) -> CatalogQualityReport:
    collector = LocalVerifiedCatalogCollector(catalog_path)
    normalizer = ProductNormalizer(BrandResolver(registry_path), base_url=base_url)
    try:
        records = await collector.all_records()
        products = [normalizer.normalize(record) for record in records]
        return _build_quality_report_from_records(
            source_path=str(catalog_path),
            records=records,
            products=products,
            max_issues=max_issues,
            max_targets=max_targets,
        )
    finally:
        normalizer.close()


async def build_index_quality_report(
    *,
    index_path: Path,
    registry_path: Path,
    base_url: str,
    limit: int | None = None,
    max_issues: int | None = 50,
    max_targets: int | None = 50,
) -> CatalogQualityReport:
    store = SQLiteProductIndexStore(index_path)
    normalizer = ProductNormalizer(BrandResolver(registry_path), base_url=base_url)
    try:
        records = await store.all_products(limit=limit)
        products = [normalizer.normalize(record) for record in records]
        return _build_quality_report_from_records(
            source_path=str(index_path),
            records=records,
            products=products,
            max_issues=max_issues,
            max_targets=max_targets,
        )
    finally:
        normalizer.close()
        await store.close()


def _build_quality_report_from_records(
    *,
    source_path: str,
    records: list[ProductSourceRecord],
    products: list[ProductSearchResult],
    max_issues: int | None,
    max_targets: int | None,
) -> CatalogQualityReport:
    canonical_ids_with_product_name_en = {
        product.canonical_product_id for product in products if product.canonical_product_id and product.product_name_en
    }
    source_counts: Counter[str] = Counter()
    enrichment_missing_fields: Counter[str] = Counter()
    issues: list[CatalogQualityIssue] = []
    enrichment_targets_by_key: dict[str, CatalogEnrichmentTarget] = {}
    product_name_en_targets_by_key: dict[str, CatalogEnrichmentTarget] = {}
    product_name_en_count = 0
    display_cleaned_count = 0
    product_name_display_ko_override_count = 0
    product_name_display_en_override_count = 0
    quality_score_total = 0

    for record, product in zip(records, products, strict=True):
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
        product_name_en_target = _product_name_en_target(
            product,
            canonical_ids_with_product_name_en=canonical_ids_with_product_name_en,
        )
        if product_name_en_target is not None:
            _set_best_target(enrichment_targets_by_key, product_name_en_target)
            target_key = _target_key(product_name_en_target)
            existing_target = product_name_en_targets_by_key.get(target_key)
            if existing_target is None or _target_sort_key(product_name_en_target) < _target_sort_key(
                existing_target
            ):
                product_name_en_targets_by_key[target_key] = product_name_en_target
        for field in product.enrichment_missing_fields:
            if field == "product_name_en":
                continue
            target = _missing_field_target(product, field)
            if target is not None:
                _set_best_target(enrichment_targets_by_key, target)
        issues.extend(_required_issues(product))
        issues.extend(_display_issues(product))
        issues.extend(_enrichment_issues(product))

    sorted_issues = sorted(issues, key=_issue_sort_key)
    if max_issues is not None and max_issues >= 0:
        sorted_issues = sorted_issues[:max_issues]
    enrichment_targets = sorted(enrichment_targets_by_key.values(), key=_target_sort_key)
    enrichment_target_count = len(enrichment_targets)
    product_name_en_targets = sorted(product_name_en_targets_by_key.values(), key=_target_sort_key)
    product_name_en_target_count = len(product_name_en_targets)
    if max_targets is not None and max_targets >= 0:
        enrichment_targets = enrichment_targets[:max_targets]
        product_name_en_targets = product_name_en_targets[:max_targets]
    total = len(records)
    return CatalogQualityReport(
        catalog_path=source_path,
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
        enrichment_target_count=enrichment_target_count,
        enrichment_targets=enrichment_targets,
        product_name_en_target_count=product_name_en_target_count,
        product_name_en_targets=product_name_en_targets,
        issues=sorted_issues,
    )


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
    issues: list[CatalogQualityIssue] = []
    if any(marker in display_name for marker in DIRTY_DISPLAY_MARKERS):
        issues.append(_issue(product, "display", "dirty_display_name", display_name))
    for issue_name, pattern in DIRTY_DISPLAY_PATTERNS:
        if pattern.search(display_name):
            issues.append(_issue(product, "display", issue_name, display_name))
            break
    if _has_brand_prefix(display_name, product):
        issues.append(_issue(product, "display", "brand_prefixed_display_name", display_name))
    return issues


def _has_brand_prefix(display_name: str, product: ProductSearchResult) -> bool:
    display_key = _display_key(display_name)
    if not display_key:
        return False
    for brand in [product.brand_ko, product.brand_en]:
        brand_key = _display_key(brand)
        if not brand_key:
            continue
        if display_key != brand_key and display_key.startswith(brand_key):
            return True
    return False


def _display_key(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", value).casefold()


def _enrichment_issues(product: ProductSearchResult) -> list[CatalogQualityIssue]:
    issues: list[CatalogQualityIssue] = []
    for field in product.enrichment_missing_fields:
        issues.append(_issue(product, "enrichment", f"missing_{field}", field))
    return issues


def _product_name_en_target(
    product: ProductSearchResult,
    *,
    canonical_ids_with_product_name_en: set[str | None],
) -> CatalogEnrichmentTarget | None:
    if product.product_name_en:
        return None
    if product.canonical_product_id in canonical_ids_with_product_name_en:
        return None
    if not product.product_name_display_ko and not product.product_name_ko:
        return None
    reason_parts = ["product_name_en missing"]
    if product.source_url:
        reason_parts.append("source_url available")
    if product.brand_en:
        reason_parts.append("brand_en available")
    return CatalogEnrichmentTarget(
        field="product_name_en",
        source=product.source,
        source_product_id=product.source_product_id,
        canonical_product_id=product.canonical_product_id,
        brand_ko=product.brand_ko,
        brand_en=product.brand_en,
        product_name_display_ko=product.product_name_display_ko or product.product_name_ko,
        source_url=product.source_url,
        reason=", ".join(reason_parts),
    )


def _missing_field_target(product: ProductSearchResult, field: str) -> CatalogEnrichmentTarget | None:
    if field not in {"brand_en", "image_url", "price"}:
        return None
    if not product.product_name_display_ko and not product.product_name_ko and not product.product_name_en:
        return None
    reason_parts = [f"{field} missing"]
    if product.source_url:
        reason_parts.append("source_url available")
    if product.source_product_id:
        reason_parts.append("source_product_id available")
    return CatalogEnrichmentTarget(
        field=field,
        source=product.source,
        source_product_id=product.source_product_id,
        canonical_product_id=product.canonical_product_id,
        brand_ko=product.brand_ko,
        brand_en=product.brand_en,
        product_name_display_ko=product.product_name_display_ko or product.product_name_ko or product.product_name_en,
        source_url=product.source_url,
        reason=", ".join(reason_parts),
    )


def _target_key(target: CatalogEnrichmentTarget) -> str:
    prefix = target.field
    if target.canonical_product_id:
        if target.field == "product_name_en":
            return f"{prefix}:{target.canonical_product_id}"
        return f"{prefix}:{target.canonical_product_id}:{target.source}"
    return prefix + ":" + ":".join(
        value
        for value in [
            target.source,
            target.source_product_id,
            target.product_name_display_ko,
        ]
        if value
    )


def _set_best_target(
    targets_by_key: dict[str, CatalogEnrichmentTarget],
    target: CatalogEnrichmentTarget,
) -> None:
    target_key = _target_key(target)
    existing_target = targets_by_key.get(target_key)
    if existing_target is None or _target_sort_key(target) < _target_sort_key(existing_target):
        targets_by_key[target_key] = target


def _target_sort_key(target: CatalogEnrichmentTarget) -> tuple[int, int, int, str, str]:
    source_rank = {"official": 0, "oliveyoung-global": 1, "musinsa": 2, "oliveyoung": 3}
    field_rank = {"product_name_en": 0, "brand_en": 1, "image_url": 2, "price": 3}
    return (
        field_rank.get(target.field, 9),
        0 if target.source_url else 1,
        source_rank.get(target.source.split(":", 1)[0], 9),
        target.brand_ko or target.brand_en or "",
        target.product_name_display_ko or "",
    )


def _target_search_query(target: CatalogEnrichmentTarget) -> str:
    return " ".join(
        value
        for value in [
            target.brand_en,
            target.brand_ko,
            target.product_name_display_ko,
        ]
        if value
    )


def _target_matches_filters(
    target: CatalogEnrichmentTarget,
    *,
    sources: set[str],
    fields: set[str],
) -> bool:
    if fields and _normalize_filter_value(target.field) not in fields:
        return False
    if not sources:
        return True
    target_source = _normalize_filter_value(target.source)
    target_source_prefix = _normalize_filter_value(target.source.split(":", 1)[0])
    return target_source in sources or target_source_prefix in sources


def _normalize_filter_value(value: str) -> str:
    return value.strip().lower()


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
