from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.config import get_settings
from app.data_collector.base import SearchCriteria
from app.models.product import SearchResponse
from app.service.factory import get_search_service
from app.service.search_service import SearchService


router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/search", response_model=SearchResponse)
async def search(
    q: Annotated[str | None, Query(min_length=1, description="검색어")] = None,
    keyword: Annotated[str | None, Query(min_length=1, description="검색어 alias")] = None,
    brand: Annotated[str | None, Query(min_length=1, description="브랜드 필터")] = None,
    min_price: Annotated[int | None, Query(ge=0, description="최소 가격")] = None,
    max_price: Annotated[int | None, Query(ge=0, description="최대 가격")] = None,
    has_shade: Annotated[bool | None, Query(description="색상/호수 존재 여부")] = None,
    limit: Annotated[int, Query(ge=1, le=200, description="반환 개수")] = 48,
    service: SearchService = Depends(get_search_service),
) -> SearchResponse:
    term = (q or keyword or "").strip()
    if not term:
        raise HTTPException(status_code=422, detail="q 또는 keyword가 필요합니다.")

    settings = get_settings()
    criteria = SearchCriteria(
        brand=brand.strip() if brand else None,
        min_price=min_price,
        max_price=max_price,
        has_shade=has_shade,
        limit=min(limit, settings.max_results),
    )
    return await service.search(term, criteria)
