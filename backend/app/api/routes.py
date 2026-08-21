import hmac
import os
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from app.core.config import get_settings
from app.data_collector.base import SearchCriteria
from app.editor.batch import EditorBatchService
from app.indexing import turso_http
from app.models.editor import (
    EditorBatchRequest,
    EditorBatchResponse,
    EditorConfirmRequest,
    EditorConfirmResponse,
)
from app.models.product import SearchResponse, SuggestionResponse
from app.models.review import (
    MatchDetail,
    MatchReviewRequest,
    MatchReviewResponse,
    PendingMatchListResponse,
)
from app.search_engine.analytics import InMemorySearchAnalytics
from app.service.factory import get_search_analytics, get_search_service
from app.service.search_service import SearchService


router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "release_sha": _release_sha(),
    }


def _release_sha() -> str:
    return (
        os.getenv("GLOWSEARCH_RELEASE_SHA")
        or os.getenv("RENDER_GIT_COMMIT")
        or os.getenv("GITHUB_SHA")
        or "unknown"
    )


@router.get("/search", response_model=SearchResponse)
async def search(
    q: Annotated[str | None, Query(min_length=1, description="검색어")] = None,
    keyword: Annotated[str | None, Query(min_length=1, description="검색어 alias")] = None,
    brand: Annotated[str | None, Query(min_length=1, description="브랜드 필터")] = None,
    min_price: Annotated[int | None, Query(ge=0, description="최소 가격")] = None,
    max_price: Annotated[int | None, Query(ge=0, description="최대 가격")] = None,
    has_shade: Annotated[bool | None, Query(description="색상/호수 존재 여부")] = None,
    limit: Annotated[int, Query(ge=1, le=480, description="반환 개수")] = 48,
    index_only: Annotated[bool, Query(description="인덱스 결과만 반환 (라이브 수집 건너뜀)")] = False,
    service: SearchService = Depends(get_search_service),
    analytics: InMemorySearchAnalytics = Depends(get_search_analytics),
) -> SearchResponse:
    term = (q or keyword or "").strip()
    if not term:
        raise HTTPException(status_code=422, detail="q 또는 keyword가 필요합니다.")
    analytics.record(term)

    settings = get_settings()
    criteria = SearchCriteria(
        brand=brand.strip() if brand else None,
        min_price=min_price,
        max_price=max_price,
        has_shade=has_shade,
        limit=min(limit, settings.max_results),
        index_only=index_only,
    )
    return await service.search(term, criteria)


@router.get("/suggest", response_model=SuggestionResponse)
async def suggest(
    q: Annotated[str | None, Query(min_length=1, description="자동완성 검색어")] = None,
    limit: Annotated[int, Query(ge=1, le=20, description="반환 개수")] = 10,
    service: SearchService = Depends(get_search_service),
) -> SuggestionResponse:
    term = (q or "").strip()
    if not term:
        raise HTTPException(status_code=422, detail="q가 필요합니다.")
    return SuggestionResponse(query=term, suggestions=service.suggest(term, limit))


@router.post("/editor/batch", response_model=EditorBatchResponse)
async def editor_batch(
    request: EditorBatchRequest,
    service: SearchService = Depends(get_search_service),
) -> EditorBatchResponse:
    return await EditorBatchService(service).batch(request.text, limit=request.limit)


@router.post("/editor/confirm", response_model=EditorConfirmResponse)
async def editor_confirm(
    request: EditorConfirmRequest,
    service: SearchService = Depends(get_search_service),
) -> EditorConfirmResponse:
    saved = await service.record_editor_confirmed_mapping(
        raw_text=request.raw_text,
        normalized_query=request.normalized_query,
        source=request.source,
        source_url=request.source_url,
        source_product_id=request.source_product_id,
        canonical_product_id=request.canonical_product_id,
        brand_ko=request.brand_ko,
        brand_en=request.brand_en,
        product_name_ko=request.product_name_ko,
        product_name_en=request.product_name_en,
        shade=request.shade,
    )
    return EditorConfirmResponse(saved=saved)


