import httpx
import pytest

from app.api.main import create_app
from app.cache.ttl import AsyncTTLCache
from app.core.config import Settings
from app.indexing.store import SQLiteProductIndexStore
from app.models.product import ProductSourceRecord
from app.normalizer.brand import BrandResolver
from app.normalizer.product import ProductNormalizer
from app.service.factory import get_search_service
from app.service.search_service import SearchService, _CollectedResult

ADMIN_TOKEN = "test-admin-review-token"


def _enabled_settings(**overrides) -> Settings:
    return Settings(
        admin_review_api_enabled=True,
        admin_review_token=ADMIN_TOKEN,
        **overrides,
    )


def _disabled_settings(**overrides) -> Settings:
    return Settings(**overrides)


async def _build_service(tmp_path) -> tuple[SearchService, SQLiteProductIndexStore]:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text('{"entries":[]}', encoding="utf-8")
    store = SQLiteProductIndexStore(tmp_path / "admin_review_index.sqlite3")
    service = SearchService(
        collectors=[],
        normalizer=ProductNormalizer(
            BrandResolver(registry_path),
            base_url="https://www.oliveyoung.co.kr",
        ),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        product_index=store,
        index_background_refresh_enabled=False,
    )
    return service, store


async def _seed_pending_match(
    store: SQLiteProductIndexStore, *, canonical_product_id: str = "verified-review-1"
) -> str:
    await store.upsert_search_results(
        "리뷰용 세럼",
        [
            ProductSourceRecord(
                canonical_product_id=canonical_product_id,
                source_brand_name="리뷰브랜드",
                product_name_ko="리뷰용 세럼",
                source="musinsa",
                source_product_id="review-ms-1",
                source_url="https://musinsa.example/review-ms-1",
                original_price=18000,
            )
        ],
    )
    offer_id = store._connection.execute(  # noqa: SLF001 - test-only direct row access
        "SELECT id FROM product_offers WHERE source_product_id = 'review-ms-1'"
    ).fetchone()["id"]
    match_id = await store.record_candidate_match(
        canonical_product_id=canonical_product_id,
        offer_id=offer_id,
        confidence=0.6,
        match_method="brand_name_exact",
        evidence=[{"type": "brand_name_exact", "value": "match", "weight": 0.55}],
    )
    assert match_id is not None
    return match_id


@pytest.mark.asyncio
async def test_admin_review_routes_404_when_disabled_by_default(tmp_path, monkeypatch) -> None:
    service, store = await _build_service(tmp_path)
    monkeypatch.setattr("app.api.routes.get_settings", _disabled_settings)
    app = create_app()
    app.dependency_overrides[get_search_service] = lambda: service
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        list_response = await client.get("/index/matches/pending")
        detail_response = await client.get("/index/matches/anything")
        review_response = await client.post(
            "/index/matches/anything/review",
            json={"decision": "verified", "reviewer": "alice"},
        )

    app.dependency_overrides.clear()
    await store.close()

    assert list_response.status_code == 404
    assert detail_response.status_code == 404
    assert review_response.status_code == 404


@pytest.mark.asyncio
async def test_admin_review_routes_404_when_flag_on_but_token_unset(tmp_path, monkeypatch) -> None:
    service, store = await _build_service(tmp_path)
    monkeypatch.setattr(
        "app.api.routes.get_settings",
        lambda: Settings(admin_review_api_enabled=True, admin_review_token=None),
    )
    app = create_app()
    app.dependency_overrides[get_search_service] = lambda: service
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/index/matches/pending")

    app.dependency_overrides.clear()
    await store.close()

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_review_routes_403_on_missing_or_wrong_token(tmp_path, monkeypatch) -> None:
    service, store = await _build_service(tmp_path)
    monkeypatch.setattr("app.api.routes.get_settings", _enabled_settings)
    app = create_app()
    app.dependency_overrides[get_search_service] = lambda: service
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        no_header = await client.get("/index/matches/pending")
        wrong_token = await client.get(
            "/index/matches/pending", headers={"Authorization": "Bearer wrong-token"}
        )

    app.dependency_overrides.clear()
    await store.close()

    assert no_header.status_code == 403
    assert wrong_token.status_code == 403


