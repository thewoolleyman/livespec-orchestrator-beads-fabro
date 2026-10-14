"""Hermetic admission tests must not shadow explicitly requested live CLIs."""

import inspect
import os
import runpy
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest


@pytest.mark.parametrize(
    ("live_variable", "live_value"),
    [(None, None), ("LIVESPEC_CODEX_SKILL_PICKER", "1"), ("LIVESPEC_E2E_HARNESS", "real")],
)
def test_cli_isolation_yields_to_explicit_live_acceptance(
    *, monkeypatch: pytest.MonkeyPatch, live_variable: str | None, live_value: str | None
) -> None:
    monkeypatch.delenv("LIVESPEC_CODEX_SKILL_PICKER", raising=False)
    monkeypatch.delenv("LIVESPEC_E2E_HARNESS", raising=False)
    monkeypatch.setenv("PATH", "/real-model-bin")
    if live_variable is not None:
        assert live_value is not None
        monkeypatch.setenv(live_variable, live_value)
    namespace = runpy.run_path(str(Path(__file__).with_name("conftest.py")))
    fixture = cast("Callable[..., None]", inspect.unwrap(namespace["hermetic_pre_admission_judge"]))

    fixture(monkeypatch=monkeypatch, _judgement_cli_bin="/fake-model-bin")

    expected = (
        f"/fake-model-bin{os.pathsep}/real-model-bin"
        if live_variable is None
        else "/real-model-bin"
    )
    assert os.environ["PATH"] == expected