@router.get("/index/status")
async def index_status(
    service: SearchService = Depends(get_search_service),
) -> dict[str, int | str | bool | None]:
    settings = get_settings()
    stats = await service.index_stats()
    stats.update(
        {
            "product_index_enabled": settings.product_index_enabled,
            "product_index_path": str(settings.product_index_path),
            "warmup_on_startup": settings.product_index_warmup_on_startup,
            "verified_catalog_backfill_on_startup": settings.product_index_verified_catalog_backfill_on_startup,
            "max_seed_queries": settings.product_index_max_seed_queries,
            "background_refresh_limit": settings.product_index_background_refresh_limit,
            "browser_collector_enabled": settings.browser_collector_enabled,
            "oliveyoung_html_collector_enabled": settings.oliveyoung_html_collector_enabled,
            "oliveyoung_public_api_enabled": settings.oliveyoung_public_api_enabled,
            "live_search_required": settings.oliveyoung_live_search_required,
            "admin_token_configured": bool(settings.product_index_admin_token),
        }
    )
    return stats


@router.get("/diagnostics")
async def diagnostics(
    service: SearchService = Depends(get_search_service),
) -> dict[str, object]:
    settings = get_settings()
    payload = service.diagnostics()
    payload["index"] = await service.index_stats()
    payload["search_gaps"] = await service.recent_search_gaps(limit=20)
    payload["catalog_jobs"] = {
        "stats": await service.catalog_job_stats(),
        "recent": await service.recent_catalog_jobs(limit=20),
    }
    payload["verified_catalog"] = _verified_catalog_stats(settings.verified_catalog_path)
    payload["adapter_readiness"] = _adapter_readiness(settings)
    payload["config"] = {
        "product_index_enabled": settings.product_index_enabled,
        "warmup_on_startup": settings.product_index_warmup_on_startup,
        "verified_catalog_backfill_on_startup": settings.product_index_verified_catalog_backfill_on_startup,
        "product_index_background_refresh_limit": settings.product_index_background_refresh_limit,
        "source_time_budget_seconds": settings.source_time_budget_seconds,
        "live_collect_deadline_seconds": settings.live_collect_deadline_seconds,
        "live_first_result_grace_seconds": settings.live_first_result_grace_seconds,
        "background_collect_deadline_seconds": settings.background_collect_deadline_seconds,
        "browser_collector_enabled": settings.browser_collector_enabled,
        "oliveyoung_html_collector_enabled": settings.oliveyoung_html_collector_enabled,
        "oliveyoung_public_api_enabled": settings.oliveyoung_public_api_enabled,
        "live_search_required": settings.oliveyoung_live_search_required,
        "result_source_prefixes": settings.result_source_prefixes,
        "managed_search_api_enabled": settings.managed_search_api_enabled,
        "musinsa_api_enabled": settings.musinsa_api_enabled,
        "oliveyoung_global_api_enabled": settings.oliveyoung_global_api_enabled,
        "official_brand_api_enabled": settings.official_brand_api_enabled,
        "global_discovery_api_enabled": settings.global_discovery_api_enabled,
        "barcode_lookup_api_enabled": settings.barcode_lookup_api_enabled,
    }
    return payload


def _verified_catalog_stats(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "total": 0,
            "canonical_product_id": 0,
            "product_name_en": 0,
            "source_counts": {},
        }

    payload = json.loads(path.read_text(encoding="utf-8"))
    products = payload.get("products", []) if isinstance(payload, dict) else payload
    items = [item for item in products if isinstance(item, dict)]
    source_counts: Counter[str] = Counter()
    canonical_count = 0
    product_name_en_count = 0

    for item in items:
        if item.get("canonical_product_id"):
            canonical_count += 1
        if item.get("product_name_en"):
            product_name_en_count += 1
        for source in _catalog_sources(item):
            source_counts[source] += 1

    return {
        "path": str(path),
        "exists": True,
        "total": len(items),
        "canonical_product_id": canonical_count,
        "product_name_en": product_name_en_count,
        "source_counts": dict(sorted(source_counts.items())),
    }


