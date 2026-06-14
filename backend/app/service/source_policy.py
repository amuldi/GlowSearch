from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable

from app.normalizer.text import clean_text


@dataclass(frozen=True)
class SourceProfile:
    prefix: str
    label: str
    priority: int
    kind: str


DEFAULT_SOURCE_PROFILES: tuple[SourceProfile, ...] = (
    SourceProfile("oliveyoung", "Olive Young", 10, "retailer"),
    SourceProfile("musinsa", "Musinsa", 30, "retailer"),
    SourceProfile("coupang", "Coupang", 35, "retailer"),
    SourceProfile("hwahae", "Hwahae", 45, "catalog"),
    SourceProfile("glowpick", "Glowpick", 46, "catalog"),
    SourceProfile("fudejapan", "Fude Japan", 47, "catalog"),
    SourceProfile("official", "Official brand", 20, "brand"),
    SourceProfile("managed", "Managed scraper", 40, "managed"),
    SourceProfile("barcode", "Barcode/GTIN", 50, "catalog"),
    SourceProfile("discovery", "Discovery API", 60, "discovery"),
    SourceProfile("external", "External source", 90, "external"),
)


class SourcePolicy:
    def __init__(
        self,
        *,
        allowed_prefixes: Iterable[str] | None = None,
        profiles: Iterable[SourceProfile] = DEFAULT_SOURCE_PROFILES,
    ):
        self._profiles = sorted(tuple(profiles), key=lambda profile: len(profile.prefix), reverse=True)
        cleaned_allowed = [
            prefix
            for prefix in (clean_text(value) for value in (allowed_prefixes or ()))
            if prefix
        ]
        self._allowed_prefixes = tuple(cleaned_allowed) or None

    def allows(self, source: str | None) -> bool:
        if self._allowed_prefixes is None:
            return True
        return any(self._matches_prefix(source, prefix) for prefix in self._allowed_prefixes)

    def label(self, source: str | None) -> str | None:
        profile = self.profile_for(source)
        if profile is not None:
            return profile.label
        return clean_text(source)

    def priority(self, source: str | None) -> int:
        profile = self.profile_for(source)
        return profile.priority if profile is not None else 1000

    def profile_for(self, source: str | None) -> SourceProfile | None:
        for profile in self._profiles:
            if self._matches_prefix(source, profile.prefix):
                return profile
        return None

    def snapshot(self) -> dict[str, object]:
        return {
            "allowed_prefixes": list(self._allowed_prefixes) if self._allowed_prefixes else ["*"],
            "profiles": [
                {
                    "prefix": profile.prefix,
                    "label": profile.label,
                    "priority": profile.priority,
                    "kind": profile.kind,
                }
                for profile in sorted(self._profiles, key=lambda profile: profile.priority)
            ],
        }

    @staticmethod
    def _matches_prefix(source: str | None, prefix: str) -> bool:
        text = clean_text(source)
        if not text:
            return False
        return text == prefix or text.startswith(f"{prefix}:")
