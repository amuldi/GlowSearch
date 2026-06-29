from dataclasses import dataclass
from typing import Protocol

from app.models.product import ProductSourceRecord


class SourceUnavailableError(RuntimeError):
    pass


class ProductCollector(Protocol):
    name: str

    async def search(self, keyword: str, limit: int) -> list[ProductSourceRecord]:
        ...


@dataclass(frozen=True)
class SearchCriteria:
    brand: str | None = None
    min_price: int | None = None
    max_price: int | None = None
    has_shade: bool | None = None
    limit: int = 24
    record_gaps: bool = True
    index_only: bool = False
