import asyncio
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
        if "페리페라 포근" in keyword:
            return []
        if keyword == "포근 픽싱 틴트":
            return [
                ProductSourceRecord(
                    source_brand_name="에뛰드",
                    source_brand_name_en="ETUDE",
                    product_name_ko="에뛰드 포근 픽싱 틴트 17 Colors",
                    product_name_en=None,
                    shade=None,
                    regular_price=16000,
                    image_url="https://example.test/etude.jpg",
                    source="oliveyoung",
                    source_url="https://oliveyoung.example/products/etude-fixing-tint",
                    source_product_id="etude-fixing-tint-1",
                )
            ]
        if "쉐딩" in keyword:
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
        if "테스트" in keyword:
            return [
                ProductSourceRecord(
                    source_brand_name="헤라",
                    source_brand_name_en="HERA",
                    product_name_ko="헤라 테스트 13 Colors",
                    product_name_en=None,
                    regular_price=60000,
                    image_url="https://example.test/hera-colors.jpg",
                    source="oliveyoung",
                    source_url="https://oliveyoung.example/products/hera-colors",
                    source_product_id="hera-colors-1",
                )
            ]
        if "치즈냥이" in keyword:
            return [
                ProductSourceRecord(
                    canonical_product_id="verified:clio-pro-eye-palette-air-mogamju-library",
                    source_brand_name="클리오",
                    source_brand_name_en="CLIO",
                    product_name_ko="(클리오X국가유산청) 프로 아이 팔레트 에어",
                    product_name_en=None,
                    shade="21 모감주 밑 서재",
                    regular_price=34000,
                    source="glowpick",
                    source_url="https://glowpick.example/products/183245",
                    source_product_id="glowpick-183245",
                    search_keywords=["치즈냥이", "모감주 도서관"],
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


class SlowEditorSearchService:
    async def search(self, query, criteria):
        await asyncio.sleep(1)
        return SearchResponse(query=query, count=0, results=[])

    def resolve_brand_en(self, brand: str) -> str | None:
        return "HERA" if brand == "헤라" else None


class ShadeAwareEditorSearchService:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, query, criteria):
        self.queries.append(query)
        if query != "롬앤 쉐딩 그레이쿨":
            return SearchResponse(query=query, count=0, results=[])
        return SearchResponse(
            query=query,
            count=1,
            results=[
                ProductSearchResult(
                    canonical_product_id="verified:romand-better-than-shape-shading",
                    brand_ko="롬앤",
                    brand_en="rom&nd",
                    product_name_ko="롬앤 베러 댄 쉐입 쉐딩",
                    product_name_en=None,
                    shade=None,
                    source="oliveyoung",
                    source_url="https://oliveyoung.example/products/romand-shading",
                    source_product_id="romand-shading",
                    quality_score=98,
                    search_keywords=["그레이쿨"],
                )
            ],
        )

    def resolve_brand_en(self, brand: str) -> str | None:
        return "rom&nd" if brand == "롬앤" else None


class ShadeFallbackEditorSearchService:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, query, criteria):
        self.queries.append(query)
        if query != "헤라 파우더":
            return SearchResponse(query=query, count=0, results=[])
        return SearchResponse(
            query=query,
            count=1,
            results=[
                ProductSearchResult(
                    canonical_product_id="verified:hera-soft-finish-loose-powder-15g",
                    brand_ko="헤라",
                    brand_en="HERA",
                    product_name_ko="헤라 소프트 피니시 루스 파우더 15g",
                    product_name_en=None,
                    shade=None,
                    source="oliveyoung",
                    source_url="https://oliveyoung.example/products/hera-powder",
                    source_product_id="hera-powder",
                    quality_score=98,
                    search_keywords=["헤라 파우더"],
                )
            ],
        )

    def resolve_brand_en(self, brand: str) -> str | None:
        return "HERA" if brand == "헤라" else None


class EyelinerAbbreviationEditorSearchService:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, query, criteria):
        self.queries.append(query)
        if query != "캔메이크 아라":
            return SearchResponse(query=query, count=0, results=[])
        return SearchResponse(
            query=query,
            count=1,
            results=[
                ProductSearchResult(
                    canonical_product_id="verified:canmake-creamy-touch-liner",
                    brand_ko="캔메이크",
                    brand_en="CANMAKE",
                    product_name_ko="[신상출시/초슬림라이너] 캔메이크 크리미 터치 라이너 10종 택1",
                    product_name_en=None,
                    shade=None,
                    source="oliveyoung",
                    source_url="https://oliveyoung.example/products/canmake-liner",
                    source_product_id="canmake-liner",
                    quality_score=98,
                )
            ],
        )

    def resolve_brand_en(self, brand: str) -> str | None:
        return "CANMAKE" if brand == "캔메이크" else None


