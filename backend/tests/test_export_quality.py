from __future__ import annotations

import csv
import json

from app.ingestion.export_quality import build_export_quality_report


def test_export_quality_report_audits_normalized_display_and_brand_corrections(tmp_path) -> None:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "entries": [
                    {"official_en": "NOT4U", "aliases": ["낫포유"], "sources": []},
                    {"official_en": "CLIO", "aliases": ["클리오"], "sources": []},
                ]
            }
        ),
        encoding="utf-8",
    )
    export_path = tmp_path / "products_export.csv"
    with export_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
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
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "product_id": "A000000214971",
                "product_name": "[1위 속보습미스트] 뿌리는 바디로션 낫포유 크림 바디미스트 200ml",
                "brand_name": "뿌리는",
                "price": "15900",
                "discount_price": "15900",
                "rating": "4.7",
                "review_count": "1,203",
                "image_url": "https://image.example/not4u.jpg",
                "product_url": "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000214971",
                "options": json.dumps(["200ml", "리필 기획"], ensure_ascii=False),
                "sold_out": "false",
                "source": "oliveyoung",
            }
        )
        writer.writerow(
            {
                "product_id": "A000000121749",
                "product_name": "[6월 올영픽/단종부활템 증정] 클리오 킬 래쉬 수퍼프루프 마스카라 1+1기획 (+미니 속눈썹 영양제 증정)",
                "brand_name": "클리오",
                "price": "17400",
                "discount_price": "17400",
                "rating": "4.9",
                "review_count": "835",
                "image_url": "https://image.example/clio.jpg",
                "product_url": "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000121749",
                "options": '["01 롱 컬링", "02 볼륨 컬링"]',
                "sold_out": "true",
                "source": "oliveyoung",
            }
        )

    report = build_export_quality_report(
        export_path=export_path,
        registry_path=registry_path,
        base_url="https://www.oliveyoung.co.kr",
    )

    assert report.total == 2
    assert report.required_issue_count == 0
    assert report.display_issue_count == 0
    assert report.brand_corrected_count == 1
    assert report.display_cleaned_count == 2
    assert report.records_with_rating == 2
    assert report.records_with_review_count == 2
    assert report.records_with_options == 2
    assert report.sold_out_count == 1
    assert report.average_quality_score > 100
    assert report.enrichment_missing_fields == {"product_name_en": 2}
    assert any(
        issue.issue == "corrected_source_brand"
        and issue.source_brand_name == "뿌리는"
        and issue.brand_ko == "낫포유"
        for issue in report.issues
    )
