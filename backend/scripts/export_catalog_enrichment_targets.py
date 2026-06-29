from __future__ import annotations

# ruff: noqa: E402

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import Settings
from app.ingestion.catalog_quality import (
    ENRICHMENT_TARGET_EXPORT_FIELDS,
    build_catalog_quality_report,
    enrichment_target_export_rows,
    filter_enrichment_targets,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export source-backed catalog enrichment targets for small batch review."
    )
    parser.add_argument(
        "--catalog-path",
        type=Path,
        default=None,
        help="verified_products.json path. Defaults to Settings().verified_catalog_path.",
    )
    parser.add_argument(
        "--registry-path",
        type=Path,
        default=None,
        help="brand_registry.json path. Defaults to Settings().brand_registry_path.",
    )
    parser.add_argument(
        "--base-url",
        default="https://www.oliveyoung.co.kr",
        help="Base URL used for relative source/image URLs during normalization.",
    )
    parser.add_argument(
        "--max-targets",
        type=int,
        default=40,
        help="Maximum target rows to export. Use -1 for all targets.",
    )
    parser.add_argument(
        "--format",
        choices=("csv", "json", "jsonl"),
        default="csv",
        help="Output format.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file. Defaults to stdout.",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help=(
            "Filter by source prefix or source name. Can be repeated or comma-separated, "
            "for example --source official --source musinsa,oliveyoung."
        ),
    )
    parser.add_argument(
        "--field",
        action="append",
        default=[],
        help=(
            "Filter by enrichment field. Can be repeated or comma-separated. "
            "Supported fields include product_name_en, brand_en, image_url, and price."
        ),
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
        fields=_split_filters(args.field),
    )
    if args.max_targets >= 0:
        targets = targets[: args.max_targets]
    rows = enrichment_target_export_rows(targets)
    payload = _render_rows(rows, output_format=args.format)
    if args.output is None:
        sys.stdout.write(payload)
        if payload and not payload.endswith("\n"):
            sys.stdout.write("\n")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")
    return 0


def _render_rows(rows: list[dict[str, str]], *, output_format: str) -> str:
    if output_format == "json":
        return json.dumps(rows, ensure_ascii=False, indent=2)
    if output_format == "jsonl":
        return "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    if output_format == "csv":
        return _render_csv(rows)
    raise ValueError(f"Unsupported output format: {output_format}")


def _split_filters(values: list[str]) -> set[str]:
    return {
        item.strip()
        for value in values
        for item in value.split(",")
        if item.strip()
    }


def _render_csv(rows: list[dict[str, str]]) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=ENRICHMENT_TARGET_EXPORT_FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