class BrandMismatchFallbackEditorSearchService:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, query, criteria):
        self.queries.append(query)
        if query != "하이라이터":
            return SearchResponse(query=query, count=0, results=[])
        return SearchResponse(
            query=query,
            count=1,
            results=[
                ProductSearchResult(
                    canonical_product_id="verified:ofra-mini-highlighter",
                    brand_ko="오프라",
                    brand_en="OFRA Cosmetics",
                    product_name_ko="오프라 미니 하이라이터",
                    product_name_en=None,
                    shade=None,
                    source="oliveyoung",
                    source_url="https://oliveyoung.example/products/ofra-highlighter",
                    source_product_id="ofra-highlighter",
                    quality_score=98,
                )
            ],
        )

    def resolve_brand_en(self, brand: str) -> str | None:
        return "AMELI" if brand == "아멜리" else None


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


@pytest.mark.asyncio
async def test_editor_confirm_api_saves_mapping(tmp_path) -> None:
    service = _editor_service(tmp_path)
    app = create_app()
    app.dependency_overrides[get_search_service] = lambda: service._search_service
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/editor/confirm",
            json={
                "raw_text": "헤라 파우더 #13N1",
                "normalized_query": "헤라 파우더",
                "source": "oliveyoung",
                "source_url": "https://oliveyoung.example/products/hera",
                "source_product_id": "hera-1",
                "brand_ko": "헤라",
                "brand_en": "HERA",
                "product_name_ko": "헤라 파우더 13N1",
                "product_name_en": "HERA Powder",
                "shade": "13N1",
            },
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"saved": True}


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
        "헤라 파우더 #13N1\n롬앤 쉐딩 #그레이쿨\n노링크브랜드 노링크제품\n없는 상품",
        limit=5,
    )

    assert response.count == 4
    assert response.items[0].status == "확인됨"
    assert response.items[0].candidates[0].product.brand_en == "HERA"
    assert response.items[0].candidates[0].product.product_name_en == "HERA Powder"
    assert "브랜드 일치" in response.items[0].candidates[0].match_reasons
    assert "호수/컬러 일치" in response.items[0].candidates[0].match_reasons
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

    response = await service.batch("롬앤 쉐딩 #그레이쿨", limit=5)

    assert response.items[0].candidates[0].product.product_name_en is None


@pytest.mark.asyncio
async def test_editor_batch_does_not_confirm_candidate_without_requested_shade(tmp_path) -> None:
    service = _editor_service(tmp_path)

    response = await service.batch("헤라 테스트 #13N1", limit=5)

    assert response.items[0].status == "후보 있음"
    assert response.items[0].candidates[0].product.shade is None


@pytest.mark.asyncio
async def test_editor_batch_drops_product_fallback_brand_mismatch_candidates(
    tmp_path,
) -> None:
    service = _editor_service(tmp_path)

    response = await service.batch("페리페라 포근 픽싱 틴트 19호", limit=5)

    assert response.items[0].parsed.brand_query == "페리페라"
    assert response.items[0].status == "수동 확인 필요"
    assert response.items[0].candidates == []


@pytest.mark.asyncio
async def test_editor_batch_includes_registry_brand_en_without_candidate(tmp_path) -> None:
    service = _editor_service(tmp_path)

    response = await service.batch("헤라 없는제품", limit=5)

    assert response.items[0].status == "수동 확인 필요"
    assert response.items[0].parsed.brand_query == "헤라"
    assert response.items[0].parsed.brand_en == "HERA"
    assert response.items[0].candidates == []


@pytest.mark.asyncio
async def test_editor_batch_uses_catalog_keywords_without_exposing_them(tmp_path) -> None:
    service = _editor_service(tmp_path)

    response = await service.batch("클리오 치즈냥이", limit=5)

    assert response.items[0].status == "확인됨"
    candidate = response.items[0].candidates[0]
    assert candidate.product.brand_ko == "클리오"
    assert candidate.product.shade == "21 모감주 밑 서재"
    assert "제품 키워드 1/1" in candidate.match_reasons
    assert "치즈냥이" not in candidate.product.model_dump_json()


