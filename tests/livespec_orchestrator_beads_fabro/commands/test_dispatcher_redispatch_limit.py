"""The committed across-dispatch limit has no inferred default.

Covers `dispatcher.redispatch_no_progress_limit` of `SPECIFICATION/contracts.md`
section "Quantitative plan-progress limits": a positive committed integer, never
a boolean, with a configuration diagnostic when it is missing or invalid.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    PolicySettingUnreadable,
)
from returns.io import IOResult
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_limit"
_KEY = "dispatcher.redispatch_no_progress_limit"


def _write_config(*, repo: Path, dispatcher: dict[str, object]) -> None:
    config = {"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}
    _ = (repo / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")


def _resolve(*, repo: Path) -> IOResult[int, PolicySettingUnreadable]:
    module = importlib.import_module(_MODULE)
    return cast(
        "IOResult[int, PolicySettingUnreadable]",
        module.resolve_redispatch_no_progress_limit(cwd=repo),
    )


def _diagnostic(*, repo: Path) -> str:
    resolved = _resolve(repo=repo)
    assert not is_successful(resolved)
    return unsafe_perform_io(resolved.failure()).detail


def test_a_positive_committed_limit_is_the_limit(tmp_path: Path) -> None:
    """The committed value is returned unchanged."""
    module_path = (
        Path(__file__).parents[3]
        / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
        / "_dispatcher_redispatch_limit.py"
    )
    assert module_path.is_file()
    _write_config(repo=tmp_path, dispatcher={"redispatch_no_progress_limit": 3})
    resolved = _resolve(repo=tmp_path)
    assert is_successful(resolved)
    assert unsafe_perform_io(resolved.unwrap()) == 3


@pytest.mark.parametrize("value", [0, -1, True, "2", 1.5])
def test_an_invalid_limit_is_a_configuration_diagnostic(tmp_path: Path, value: object) -> None:
    """Zero, negative, boolean, textual and fractional values are all refused."""
    _write_config(repo=tmp_path, dispatcher={"redispatch_no_progress_limit": value})
    assert _KEY in _diagnostic(repo=tmp_path)


def test_a_missing_limit_has_no_implicit_count(tmp_path: Path) -> None:
    """No file and no key are both a diagnostic naming the key, never a default."""
    absent_file = _diagnostic(repo=tmp_path)
    _write_config(repo=tmp_path, dispatcher={})
    absent_key = _diagnostic(repo=tmp_path)
    for detail in (absent_file, absent_key):
        assert _KEY in detail
        assert "committed" in detail