@pytest.mark.asyncio
async def test_list_pending_matches_returns_only_pending_with_filters(
    tmp_path, monkeypatch
) -> None:
    service, store = await _build_service(tmp_path)
    match_id = await _seed_pending_match(store)
    monkeypatch.setattr("app.api.routes.get_settings", _enabled_settings)
    app = create_app()
    app.dependency_overrides[get_search_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        matching_source = await client.get(
            "/index/matches/pending", params={"source": "musinsa"}, headers=headers
        )
        other_source = await client.get(
            "/index/matches/pending", params={"source": "official"}, headers=headers
        )

    app.dependency_overrides.clear()
    await store.close()

    assert matching_source.status_code == 200
    payload = matching_source.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["match_id"] == match_id
    assert payload["items"][0]["offer"]["source"] == "musinsa"
    assert payload["items"][0]["target"]["product_name_ko"] == "리뷰용 세럼"
    assert other_source.json()["items"] == []


@pytest.mark.asyncio
async def test_get_match_detail_404_for_unknown_match_id(tmp_path, monkeypatch) -> None:
    service, store = await _build_service(tmp_path)
    monkeypatch.setattr("app.api.routes.get_settings", _enabled_settings)
    app = create_app()
    app.dependency_overrides[get_search_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/index/matches/match:does-not-exist", headers=headers)

    app.dependency_overrides.clear()
    await store.close()

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_review_match_verifies_and_records_history(tmp_path, monkeypatch) -> None:
    service, store = await _build_service(tmp_path)
    match_id = await _seed_pending_match(store)
    monkeypatch.setattr("app.api.routes.get_settings", _enabled_settings)
    app = create_app()
    app.dependency_overrides[get_search_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        review_response = await client.post(
            f"/index/matches/{match_id}/review",
            json={"decision": "verified", "reviewer": "alice", "note": "looks right"},
            headers=headers,
        )
        detail_response = await client.get(f"/index/matches/{match_id}", headers=headers)

    app.dependency_overrides.clear()
    await store.close()

    assert review_response.status_code == 200
    body = review_response.json()
    assert body["review_state"] == "verified"
    assert body["reviewed_by"] == "alice"
    assert body["idempotent"] is False

    detail = detail_response.json()
    assert detail["review_state"] == "verified"
    assert len(detail["history"]) == 1
    assert detail["history"][0]["previous_review_state"] == "pending_review"
    assert detail["history"][0]["new_review_state"] == "verified"
    assert detail["history"][0]["reviewer"] == "alice"


@pytest.mark.asyncio
async def test_review_match_replay_is_idempotent_and_does_not_duplicate_history(
    tmp_path, monkeypatch
) -> None:
    service, store = await _build_service(tmp_path)
    match_id = await _seed_pending_match(store)
    monkeypatch.setattr("app.api.routes.get_settings", _enabled_settings)
    app = create_app()
    app.dependency_overrides[get_search_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            f"/index/matches/{match_id}/review",
            json={"decision": "verified", "reviewer": "alice"},
            headers=headers,
        )
        second = await client.post(
            f"/index/matches/{match_id}/review",
            json={"decision": "verified", "reviewer": "alice"},
            headers=headers,
        )
        detail_response = await client.get(f"/index/matches/{match_id}", headers=headers)

    app.dependency_overrides.clear()
    await store.close()

    assert first.json()["idempotent"] is False
    assert second.status_code == 200
    assert second.json()["idempotent"] is True
    assert len(detail_response.json()["history"]) == 1


@pytest.mark.asyncio
async def test_review_match_conflict_on_stale_expected_updated_at(tmp_path, monkeypatch) -> None:
    service, store = await _build_service(tmp_path)
    match_id = await _seed_pending_match(store)
    monkeypatch.setattr("app.api.routes.get_settings", _enabled_settings)
    app = create_app()
    app.dependency_overrides[get_search_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/index/matches/{match_id}/review",
            json={
                "decision": "verified",
                "reviewer": "alice",
                "expected_updated_at": "2000-01-01T00:00:00+00:00",
            },
            headers=headers,
        )
        detail_response = await client.get(f"/index/matches/{match_id}", headers=headers)

    app.dependency_overrides.clear()
    await store.close()

    assert response.status_code == 409
    assert detail_response.json()["review_state"] == "pending_review"  # untouched


@pytest.mark.asyncio
async def test_review_match_can_be_overturned_and_both_events_recorded(
    tmp_path, monkeypatch
) -> None:
    service, store = await _build_service(tmp_path)
    match_id = await _seed_pending_match(store)
    monkeypatch.setattr("app.api.routes.get_settings", _enabled_settings)
    app = create_app()
    app.dependency_overrides[get_search_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            f"/index/matches/{match_id}/review",
            json={"decision": "verified", "reviewer": "alice"},
            headers=headers,
        )
        overturn = await client.post(
            f"/index/matches/{match_id}/review",
            json={"decision": "rejected", "reviewer": "bob", "note": "actually wrong"},
            headers=headers,
        )
        detail_response = await client.get(f"/index/matches/{match_id}", headers=headers)

    app.dependency_overrides.clear()
    await store.close()

    assert overturn.status_code == 200
    assert overturn.json()["review_state"] == "rejected"
    history = detail_response.json()["history"]
    assert len(history) == 2
    assert [event["new_review_state"] for event in history] == ["verified", "rejected"]


@pytest.mark.asyncio
async def test_review_match_rejects_invalid_decision_value(tmp_path, monkeypatch) -> None:
    service, store = await _build_service(tmp_path)
    match_id = await _seed_pending_match(store)
    monkeypatch.setattr("app.api.routes.get_settings", _enabled_settings)
    app = create_app()
    app.dependency_overrides[get_search_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/index/matches/{match_id}/review",
            json={"decision": "invalid", "reviewer": "alice"},
            headers=headers,
        )

    app.dependency_overrides.clear()
    await store.close()

    assert response.status_code == 422