def _catalog_sources(item: dict[str, object]) -> set[str]:
    sources: set[str] = set()
    source = item.get("source")
    if isinstance(source, str) and source:
        sources.add(source.split(":", 1)[0])
    source_url = item.get("source_url")
    if not sources and isinstance(source_url, str):
        inferred_source = _source_from_url(source_url)
        if inferred_source:
            sources.add(inferred_source)
    offers = item.get("offers")
    if isinstance(offers, list):
        for offer in offers:
            if not isinstance(offer, dict):
                continue
            offer_source = offer.get("source")
            if isinstance(offer_source, str) and offer_source:
                sources.add(offer_source.split(":", 1)[0])
    return sources


def _source_from_url(source_url: str) -> str | None:
    source_url = source_url.casefold()
    if "oliveyoung" in source_url:
        return "oliveyoung"
    if "musinsa" in source_url:
        return "musinsa"
    if "coupang" in source_url:
        return "coupang"
    if "hwahae" in source_url:
        return "hwahae"
    if "glowpick" in source_url:
        return "glowpick"
    if "fudejapan" in source_url:
        return "fudejapan"
    return None


def _adapter_readiness(settings) -> dict[str, dict[str, object]]:
    return {
        "oliveyoung_public_api": {
            "enabled": settings.oliveyoung_public_api_enabled,
            "configured": bool(settings.oliveyoung_public_api_base_url),
            "base_url_configured": bool(settings.oliveyoung_public_api_base_url),
            "reason": _adapter_reason(
                enabled=settings.oliveyoung_public_api_enabled,
                base_url=settings.oliveyoung_public_api_base_url,
            ),
        },
        "musinsa": {
            "enabled": settings.musinsa_api_enabled,
            "configured": bool(settings.musinsa_api_base_url),
            "base_url_configured": bool(settings.musinsa_api_base_url),
            "reason": _adapter_reason(
                enabled=settings.musinsa_api_enabled,
                base_url=settings.musinsa_api_base_url,
            ),
        },
        "oliveyoung_global": {
            "enabled": settings.oliveyoung_global_api_enabled,
            "configured": bool(settings.oliveyoung_global_api_base_url),
            "base_url_configured": bool(settings.oliveyoung_global_api_base_url),
            "reason": _adapter_reason(
                enabled=settings.oliveyoung_global_api_enabled,
                base_url=settings.oliveyoung_global_api_base_url,
            ),
        },
        "official_brand": {
            "enabled": settings.official_brand_api_enabled,
            "configured": bool(settings.official_brand_api_base_url),
            "base_url_configured": bool(settings.official_brand_api_base_url),
            "reason": _adapter_reason(
                enabled=settings.official_brand_api_enabled,
                base_url=settings.official_brand_api_base_url,
            ),
        },
        "global_discovery": {
            "enabled": settings.global_discovery_api_enabled,
            "configured": bool(settings.global_discovery_api_base_url),
            "base_url_configured": bool(settings.global_discovery_api_base_url),
            "reason": _adapter_reason(
                enabled=settings.global_discovery_api_enabled,
                base_url=settings.global_discovery_api_base_url,
            ),
        },
        "managed_search": {
            "enabled": settings.managed_search_api_enabled,
            "configured": bool(settings.managed_search_api_base_url),
            "base_url_configured": bool(settings.managed_search_api_base_url),
            "reason": _adapter_reason(
                enabled=settings.managed_search_api_enabled,
                base_url=settings.managed_search_api_base_url,
            ),
        },
    }


def _adapter_reason(*, enabled: bool, base_url: str | None) -> str:
    if not enabled:
        return "disabled"
    if not base_url:
        return "missing_base_url"
    return "ready"


@router.get("/index/catalog/status")
async def catalog_status(
    service: SearchService = Depends(get_search_service),
) -> dict[str, object]:
    return {
        "stats": await service.catalog_job_stats(),
        "recent": await service.recent_catalog_jobs(limit=20),
    }


