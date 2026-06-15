import os
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core.config import get_settings
from app.data_collector.base import SearchCriteria
from app.editor.batch import EditorBatchService
from app.models.editor import EditorBatchRequest, EditorBatchResponse
from app.models.product import SearchResponse, SuggestionResponse
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
    payload["config"] = {
        "product_index_enabled": settings.product_index_enabled,
        "warmup_on_startup": settings.product_index_warmup_on_startup,
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
    token: Annotated[str | None, Query(description="GLOWSEARCH_PRODUCT_INDEX_ADMIN_TOKEN")] = None,
    service: SearchService = Depends(get_search_service),
) -> dict[str, object]:
    _require_index_admin(request, token)
    summary = await service.run_catalog_jobs(
        max_jobs=max_jobs,
        limit_per_query=limit,
        kind=kind,
    )
    return asdict(summary)


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


def _require_index_admin(request: Request, token: str | None) -> None:
    settings = get_settings()
    expected_token = settings.product_index_admin_token
    if expected_token:
        if token == expected_token:
            return
        raise HTTPException(status_code=403, detail="Invalid index admin token.")

    client_host = request.client.host if request.client else ""
    if client_host in {"127.0.0.1", "::1", "localhost"}:
        return
    raise HTTPException(
        status_code=403,
        detail="Set GLOWSEARCH_PRODUCT_INDEX_ADMIN_TOKEN to enable remote index warmup.",
    )
