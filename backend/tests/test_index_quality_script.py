from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_index_quality.py"


def _load_audit_module():
    spec = importlib.util.spec_from_file_location("audit_index_quality_script", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_index_quality_script_defaults_to_all_index_products(monkeypatch) -> None:
    module = _load_audit_module()
    monkeypatch.setattr(sys, "argv", ["audit_index_quality.py"])

    args = module.parse_args()

    assert args.limit is None
    assert args.max_issues == 80
    assert args.max_targets == 40