@router.post("/index/catalog/run")
async def run_catalog_jobs(
    request: Request,
    max_jobs: Annotated[int, Query(ge=1, le=100, description="처리할 catalog job 수")] = 20,
    limit: Annotated[int, Query(ge=1, le=480, description="검색어별 수집 개수")] = 48,
    kind: Annotated[str, Query(description="catalog job kind")] = "oliveyoung-search",
    reset_stale_running_minutes: Annotated[
        int,
        Query(
            ge=0,
            le=1440,
            description="N분보다 오래 running 상태인 catalog job을 실행 전 복구합니다. 0이면 비활성화.",
        ),
    ] = 0,
    token: Annotated[str | None, Query(description="GLOWSEARCH_PRODUCT_INDEX_ADMIN_TOKEN")] = None,
    service: SearchService = Depends(get_search_service),
) -> dict[str, object]:
    _require_index_admin(request, token)
    summary = await service.run_catalog_jobs(
        max_jobs=max_jobs,
        limit_per_query=limit,
        kind=kind,
        reset_stale_running_minutes=reset_stale_running_minutes,
    )
    return asdict(summary)


@router.get("/index/turso/debug")
async def turso_debug(
    request: Request,
    token: Annotated[str | None, Query(description="GLOWSEARCH_PRODUCT_INDEX_ADMIN_TOKEN")] = None,
) -> dict[str, object]:
    """Admin-only: isolates the local-read step used by backup_to_turso,
    with raw filesystem facts, to debug why it reports 0 products when
    /index/status reports otherwise."""
    _require_index_admin(request, token)
    settings = get_settings()
    path = settings.product_index_path
    result: dict[str, object] = {
        "product_index_path": str(path),
        "path_exists": path.exists(),
        "path_size_bytes": path.stat().st_size if path.exists() else None,
    }
    from app.indexing.store import SQLiteProductIndexStore

    local = SQLiteProductIndexStore(path)
    try:
        records = await local.all_products()
        result["all_products_count"] = len(records)
        raw = local._connection.execute("SELECT COUNT(*) AS c FROM products").fetchone()
        result["raw_count_query"] = raw["c"]
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        await local.close()
    return result


@router.post("/index/turso/backup")
async def turso_backup_now(
    request: Request,
    token: Annotated[str | None, Query(description="GLOWSEARCH_PRODUCT_INDEX_ADMIN_TOKEN")] = None,
) -> dict[str, object]:
    """Admin-only: manually triggers a backup cycle (app/indexing/turso_http.py,
    httpx-based) instead of waiting for the periodic interval."""
    _require_index_admin(request, token)
    settings = get_settings()
    if not settings.turso_database_url:
        return {"ok": False, "error": "GLOWSEARCH_TURSO_DATABASE_URL is not set"}
    count = await turso_http.backup_to_turso(settings.product_index_path, settings)
    return {
        "ok": True,
        "products_backed_up": count,
        "product_index_path": str(settings.product_index_path),
    }


@router.post("/index/turso/restore")
async def turso_restore_now(
    request: Request,
    token: Annotated[str | None, Query(description="GLOWSEARCH_PRODUCT_INDEX_ADMIN_TOKEN")] = None,
) -> dict[str, object]:
    """Admin-only: manually triggers a restore-from-Turso cycle."""
    _require_index_admin(request, token)
    settings = get_settings()
    if not settings.turso_database_url:
        return {"ok": False, "error": "GLOWSEARCH_TURSO_DATABASE_URL is not set"}
    count = await turso_http.restore_from_turso(settings.product_index_path, settings)
    return {"ok": True, "products_restored": count}


