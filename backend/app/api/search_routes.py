from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.search_engine.analytics import InMemorySearchAnalytics
from app.search_engine.provider import SearchProvider
from app.search_engine.related import RelatedKeywordService
from app.service.factory import (
    get_related_keyword_service,
    get_search_analytics,
    get_search_provider,
)


router = APIRouter()


@router.get("/autocomplete")
async def autocomplete(
    q: Annotated[str | None, Query(min_length=1, description="자동완성 prefix")] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
    provider: SearchProvider = Depends(get_search_provider),
) -> dict[str, object]:
    term = (q or "").strip()
    if not term:
        raise HTTPException(status_code=422, detail="q가 필요합니다.")
    return {
        "query": term,
        "suggestions": await provider.autocomplete(term, limit),
        "provider": provider.name,
    }


@router.get("/related")
async def related(
    q: Annotated[str | None, Query(min_length=1, description="관련 검색어 기준 query")] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
    related_keywords: RelatedKeywordService = Depends(get_related_keyword_service),
) -> dict[str, object]:
    term = (q or "").strip()
    if not term:
        raise HTTPException(status_code=422, detail="q가 필요합니다.")
    return {
        "query": term,
        "related": related_keywords.related(term, limit=limit),
    }


@router.get("/popular")
async def popular(
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
    analytics: InMemorySearchAnalytics = Depends(get_search_analytics),
) -> dict[str, object]:
    return {"popular": analytics.snapshot(limit=limit).popular}


@router.get("/recent")
async def recent(
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
    analytics: InMemorySearchAnalytics = Depends(get_search_analytics),
) -> dict[str, object]:
    return {"recent": analytics.snapshot(limit=limit).recent}


@router.get("/trending")
async def trending(
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
    analytics: InMemorySearchAnalytics = Depends(get_search_analytics),
) -> dict[str, object]:
    return {"trending": analytics.snapshot(limit=limit).trending}
