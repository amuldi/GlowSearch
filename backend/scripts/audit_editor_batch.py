from __future__ import annotations

# ruff: noqa: E402

import argparse
import asyncio
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import Settings


EDITOR_SAMPLE_TEXT = "\n".join(
    [
        "헤라 파우더 #13N1",
        "어반디케이 파우더",
        "롬앤 쉐딩 #그레이쿨",
        "페리페라 스키니브로우",
        "클리오 치즈냥이",
        "키스미 아이브로우",
        "뮤드 브로우카라",
        "하밍 젤리 에어 치크 7호",
        "캔메이크 아라 카푸치노",
        "홀리카 팔레트 #핑크올로지",
        "어반디케이 문더스트 #글림락",
        "하트퍼센트 립베이스",
        "페리페라 포근 픽싱 틴트 19호",
        "아멜리 하이라이터 #432",
        "오프라 하이라이터",
        "머지 더블 글레이즈 #브레이브미",
        "비디비치 틴트밤 #카라멜허그",
    ]
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit deployed GlowSearch editor batch coverage and local verified catalog size."
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Backend URL to audit. Example: https://glowsearch-backend.onrender.com",
    )
    parser.add_argument("--text", default=EDITOR_SAMPLE_TEXT, help="Batch input text.")
    parser.add_argument("--limit", type=int, default=5, help="Candidate limit per editor line.")
    parser.add_argument("--timeout", type=float, default=40.0, help="HTTP timeout seconds.")
    parser.add_argument(
        "--catalog-path",
        type=Path,
        default=None,
        help="verified_products.json path. Defaults to Settings().verified_catalog_path.",
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    settings = Settings()
    catalog_path = args.catalog_path or settings.verified_catalog_path
    payload: dict[str, Any] = {
        "local_head": _git_head(),
        "verified_catalog": _catalog_stats(catalog_path),
    }
    if args.base_url:
        payload["remote"] = await _remote_audit(args.base_url, args.text, args.limit, args.timeout)

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


async def _remote_audit(
    base_url: str,
    text: str,
    limit: int,
    timeout: float,
) -> dict[str, Any]:
    normalized_base_url = base_url.rstrip("/")
    async with httpx.AsyncClient(base_url=normalized_base_url, timeout=max(timeout, 0.1)) as client:
        health = await _json_or_error(client, "GET", "/health")
        diagnostics = await _json_or_error(client, "GET", "/diagnostics")
        editor_batch = await _json_or_error(
            client,
            "POST",
            "/editor/batch",
            json={"text": text, "limit": max(limit, 1)},
        )

    return {
        "base_url": normalized_base_url,
        "health": health,
        "diagnostics_summary": _diagnostics_summary(diagnostics),
        "editor_batch_summary": _editor_batch_summary(editor_batch),
    }


async def _json_or_error(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    **kwargs: Any,
) -> Any:
    try:
        response = await client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def _catalog_stats(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}

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


def _catalog_sources(item: dict[str, Any]) -> set[str]:
    sources: set[str] = set()
    source = item.get("source")
    if isinstance(source, str) and source:
        sources.add(source.split(":", 1)[0])
    source_url = item.get("source_url")
    if not sources and isinstance(source_url, str):
        inferred_source = _source_from_url(source_url)
        if inferred_source:
            sources.add(inferred_source)
    for offer in item.get("offers") or []:
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


def _diagnostics_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("error"):
        return payload if isinstance(payload, dict) else {"error": "invalid diagnostics payload"}
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    index = payload.get("index") if isinstance(payload.get("index"), dict) else {}
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    catalog_jobs = payload.get("catalog_jobs") if isinstance(payload.get("catalog_jobs"), dict) else {}
    catalog_job_stats = catalog_jobs.get("stats") if isinstance(catalog_jobs.get("stats"), dict) else {}
    return {
        "release_source_prefixes": config.get("result_source_prefixes"),
        "adapters_enabled": {
            "oliveyoung_public_api": config.get("oliveyoung_public_api_enabled"),
            "musinsa": config.get("musinsa_api_enabled"),
            "oliveyoung_global": config.get("oliveyoung_global_api_enabled"),
            "official_brand": config.get("official_brand_api_enabled"),
            "global_discovery": config.get("global_discovery_api_enabled"),
            "managed_search": config.get("managed_search_api_enabled"),
        },
        "index": {
            "product_count": index.get("product_count"),
            "query_count": index.get("query_count"),
            "search_gap_count": index.get("search_gap_count"),
            "last_refreshed_at": index.get("last_refreshed_at"),
        },
        "metrics": {
            "search_count": metrics.get("search_count"),
            "index_hits": metrics.get("index_hits"),
            "index_misses": metrics.get("index_misses"),
            "search_gaps": metrics.get("search_gaps"),
            "sources": metrics.get("sources"),
            "last_source_errors": metrics.get("last_source_errors"),
        },
        "catalog_jobs": catalog_job_stats,
        "verified_catalog": payload.get("verified_catalog"),
        "adapter_readiness": payload.get("adapter_readiness"),
    }


def _editor_batch_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("error"):
        return payload if isinstance(payload, dict) else {"error": "invalid editor batch payload"}
    items = payload.get("items", [])
    rows = [item for item in items if isinstance(item, dict)]
    status_counts = Counter(str(item.get("status") or "") for item in rows)
    candidate_rows = sum(1 for item in rows if item.get("candidates"))
    source_rows = 0
    brand_en_rows = 0
    product_name_en_rows = 0
    missing_rows: list[str] = []
    row_summaries: list[dict[str, Any]] = []
    for item in rows:
        candidates = item.get("candidates") if isinstance(item.get("candidates"), list) else []
        first_product = None
        if candidates and isinstance(candidates[0], dict):
            first_product = candidates[0].get("product")
        parsed = item.get("parsed") if isinstance(item.get("parsed"), dict) else {}
        if isinstance(first_product, dict):
            if first_product.get("source_url") or first_product.get("source_product_id"):
                source_rows += 1
            if first_product.get("brand_en"):
                brand_en_rows += 1
            if first_product.get("product_name_en"):
                product_name_en_rows += 1
        elif parsed.get("brand_en"):
            brand_en_rows += 1
        if not candidates:
            missing_rows.append(str(item.get("raw_text") or ""))
        row_summaries.append(
            {
                "raw_text": item.get("raw_text"),
                "status": item.get("status"),
                "candidate_count": len(candidates),
                "parsed": {
                    "brand_query": parsed.get("brand_query"),
                    "brand_en": parsed.get("brand_en"),
                    "product_query": parsed.get("product_query"),
                    "shade_code": parsed.get("shade_code"),
                    "shade_name": parsed.get("shade_name"),
                },
                "top_candidate": _candidate_summary(first_product),
            }
        )

    return {
        "count": payload.get("count"),
        "status_counts": dict(sorted(status_counts.items())),
        "rows_with_candidates": candidate_rows,
        "rows_with_source_reference": source_rows,
        "rows_with_brand_en": brand_en_rows,
        "rows_with_product_name_en": product_name_en_rows,
        "manual_rows": missing_rows,
        "rows": row_summaries,
    }


def _candidate_summary(product: Any) -> dict[str, Any] | None:
    if not isinstance(product, dict):
        return None
    offers = product.get("offers") if isinstance(product.get("offers"), list) else []
    return {
        "brand_ko": product.get("brand_ko"),
        "brand_en": product.get("brand_en"),
        "product_name_ko": product.get("product_name_ko"),
        "product_name_en": product.get("product_name_en"),
        "shade": product.get("shade"),
        "source": product.get("source"),
        "source_url": product.get("source_url"),
        "offer_sources": [
            offer.get("source") for offer in offers if isinstance(offer, dict) and offer.get("source")
        ],
        "enrichment_missing_fields": product.get("enrichment_missing_fields"),
    }


def _git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
