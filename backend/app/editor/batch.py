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
    _CONCURRENCY = 8
    _LINE_TIMEOUT_SECONDS = 6.5

    def __init__(self, search_service: SearchService):
        self._search_service = search_service

    async def batch(self, text: str, *, limit: int = 5) -> EditorBatchResponse:
        parsed_lines = parse_editor_lines(text)
        semaphore = asyncio.Semaphore(self._CONCURRENCY)

        async def resolve(parsed: EditorParsedLine) -> EditorBatchItem:
            async with semaphore:
                try:
                    return await asyncio.wait_for(
                        self._resolve_line(parsed, limit=limit),
                        timeout=self._LINE_TIMEOUT_SECONDS,
                    )
                except TimeoutError:
                    parsed_with_brand = self._with_resolved_brand_en(parsed)
                    return EditorBatchItem(
                        raw_text=parsed.raw_text,
                        parsed=parsed_with_brand,
                        status="수동 확인 필요",
                        candidates=[],
                    )

        items = await asyncio.gather(*(resolve(parsed) for parsed in parsed_lines))
        return EditorBatchResponse(count=len(items), items=list(items))

    async def _resolve_line(self, parsed: EditorParsedLine, *, limit: int) -> EditorBatchItem:
        parsed = self._with_resolved_brand_en(parsed)
        candidates = await self._candidates_for_query(
            parsed,
            parsed.normalized_query,
            limit=limit,
            require_brand=True,
        )
        if not candidates and _should_try_product_fallback(parsed):
            candidates = await self._candidates_for_query(
                parsed,
                parsed.product_query or parsed.normalized_query,
                limit=limit,
                require_brand=False,
            )
        return EditorBatchItem(
            raw_text=parsed.raw_text,
            parsed=parsed,
            status=_status(parsed, candidates),
            candidates=candidates,
        )

    async def _candidates_for_query(
        self,
        parsed: EditorParsedLine,
        query: str,
        *,
        limit: int,
        require_brand: bool,
    ) -> list[EditorProductCandidate]:
        response = await self._search_service.search(
            query,
            SearchCriteria(limit=max(limit, 1), record_gaps=False),
        )
        products = [
            product
            for product in response.results
            if _has_source_link(product)
            and _passes_editor_relevance(parsed, product, require_brand=require_brand)
        ]
        candidates = []
        for product in products:
            score, reasons = _candidate_score(parsed, product)
            candidates.append(
                EditorProductCandidate(
                    product=product,
                    match_score=score,
                    match_reasons=reasons,
                )
            )
        candidates.sort(key=lambda candidate: candidate.match_score, reverse=True)
        return candidates[:limit]

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


def _status(
    parsed: EditorParsedLine,
    candidates: list[EditorProductCandidate],
) -> EditorMatchStatus:
    if not candidates:
        return "수동 확인 필요"
    if parsed.brand_query and not any(_candidate_brand_matches(parsed, candidate.product) for candidate in candidates):
        return "수동 확인 필요"
    if len(candidates) == 1 and _candidate_confirms_identity(parsed, candidates[0].product):
        return "확인됨"
    return "후보 있음"


def _candidate_score(parsed: EditorParsedLine, product: ProductSearchResult) -> tuple[int, list[str]]:
    score = product.quality_score
    reasons: list[str] = []
    if product.source_priority is not None:
        score += max(0, 80 - product.source_priority)
    if product.product_name_en:
        score += 8
        reasons.append("영문 제품명")
    if product.source_url or any(offer.source_url for offer in product.offers):
        score += 10
        reasons.append("source 링크")
    if product.image_url:
        score += 4
        reasons.append("이미지")

    brand_query = _key(parsed.brand_query)
    if brand_query:
        brand_text = _key(" ".join(value for value in [product.brand_ko, product.brand_en] if value))
        if brand_query and brand_query in brand_text:
            score += 40
            reasons.append("브랜드 일치")
        else:
            reasons.append("브랜드 불일치")

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
                " ".join(product.search_keywords or []),
            ]
            if value
        )
    )
    if product_tokens:
        matched = sum(1 for token in product_tokens if token and token in product_text)
        score += matched * 18
        if matched == len(product_tokens):
            score += 20
        if matched:
            reasons.append(f"제품 키워드 {matched}/{len(product_tokens)}")

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
                    " ".join(product.search_keywords or []),
                ]
                if value
            )
        )
        matched_shades = sum(1 for token in shade_tokens if token and token in shade_text)
        score += matched_shades * 45
        if matched_shades:
            reasons.append("호수/컬러 일치")
        if matched_shades == 0:
            score -= 35
            reasons.append("호수/컬러 확인 필요")

    return score, reasons


def _passes_editor_relevance(
    parsed: EditorParsedLine,
    product: ProductSearchResult,
    *,
    require_brand: bool,
) -> bool:
    brand_query = _key(parsed.brand_query)
    product_tokens = [_key(token) for token in _tokens(parsed.product_query)]

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

    if require_brand and brand_query and brand_query not in brand_text:
        return False

    if product_tokens:
        matched_product_tokens = sum(1 for token in product_tokens if token and token in product_text)
        required_matches = len(product_tokens) if len(product_tokens) <= 2 else max(2, len(product_tokens) - 1)
        if matched_product_tokens < required_matches:
            return False

    return bool(product_tokens or brand_query)


def _has_source_link(product: ProductSearchResult) -> bool:
    return bool(product.source_url or any(offer.source_url for offer in product.offers))


def _candidate_confirms_identity(
    parsed: EditorParsedLine,
    product: ProductSearchResult,
) -> bool:
    if not _candidate_brand_matches(parsed, product):
        return False
    shade_tokens = [_key(value) for value in [parsed.shade_code, parsed.shade_name] if value]
    if not shade_tokens:
        return True
    product_text = _product_match_text(product)
    return all(token and token in product_text for token in shade_tokens)


def _candidate_brand_matches(
    parsed: EditorParsedLine,
    product: ProductSearchResult,
) -> bool:
    brand_query = _key(parsed.brand_query)
    if not brand_query:
        return True
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
    return brand_query in brand_text


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
                " ".join(product.search_keywords or []),
            ]
            if value
        )
    )


def _tokens(value: str | None) -> list[str]:
    if not value:
        return []
    return re.findall(r"[0-9A-Za-z가-힣]+", value)


def _should_try_product_fallback(parsed: EditorParsedLine) -> bool:
    product_tokens = [_key(token) for token in _tokens(parsed.product_query)]
    return len([token for token in product_tokens if token]) >= 2


def _key(value: str | None) -> str:
    return search_key(value)
