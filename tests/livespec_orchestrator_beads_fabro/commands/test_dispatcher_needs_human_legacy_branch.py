"""Coverage for the Red-only legacy guard in test_dispatcher_needs_human."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_needs_human_test_module() -> ModuleType:
    module_path = Path(__file__).with_name("test_dispatcher_needs_human.py")
    spec = importlib.util.spec_from_file_location(
        "test_dispatcher_needs_human_coverage_target", module_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_legacy_resolver_guard_branch_is_covered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_needs_human_test_module()
    monkeypatch.setattr(
        module.loop_selection, "resolve_or_bounce_needs_human", object(), raising=False
    )

    module.test_dispatcher_pass_leaves_blocked_needs_human_item_blocked(
        tmp_path=tmp_path, monkeypatch=monkeypatch
    )
