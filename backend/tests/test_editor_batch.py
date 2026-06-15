import sqlite3

import httpx
import pytest

from app.cache.ttl import AsyncTTLCache
from app.api.main import create_app
from app.editor.batch import EditorBatchService
from app.editor.parser import parse_editor_line, parse_editor_lines
from app.indexing.store import SQLiteProductIndexStore
from app.models.product import ProductSearchResult, ProductSourceRecord, SearchResponse
from app.normalizer.brand import BrandResolver
from app.normalizer.product import ProductNormalizer
from app.service.factory import get_search_service
from app.service.search_service import SearchService, _CollectedResult


class EditorFakeCollector:
    name = "editor-fake"

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        if "없는" in keyword:
            return []
        if "후보" in keyword:
            return [
                ProductSourceRecord(
                    source_brand_name="롬앤",
                    source_brand_name_en="rom&nd",
                    product_name_ko="롬앤 베러 댄 쉐딩 그레이쿨",
                    product_name_en=None,
                    shade="그레이쿨",
                    regular_price=13000,
                    image_url="https://example.test/romand.jpg",
                    source="oliveyoung",
                    source_url="https://oliveyoung.example/products/1",
                    source_product_id="oliveyoung-1",
                ),
                ProductSourceRecord(
                    source_brand_name="롬앤",
                    source_brand_name_en="rom&nd",
                    product_name_ko="롬앤 베러 댄 쉐딩 오트그레인",
                    product_name_en=None,
                    shade="오트그레인",
                    regular_price=13000,
                    image_url="https://example.test/romand-2.jpg",
                    source="musinsa",
                    source_url="https://musinsa.example/products/2",
                    source_product_id="musinsa-2",
                ),
            ]
        if "노링크" in keyword:
            return [
                ProductSourceRecord(
                    source_brand_name="노링크브랜드",
                    source_brand_name_en="No Link Brand",
                    product_name_ko="노링크브랜드 노링크제품",
                    shade="13N1",
                    regular_price=60000,
                    source="oliveyoung",
                    source_product_id="no-link-1",
                )
            ]
        return [
            ProductSourceRecord(
                source_brand_name="헤라",
                source_brand_name_en="HERA",
                product_name_ko="헤라 파우더 13N1",
                product_name_en="HERA Powder",
                shade="13N1",
                regular_price=60000,
                image_url="https://example.test/hera.jpg",
                source="oliveyoung",
                source_url="https://oliveyoung.example/products/hera",
                source_product_id="hera-1",
            )
        ]


class EditorRouteSearchService:
    async def search(self, query, criteria):
        return SearchResponse(
            query=query,
            count=1,
            results=[
                ProductSearchResult(
                    brand_ko="헤라",
                    brand_en="HERA",
                    product_name_ko="헤라 파우더 13N1",
                    product_name_en=None,
                    shade="13N1",
                    source="oliveyoung",
                    source_url="https://oliveyoung.example/products/hera",
                    source_product_id="hera-1",
                    quality_score=80,
                )
            ],
        )


@pytest.mark.asyncio
async def test_editor_batch_api_returns_line_items() -> None:
    app = create_app()
    app.dependency_overrides[get_search_service] = lambda: EditorRouteSearchService()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/editor/batch", json={"text": "헤라 파우더 #13N1"})

    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["parsed"]["shade_code"] == "13N1"
    assert payload["items"][0]["candidates"][0]["product"]["source_url"]


def test_parse_editor_lines_splits_batch_input() -> None:
    parsed = parse_editor_lines("헤라 파우더 #13N1\n\n롬앤 쉐딩 #그레이쿨")

    assert [item.raw_text for item in parsed] == ["헤라 파우더 #13N1", "롬앤 쉐딩 #그레이쿨"]


@pytest.mark.parametrize(
    ("raw", "shade_code", "shade_name", "normalized_query"),
    [
        ("헤라 파우더 #13N1", "13N1", None, "헤라 파우더"),
        ("페리페라 포근 픽싱 틴트 19호", "19호", None, "페리페라 포근 픽싱 틴트"),
        ("아멜리 하이라이터 #432", "432", None, "아멜리 하이라이터"),
        ("롬앤 쉐딩 #그레이쿨", None, "그레이쿨", "롬앤 쉐딩"),
        ("캔메이크 아라 카푸치노", None, "카푸치노", "캔메이크 아라"),
    ],
)
def test_parse_editor_line_extracts_shade(
    raw: str,
    shade_code: str | None,
    shade_name: str | None,
    normalized_query: str,
) -> None:
    parsed = parse_editor_line(raw)

    assert parsed.shade_code == shade_code
    assert parsed.shade_name == shade_name
    assert parsed.normalized_query == normalized_query


@pytest.mark.asyncio
async def test_editor_batch_returns_statuses_and_filters_candidates_without_source_url(tmp_path) -> None:
    service = _editor_service(tmp_path)

    response = await service.batch(
        "헤라 파우더 #13N1\n롬앤 후보 #그레이쿨\n노링크브랜드 노링크제품\n없는 상품",
        limit=5,
    )

    assert response.count == 4
    assert response.items[0].status == "확인됨"
    assert response.items[0].candidates[0].product.brand_en == "HERA"
    assert response.items[0].candidates[0].product.product_name_en == "HERA Powder"
    assert response.items[1].status == "후보 있음"
    assert [candidate.product.shade for candidate in response.items[1].candidates] == [
        "그레이쿨",
        "오트그레인",
    ]
    assert response.items[2].status == "수동 확인 필요"
    assert response.items[2].candidates == []
    assert response.items[3].status == "수동 확인 필요"
    assert "미확인" not in response.model_dump_json()
    assert "Unknown" not in response.model_dump_json()
    assert "N/A" not in response.model_dump_json()


@pytest.mark.asyncio
async def test_editor_batch_does_not_generate_english_product_name(tmp_path) -> None:
    service = _editor_service(tmp_path)

    response = await service.batch("롬앤 후보 #그레이쿨", limit=5)

    assert response.items[0].candidates[0].product.product_name_en is None


def test_product_index_prepares_editor_confirmed_mappings_table(tmp_path) -> None:
    db_path = tmp_path / "product_index.sqlite3"
    SQLiteProductIndexStore(db_path)

    connection = sqlite3.connect(db_path)
    table = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'editor_confirmed_mappings'"
    ).fetchone()
    connection.close()

    assert table is not None


def _editor_service(tmp_path) -> EditorBatchService:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        (
            '{"entries":['
            '{"official_en":"HERA","aliases":["헤라"],"sources":[]},'
            '{"official_en":"rom&nd","aliases":["롬앤"],"sources":[]}'
            "]}"
        ),
        encoding="utf-8",
    )
    search_service = SearchService(
        collectors=[EditorFakeCollector()],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
    )
    return EditorBatchService(search_service)
