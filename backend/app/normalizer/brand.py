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
    matched_text: str | None = None


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
                return BrandMatch(official_en=official, matched_alias=alias, matched_text=alias)
        text = clean_text(value)
        if text:
            for _, alias, official in self._scan_aliases:
                matched_text = self._loose_alias_match(text, alias)
                if matched_text:
                    return BrandMatch(
                        official_en=official,
                        matched_alias=alias,
                        matched_text=matched_text,
                    )
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

    @classmethod
    def _loose_alias_match(cls, text: str, alias: str) -> str | None:
        if not has_hangul(alias):
            return None
        candidates = re.findall(r"[0-9A-Za-z가-힣ㄱ-ㅎㅏ-ㅣ]+", text)
        candidates.append(cls._key(text))
        seen: set[str] = set()
        for candidate in candidates:
            key = cls._key(candidate)
            if not key or key in seen:
                continue
            seen.add(key)
            if cls._is_loose_brand_prefix(key, cls._key(alias)):
                return candidate
        return None

    @classmethod
    def _is_loose_brand_prefix(cls, query_key: str, alias_key: str) -> bool:
        if len(query_key) < 2 or len(alias_key) < 2:
            return False

        query_index = 0
        alias_index = 0
        while query_index < len(query_key) and alias_index < len(alias_key):
            query_char = query_key[query_index]
            alias_char = alias_key[alias_index]
            if query_char == alias_char:
                query_index += 1
                alias_index += 1
                continue
            if cls._is_compat_initial(query_char) and query_char == cls._hangul_initial(alias_char):
                query_index += 1
                alias_index += 1
                continue
            return False

        return query_index == len(query_key) or alias_index == len(alias_key)

    @staticmethod
    def _is_compat_initial(char: str) -> bool:
        return char in "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"

    @staticmethod
    def _hangul_initial(char: str) -> str | None:
        initials = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
        code = ord(char)
        if not 0xAC00 <= code <= 0xD7A3:
            return None
        return initials[(code - 0xAC00) // 588]

    @staticmethod
    def _clean_latin_brand(value: str | None) -> str | None:
        text = clean_text(value)
        if text is None:
            return None
        text = re.sub(r"\s*브랜드관\s*$", "", text).strip()
        return text or None