@pytest.mark.asyncio
async def test_editor_batch_records_manual_review_search_gap(tmp_path) -> None:
    service = _editor_service(tmp_path)

    response = await service.batch("없는 제품", limit=3)
    await service._search_service.drain_background_tasks()
    gaps = await service._search_service.recent_search_gaps(limit=10)
    jobs = await service._search_service.recent_catalog_jobs(limit=10)

    assert response.items[0].status == "수동 확인 필요"
    assert gaps[0]["query"] == "없는 제품"
    assert gaps[0]["last_reason"] == "editor_manual_review"
    assert jobs[0]["query"] == "없는 제품"
    assert jobs[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_editor_batch_returns_manual_item_when_line_times_out(monkeypatch) -> None:
    monkeypatch.setattr(EditorBatchService, "_LINE_TIMEOUT_SECONDS", 0.01)
    service = EditorBatchService(SlowEditorSearchService())

    response = await service.batch("헤라 파우더 #13N1", limit=3)

    assert response.count == 1
    assert response.items[0].status == "수동 확인 필요"
    assert response.items[0].parsed.brand_en == "HERA"
    assert response.items[0].candidates == []


@pytest.mark.asyncio
async def test_editor_batch_searches_with_shade_query_first() -> None:
    search_service = ShadeAwareEditorSearchService()
    service = EditorBatchService(search_service)

    response = await service.batch("롬앤 쉐딩 #그레이쿨", limit=3)

    assert search_service.queries == ["롬앤 쉐딩 그레이쿨"]
    assert response.items[0].status == "확인됨"
    assert response.items[0].candidates[0].product.source_product_id == "romand-shading"


@pytest.mark.asyncio
async def test_editor_batch_falls_back_to_normalized_query_when_shade_query_misses() -> None:
    search_service = ShadeFallbackEditorSearchService()
    service = EditorBatchService(search_service)

    response = await service.batch("헤라 파우더 #13N1", limit=3)

    assert search_service.queries == ["헤라 파우더 13N1", "헤라 파우더"]
    assert response.items[0].status == "후보 있음"
    assert response.items[0].candidates[0].product.source_product_id == "hera-powder"


@pytest.mark.asyncio
async def test_editor_batch_matches_eyeliner_abbreviation() -> None:
    search_service = EyelinerAbbreviationEditorSearchService()
    service = EditorBatchService(search_service)

    response = await service.batch("캔메이크 아라 카푸치노", limit=3)

    assert search_service.queries == ["캔메이크 아라 카푸치노", "캔메이크 아라"]
    assert response.items[0].status == "후보 있음"
    assert response.items[0].candidates[0].product.source_product_id == "canmake-liner"


@pytest.mark.asyncio
async def test_editor_batch_drops_brand_mismatch_product_fallback_candidates() -> None:
    search_service = BrandMismatchFallbackEditorSearchService()
    service = EditorBatchService(search_service)

    response = await service.batch("아멜리 하이라이터 #432", limit=3)

    assert search_service.queries == [
        "아멜리 하이라이터 432",
        "아멜리 하이라이터",
        "하이라이터",
    ]
    assert response.items[0].status == "수동 확인 필요"
    assert response.items[0].candidates == []


def test_product_index_prepares_editor_confirmed_mappings_table(tmp_path) -> None:
    db_path = tmp_path / "product_index.sqlite3"
    SQLiteProductIndexStore(db_path)

    connection = sqlite3.connect(db_path)
    table = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'editor_confirmed_mappings'"
    ).fetchone()
    connection.close()

    assert table is not None


@pytest.mark.asyncio
async def test_product_index_records_editor_confirmed_mapping(tmp_path) -> None:
    db_path = tmp_path / "product_index.sqlite3"
    store = SQLiteProductIndexStore(db_path)

    saved = await store.record_editor_confirmed_mapping(
        raw_text="헤라 파우더 #13N1",
        normalized_query="헤라 파우더",
        source="oliveyoung",
        source_url="https://oliveyoung.example/products/hera",
        source_product_id="hera-1",
        brand_ko="헤라",
        brand_en="HERA",
        product_name_ko="헤라 파우더 13N1",
        product_name_en="HERA Powder",
        shade="13N1",
    )

    connection = sqlite3.connect(db_path)
    row = connection.execute(
        "SELECT raw_text, normalized_query, source, product_name_en FROM editor_confirmed_mappings"
    ).fetchone()
    connection.close()

    assert saved is True
    assert row == ("헤라 파우더 #13N1", "헤라 파우더", "oliveyoung", "HERA Powder")


def _editor_service(tmp_path) -> EditorBatchService:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        (
            '{"entries":['
            '{"official_en":"HERA","aliases":["헤라"],"sources":[]},'
            '{"official_en":"rom&nd","aliases":["롬앤"],"sources":[]},'
            '{"official_en":"CLIO","aliases":["클리오"],"sources":[]}'
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
        product_index=SQLiteProductIndexStore(tmp_path / "editor_index.sqlite3"),
    )
    return EditorBatchService(search_service)
