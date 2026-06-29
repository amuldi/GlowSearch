from __future__ import annotations

# ruff: noqa: E402

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import Settings
from app.ingestion.export_quality import build_export_quality_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit exported product CSV normalization quality before catalog/index promotion."
    )
    parser.add_argument(
        "--export-path",
        type=Path,
        default=PROJECT_ROOT / "data" / "products_export.csv",
        help="products_export.csv path.",
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
        "--max-issues",
        type=int,
        default=80,
        help="Maximum number of issue rows to include. Use -1 for all issues.",
    )
    parser.add_argument(
        "--fail-on-required",
        action="store_true",
        help="Exit 1 when required exported fields are missing after normalization.",
    )
    parser.add_argument(
        "--fail-on-dirty-display",
        action="store_true",
        help="Exit 1 when normalized display names still contain retail/promo markers.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = Settings()
    report = build_export_quality_report(
        export_path=args.export_path,
        registry_path=args.registry_path or settings.brand_registry_path,
        base_url=args.base_url,
        max_issues=None if args.max_issues < 0 else args.max_issues,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))

    if args.fail_on_required and report.required_issue_count:
        return 1
    if args.fail_on_dirty_display and report.display_issue_count:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
