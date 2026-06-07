import asyncio

import pytest

from app.cache.ttl import AsyncTTLCache
from app.data_collector.base import SearchCriteria
from app.index.store import JsonProductIndexStore
from app.models.product import ProductSourceRecord
from app.normalizer.brand import BrandResolver
from app.normalizer.product import ProductNormalizer
from app.service.search_service import SearchService, _CollectedResult


class SlowCollector:
    name = "slow"

    def __init__(self) -> None:
        self.calls = 0

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        self.calls += 1
        await asyncio.sleep(0.05)
        return [
            ProductSourceRecord(
                source_brand_name="롬앤",
                product_name_ko="롬앤 느린 틴트",
                regular_price=15000,
                source="slow",
            )
        ]


class UpdatingCollector:
    name = "updating"

    def __init__(self) -> None:
        self.calls = 0

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        self.calls += 1
        return [
            ProductSourceRecord(
                source_brand_name="롬앤",
                product_name_ko="롬앤 글래스팅 틴트",
                regular_price=15000,
                currency="KRW",
                source="oliveyoung",
                source_product_id="A1",
            )
        ]


def _normalizer(tmp_path) -> ProductNormalizer:
    registry_path = tmp_path / "brand_registry.json"
    registry_path.write_text(
        '{"entries":[{"official_en":"rom&nd","aliases":["롬앤","romand"],"sources":[]}]}',
        encoding="utf-8",
    )
    return ProductNormalizer(
        BrandResolver(registry_path),
        base_url="https://www.oliveyoung.co.kr",
    )


async def _seed_index(store: JsonProductIndexStore, price: int = 13000) -> None:
    await store.upsert(
        [
            ProductSourceRecord(
                source_brand_name="롬앤",
                product_name_ko="롬앤 글래스팅 틴트",
                regular_price=price,
                currency="KRW",
                source="oliveyoung",
                source_product_id="A1",
            )
        ],
        queries=["롬앤 틴트"],
    )


@pytest.mark.asyncio
async def test_search_service_returns_fresh_index_without_waiting_for_collectors(tmp_path) -> None:
    store = JsonProductIndexStore(tmp_path / "product_index.json")
    await _seed_index(store)
    slow = SlowCollector()
    service = SearchService(
        collectors=[slow],
        normalizer=_normalizer(tmp_path),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        index_store=store,
        source_time_budget_seconds=0.01,
    )

    response = await service.search("롬앤 틴트", SearchCriteria(limit=24))

    assert response.count == 1
    assert response.results[0].price == 13000
    assert slow.calls == 0


@pytest.mark.asyncio
async def test_search_service_returns_stale_index_and_revalidates(tmp_path) -> None:
    store = JsonProductIndexStore(
        tmp_path / "product_index.json",
        fresh_ttl_seconds=0,
        stale_ttl_seconds=60,
    )
    await _seed_index(store, price=13000)
    collector = UpdatingCollector()
    service = SearchService(
        collectors=[collector],
        normalizer=_normalizer(tmp_path),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        index_store=store,
        source_time_budget_seconds=0.5,
        stale_revalidate_enabled=True,
    )

    response = await service.search("롬앤 틴트", SearchCriteria(limit=24))
    assert response.results[0].price == 13000

    for _ in range(20):
        if collector.calls:
            break
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.01)

    refreshed = await service.search("롬앤 틴트", SearchCriteria(limit=24))
    await service.close()

    assert collector.calls >= 1
    assert refreshed.results[0].price == 15000


@pytest.mark.asyncio
async def test_search_service_enforces_source_time_budget(tmp_path) -> None:
    slow = SlowCollector()
    service = SearchService(
        collectors=[slow],
        normalizer=_normalizer(tmp_path),
        cache=AsyncTTLCache[_CollectedResult](ttl_seconds=60),
        source_time_budget_seconds=0.001,
    )

    response = await service.search("롬앤 틴트", SearchCriteria(limit=24))

    assert response.count == 0
    assert response.source_errors == ["slow: request timed out"]
