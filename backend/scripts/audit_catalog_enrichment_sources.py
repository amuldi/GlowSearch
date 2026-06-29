from __future__ import annotations

# ruff: noqa: E402

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import Settings
from app.ingestion.catalog_quality import (
    build_catalog_quality_report,
    filter_enrichment_targets,
)
from app.ingestion.source_evidence import (
    ProductImageEvidence,
    ProductNameEvidence,
    ProductPriceEvidence,
    extract_product_image_evidence,
    extract_product_name_evidence,
    extract_product_price_evidence,
    product_name_en_candidate,
    product_name_en_rejection_reason,
)

FIELDNAMES = (
    "priority",
    "field",
    "canonical_product_id",
    "source",
    "source_product_id",
    "product_name_display_ko",
    "source_url",
    "candidate_name",
    "candidate_language",
    "candidate_source",
    "usable_for_product_name_en",
    "usable_for_target_field",
    "candidate_image_url",
    "candidate_price",
    "candidate_currency",
    "candidate_rejection_reason",
    "evidence_count",
    "evidence_names",
    "evidence_languages",
    "error",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch enrichment target source URLs and report whether source-backed "
            "Latin product names are present. This script never writes catalog data."
        )
    )
    parser.add_argument("--catalog-path", type=Path, default=None)
    parser.add_argument("--registry-path", type=Path, default=None)
    parser.add_argument("--base-url", default="https://www.oliveyoung.co.kr")
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--field", action="append", default=[])
    parser.add_argument("--max-targets", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--format", choices=("csv", "json", "jsonl"), default="csv")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--only-usable",
        action="store_true",
        help="Only output rows with a source-backed Latin product name candidate.",
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    settings = Settings()
    report = await build_catalog_quality_report(
        catalog_path=args.catalog_path or settings.verified_catalog_path,
        registry_path=args.registry_path or settings.brand_registry_path,
        base_url=args.base_url,
        max_issues=0,
        max_targets=None,
    )
    targets = filter_enrichment_targets(
        report.enrichment_targets,
        sources=_split_filters(args.source),
        fields=_split_filters(args.field, default={"product_name_en"}),
    )
    if args.max_targets >= 0:
        targets = targets[: args.max_targets]

    rows: list[dict[str, str]] = []
    for priority, target in enumerate(targets, start=1):
        evidence: list[ProductNameEvidence] = []
        image_evidence: list[ProductImageEvidence] = []
        price_evidence: list[ProductPriceEvidence] = []
        error = ""
        if target.source_url:
            try:
                html = _fetch_text(target.source_url, timeout=args.timeout)
                evidence = extract_product_name_evidence(html)
                image_evidence = extract_product_image_evidence(html)
                price_evidence = extract_product_price_evidence(html)
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                error = f"{exc.__class__.__name__}: {exc}"
        candidate = product_name_en_candidate(
            evidence,
            rejected_names={
                target.brand_en or "",
                target.brand_ko or "",
                target.source,
                target.source.split(":", 1)[0],
            },
        )
        rejection_reason = ""
        if candidate is None:
            rejection_reason = (
                "fetch_error"
                if error and not evidence
                else product_name_en_rejection_reason(
                    evidence,
                    rejected_names={
                        target.brand_en or "",
                        target.brand_ko or "",
                        target.source,
                        target.source.split(":", 1)[0],
                    },
                )
            )
        image_candidate = image_evidence[0] if image_evidence else None
        price_candidate = _first_usable_price(price_evidence)
        usable = _target_has_candidate(
            target.field,
            product_name_candidate=candidate,
            image_candidate=image_candidate,
            price_candidate=price_candidate,
        )
        if not usable:
            rejection_reason = _candidate_rejection_reason_for_target(
                target.field,
                existing_reason=rejection_reason,
                error=error,
                evidence=evidence,
                image_evidence=image_evidence,
                price_evidence=price_evidence,
            )
        if args.only_usable and not usable:
            continue
        rows.append(
            {
                "priority": str(priority),
                "field": target.field,
                "canonical_product_id": target.canonical_product_id or "",
                "source": target.source,
                "source_product_id": target.source_product_id or "",
                "product_name_display_ko": target.product_name_display_ko or "",
                "source_url": target.source_url or "",
                "candidate_name": candidate.name if candidate else "",
                "candidate_language": candidate.language if candidate else "",
                "candidate_source": candidate.source if candidate else "",
                "usable_for_product_name_en": "true" if candidate else "false",
                "usable_for_target_field": "true" if usable else "false",
                "candidate_image_url": image_candidate.url if image_candidate else "",
                "candidate_price": price_candidate.price if price_candidate else "",
                "candidate_currency": price_candidate.currency if price_candidate else "",
                "candidate_rejection_reason": rejection_reason,
                "evidence_count": str(len(evidence)),
                "evidence_names": " | ".join(item.name for item in evidence[:5]),
                "evidence_languages": " | ".join(item.language for item in evidence[:5]),
                "error": error,
            }
        )

    payload = _render_rows(rows, output_format=args.format)
    if args.output is None:
        sys.stdout.write(payload)
        if payload and not payload.endswith("\n"):
            sys.stdout.write("\n")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")
    return 0


def _fetch_text(url: str, *, timeout: float) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "GlowSearch catalog source audit (+source-backed enrichment)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        body = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    return body.decode(charset, errors="replace")


def _split_filters(values: list[str], *, default: set[str] | None = None) -> set[str]:
    if not values:
        return default or set()
    return {
        item.strip()
        for value in values
        for item in value.split(",")
        if item.strip()
    }


def _render_rows(rows: list[dict[str, str]], *, output_format: str) -> str:
    if output_format == "json":
        return json.dumps(rows, ensure_ascii=False, indent=2)
    if output_format == "jsonl":
        return "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    if output_format == "csv":
        from io import StringIO

        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
        return buffer.getvalue()
    raise ValueError(f"Unsupported output format: {output_format}")


def _target_has_candidate(
    field: str,
    *,
    product_name_candidate: ProductNameEvidence | None,
    image_candidate: ProductImageEvidence | None,
    price_candidate: ProductPriceEvidence | None,
) -> bool:
    if field == "product_name_en":
        return product_name_candidate is not None
    if field == "image_url":
        return image_candidate is not None and _is_usable_image_url(image_candidate.url)
    if field == "price":
        return price_candidate is not None
    return False


def _candidate_rejection_reason_for_target(
    field: str,
    *,
    existing_reason: str,
    error: str,
    evidence: list[ProductNameEvidence],
    image_evidence: list[ProductImageEvidence],
    price_evidence: list[ProductPriceEvidence],
) -> str:
    if error and not evidence and not image_evidence and not price_evidence:
        return "fetch_error"
    if field == "image_url":
        if image_evidence:
            return "invalid_image_url_evidence"
        return "no_image_evidence"
    if field == "price":
        if price_evidence:
            return "non_positive_price_evidence"
        return "no_price_evidence"
    return existing_reason


def _first_usable_price(values: list[ProductPriceEvidence]) -> ProductPriceEvidence | None:
    for value in values:
        if _is_positive_price(value.price):
            return value
    return None


def _is_positive_price(value: str) -> bool:
    normalized = _numeric_price_text(value)
    if not normalized:
        return False
    try:
        return float(normalized) > 0
    except ValueError:
        return False


def _numeric_price_text(value: str) -> str:
    return "".join(char for char in value if char.isdigit() or char == ".").strip(".")


def _is_usable_image_url(value: str) -> bool:
    return value.startswith(("https://", "http://")) and not value.startswith(("https:https://", "http:http://"))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
