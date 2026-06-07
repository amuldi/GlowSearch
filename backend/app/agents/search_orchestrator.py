from __future__ import annotations

from app.data_collector.base import SearchCriteria
from app.models.product import SearchResponse
from app.service.search_service import SearchService


class SearchOrchestratorAgent:
    """Compatibility wrapper for the request-time search orchestrator."""

    def __init__(self, service: SearchService):
        self._service = service

    async def search(self, query: str, criteria: SearchCriteria) -> SearchResponse:
        return await self._service.search(query, criteria)