@router.post("/index/warm")
async def warm_index(
    request: Request,
    q: Annotated[
        list[str] | None,
        Query(description="수집할 검색어. 생략하면 설정된 Olive Young seed 전체를 사용합니다."),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=480, description="검색어별 수집 개수")] = 48,
    wait: Annotated[bool, Query(description="true면 완료까지 기다립니다.")] = False,
    token: Annotated[str | None, Query(description="GLOWSEARCH_PRODUCT_INDEX_ADMIN_TOKEN")] = None,
    service: SearchService = Depends(get_search_service),
) -> dict[str, int | str | bool]:
    _require_index_admin(request, token)
    if wait:
        scheduled_queries = await service.warm_index(q, limit=limit)
        return {
            "status": "completed",
            "scheduled_queries": scheduled_queries,
            "limit": limit,
            "wait": wait,
        }
    scheduled_queries = service.schedule_warm_index(q, limit=limit)
    return {
        "status": "scheduled",
        "scheduled_queries": scheduled_queries,
        "limit": limit,
        "wait": wait,
    }


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    return token or None


def _require_admin_review(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Auth for the match-review API (milestone 4). Deliberately stricter
    than _require_index_admin: no localhost fallback, and a dedicated
    GLOWSEARCH_ADMIN_REVIEW_TOKEN separate from the index admin token. If
    either the feature flag or the token is unset, every /index/matches/*
    route 404s as if it doesn't exist, rather than 403 — an unconfigured
    approval API should not even reveal its own existence."""
    settings = get_settings()
    if not settings.admin_review_api_enabled or not settings.admin_review_token:
        raise HTTPException(status_code=404)
    provided = _bearer_token(authorization)
    if provided is not None and hmac.compare_digest(provided, settings.admin_review_token):
        return
    raise HTTPException(status_code=403, detail="Invalid admin review token.")


@router.get(
    "/index/matches/pending",
    response_model=PendingMatchListResponse,
    dependencies=[Depends(_require_admin_review)],
)
async def list_pending_matches(
    limit: Annotated[int, Query(ge=1, le=100, description="반환 개수")] = 20,
    after_id: Annotated[int | None, Query(ge=1, description="이 id보다 큰 매치부터")] = None,
    source: Annotated[str | None, Query(description="판매처 필터")] = None,
    service: SearchService = Depends(get_search_service),
) -> PendingMatchListResponse:
    return await service.list_pending_matches(limit=limit, after_id=after_id, source=source)


@router.get(
    "/index/matches/{match_id}",
    response_model=MatchDetail,
    dependencies=[Depends(_require_admin_review)],
)
async def get_match(
    match_id: str,
    service: SearchService = Depends(get_search_service),
) -> MatchDetail:
    detail = await service.get_match_detail(match_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Match not found.")
    return detail


@router.post(
    "/index/matches/{match_id}/review",
    response_model=MatchReviewResponse,
    dependencies=[Depends(_require_admin_review)],
)
async def review_match(
    match_id: str,
    request: MatchReviewRequest,
    service: SearchService = Depends(get_search_service),
) -> MatchReviewResponse:
    outcome = await service.review_match(
        match_id,
        decision=request.decision,
        reviewer=request.reviewer,
        note=request.note,
        expected_updated_at=request.expected_updated_at,
    )
    if outcome is None or outcome.status == "not_found":
        raise HTTPException(status_code=404, detail="Match not found.")
    if outcome.status == "conflict":
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Match has been updated since expected_updated_at.",
                "current_updated_at": outcome.row["updated_at"],
                "current_review_state": outcome.row["review_state"],
            },
        )
    row = outcome.row
    return MatchReviewResponse(
        match_id=row["match_id"],
        review_state=row["review_state"],
        reviewed_by=row["reviewed_by"],
        reviewed_at=row["reviewed_at"],
        updated_at=row["updated_at"],
        idempotent=(outcome.status == "noop"),
    )


def _require_index_admin(request: Request, token: str | None) -> None:
    settings = get_settings()
    expected_token = settings.product_index_admin_token
    if expected_token:
        if token is not None and hmac.compare_digest(token, expected_token):
            return
        raise HTTPException(status_code=403, detail="Invalid index admin token.")

    client_host = request.client.host if request.client else ""
    if client_host in {"127.0.0.1", "::1", "localhost"}:
        return
    raise HTTPException(
        status_code=403,
        detail="Set GLOWSEARCH_PRODUCT_INDEX_ADMIN_TOKEN to enable remote index warmup.",
    )
