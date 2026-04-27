from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from app.normalizer.text import clean_text, has_hangul, has_latin


class BrandRegistryEntry(BaseModel):
    official_en: str
    aliases: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class BrandRegistry(BaseModel):
    entries: list[BrandRegistryEntry] = Field(default_factory=list)


@dataclass(frozen=True)
class BrandMatch:
    official_en: str
    matched_alias: str


class ExternalBrandResolver(Protocol):
    def resolve(self, source_brand_name: str | None, *fallback_texts: str | None) -> str | None: ...

    def close(self) -> None: ...


class BrandResolver:
    def __init__(
        self,
        registry_path: Path,
        external_resolvers: list[ExternalBrandResolver] | None = None,
    ):
        self._aliases: dict[str, str] = {}
        self._scan_aliases: list[tuple[str, str, str]] = []
        self._external_resolvers = external_resolvers or []
        self._load_registry(registry_path)

    def resolve(self, source_brand_name: str | None, *fallback_texts: str | None) -> str | None:
        brand = clean_text(source_brand_name)
        if brand is not None:
            mapped = self._aliases.get(self._key(brand))
            if mapped:
                return mapped

        for text in fallback_texts:
            match = self.match_text(text)
            if match:
                return match.official_en

        should_use_external = brand is None or has_hangul(brand) or not has_latin(brand)
        if should_use_external:
            for resolver in self._external_resolvers:
                mapped = resolver.resolve(brand, *fallback_texts)
                if mapped:
                    return self._clean_latin_brand(mapped)

        if brand is None or has_hangul(brand) or not has_latin(brand):
            return None
        return self._clean_latin_brand(brand)

    def close(self) -> None:
        for resolver in self._external_resolvers:
            resolver.close()

    def match_text(self, value: str | None) -> BrandMatch | None:
        key = self._key(value)
        if not key:
            return None
        for alias_key, alias, official in self._scan_aliases:
            if alias_key and alias_key in key:
                return BrandMatch(official_en=official, matched_alias=alias)
        return None

    def _load_registry(self, registry_path: Path) -> None:
        if not registry_path.exists():
            return
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
        registry = BrandRegistry.model_validate(payload)
        for entry in registry.entries:
            official = self._clean_latin_brand(entry.official_en)
            if official is None:
                continue
            values = [entry.official_en, *entry.aliases]
            for alias in values:
                key = self._key(alias)
                if key:
                    self._aliases[key] = official
                    self._scan_aliases.append((key, alias, official))
        self._scan_aliases.sort(key=lambda item: len(item[0]), reverse=True)

    @staticmethod
    def _key(value: str | None) -> str:
        text = clean_text(value)
        if text is None:
            return ""
        return re.sub(r"[\s\-_./]+", "", text).casefold()

    @staticmethod
    def _clean_latin_brand(value: str | None) -> str | None:
        text = clean_text(value)
        if text is None:
            return None
        text = re.sub(r"\s*브랜드관\s*$", "", text).strip()
        return text or None
