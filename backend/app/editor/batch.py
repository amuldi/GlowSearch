from __future__ import annotations

import asyncio
import re

from app.data_collector.base import SearchCriteria
from app.editor.parser import parse_editor_lines
from app.models.editor import (
    EditorBatchItem,
    EditorBatchResponse,
    EditorMatchStatus,
    EditorParsedLine,
    EditorProductCandidate,
)
from app.models.product import ProductSearchResult
from app.search.synonyms import search_key
from app.service.search_service import SearchService


class EditorBatchService:
    _CONCURRENCY = 4

    def __init__(self, search_service: SearchService):
        self._search_service = search_service

    async def batch(self, text: str, *, limit: int = 5) -> EditorBatchResponse:
        parsed_lines = parse_editor_lines(text)
        semaphore = asyncio.Semaphore(self._CONCURRENCY)

        async def resolve(parsed: EditorParsedLine) -> EditorBatchItem:
            async with semaphore:
                return await self._resolve_line(parsed, limit=limit)

        items = await asyncio.gather(*(resolve(parsed) for parsed in parsed_lines))
        return EditorBatchResponse(count=len(items), items=list(items))

    async def _resolve_line(self, parsed: EditorParsedLine, *, limit: int) -> EditorBatchItem:
        parsed = self._with_resolved_brand_en(parsed)
        response = await self._search_service.search(
            parsed.normalized_query,
            SearchCriteria(limit=max(limit, 1)),
        )
        products = [
            product
            for product in response.results
            if _has_source_link(product) and _passes_editor_relevance(parsed, product)
        ]
        candidates = [
            EditorProductCandidate(product=product, match_score=_candidate_score(parsed, product))
            for product in products
        ]
        candidates.sort(key=lambda candidate: candidate.match_score, reverse=True)
        candidates = candidates[:limit]
        return EditorBatchItem(
            raw_text=parsed.raw_text,
            parsed=parsed,
            status=_status(candidates),
            candidates=candidates,
        )

    def _with_resolved_brand_en(self, parsed: EditorParsedLine) -> EditorParsedLine:
        if parsed.brand_en or not parsed.brand_query:
            return parsed
        resolve_brand_en = getattr(self._search_service, "resolve_brand_en", None)
        if resolve_brand_en is None:
            return parsed
        brand_en = resolve_brand_en(parsed.brand_query)
        if not brand_en:
            return parsed
        return parsed.model_copy(update={"brand_en": brand_en})


def _status(candidates: list[EditorProductCandidate]) -> EditorMatchStatus:
    if not candidates:
        return "수동 확인 필요"
    if len(candidates) == 1:
        return "확인됨"
    return "후보 있음"


def _candidate_score(parsed: EditorParsedLine, product: ProductSearchResult) -> int:
    score = product.quality_score
    if product.source_priority is not None:
        score += max(0, 80 - product.source_priority)
    if product.product_name_en:
        score += 8
    if product.source_url or any(offer.source_url for offer in product.offers):
        score += 10
    if product.image_url:
        score += 4

    brand_query = _key(parsed.brand_query)
    if brand_query:
        brand_text = _key(" ".join(value for value in [product.brand_ko, product.brand_en] if value))
        if brand_query and brand_query in brand_text:
            score += 40

    product_tokens = [_key(token) for token in _tokens(parsed.product_query)]
    product_text = _key(
        " ".join(
            value
            for value in [
                product.product_name_ko,
                product.product_name_en,
                product.category,
                product.description,
                product.shade,
                " ".join(product.options or []),
            ]
            if value
        )
    )
    if product_tokens:
        matched = sum(1 for token in product_tokens if token and token in product_text)
        score += matched * 18
        if matched == len(product_tokens):
            score += 20

    shade_values = [parsed.shade_code, parsed.shade_name]
    shade_tokens = [_key(value) for value in shade_values if value]
    if shade_tokens:
        shade_text = _key(
            " ".join(
                value
                for value in [
                    product.shade,
                    product.product_name_ko,
                    product.product_name_en,
                    " ".join(product.options or []),
                ]
                if value
            )
        )
        score += sum(35 for token in shade_tokens if token and token in shade_text)

    return score


def _passes_editor_relevance(parsed: EditorParsedLine, product: ProductSearchResult) -> bool:
    brand_query = _key(parsed.brand_query)
    product_tokens = [_key(token) for token in _tokens(parsed.product_query)]
    shade_tokens = [_key(value) for value in [parsed.shade_code, parsed.shade_name] if value]

    brand_text = _key(
        " ".join(
            value
            for value in [
                product.brand_ko,
                product.brand_en,
                product.product_name_ko,
                product.product_name_en,
            ]
            if value
        )
    )
    product_text = _product_match_text(product)

    if brand_query and brand_query not in brand_text:
        return False

    if product_tokens:
        matched_product_tokens = sum(1 for token in product_tokens if token and token in product_text)
        required_matches = len(product_tokens) if len(product_tokens) <= 2 else max(2, len(product_tokens) - 1)
        if matched_product_tokens < required_matches:
            return False

    if shade_tokens and any(token in product_text for token in shade_tokens):
        return True

    return bool(product_tokens or brand_query)


def _has_source_link(product: ProductSearchResult) -> bool:
    return bool(product.source_url or any(offer.source_url for offer in product.offers))


def _product_match_text(product: ProductSearchResult) -> str:
    return _key(
        " ".join(
            value
            for value in [
                product.product_name_ko,
                product.product_name_en,
                product.category,
                product.description,
                product.shade,
                " ".join(product.options or []),
            ]
            if value
        )
    )


def _tokens(value: str | None) -> list[str]:
    if not value:
        return []
    return re.findall(r"[0-9A-Za-z가-힣]+", value)


def _key(value: str | None) -> str:
    return search_key(value)
