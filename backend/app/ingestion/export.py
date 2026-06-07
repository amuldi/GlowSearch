from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from pathlib import Path

from app.models.product import ProductSourceRecord


CSV_FIELDS = (
    "product_id",
    "product_name",
    "brand_name",
    "category",
    "price",
    "discount_price",
    "rating",
    "review_count",
    "image_url",
    "product_url",
    "description",
    "options",
    "sold_out",
    "source",
    "updated_at",
)


def write_products_csv(records: Iterable[ProductSourceRecord], output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow(_csv_row(record))
            count += 1
    return count


def _csv_row(record: ProductSourceRecord) -> dict[str, object | None]:
    return {
        "product_id": record.source_product_id,
        "product_name": record.product_name_ko,
        "brand_name": record.source_brand_name,
        "category": record.category,
        "price": record.regular_price,
        "discount_price": record.sale_price,
        "rating": record.rating,
        "review_count": record.review_count,
        "image_url": record.image_url,
        "product_url": record.source_url,
        "description": record.description,
        "options": json.dumps(record.options, ensure_ascii=False) if record.options else None,
        "sold_out": record.sold_out,
        "source": record.source,
        "updated_at": record.updated_at,
    }
