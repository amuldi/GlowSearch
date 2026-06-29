from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "smoke_search.py"


def _load_smoke_search_module():
    spec = importlib.util.spec_from_file_location("smoke_search_script", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_smoke_search_expectations_parse_query_display_pairs() -> None:
    module = _load_smoke_search_module()

    expectations = module._parse_expectations(
        [
            "페리페라 스키니브로우=스피디 스키니 브로우",
            "오렌즈 글로이 티어=글로이 티어 원데이",
        ]
    )

    assert expectations == {
        "페리페라 스키니브로우": "스피디 스키니 브로우",
        "오렌즈 글로이 티어": "글로이 티어 원데이",
    }


def test_smoke_search_expectations_reject_invalid_pairs() -> None:
    module = _load_smoke_search_module()

    with pytest.raises(ValueError):
        module._parse_expectations(["페리페라 스키니브로우"])


def test_smoke_search_display_name_prefers_curated_display_name() -> None:
    module = _load_smoke_search_module()

    display_name = module._display_name_from_result(
        {
            "brand_ko": "페리페라",
            "product_name_ko": "[6월 올영픽] 페리페라 스피디 스키니 브로우 8 Colors (단품/더블)",
            "product_name_display_ko": "스피디 스키니 브로우",
        }
    )

    assert display_name == "스피디 스키니 브로우"
