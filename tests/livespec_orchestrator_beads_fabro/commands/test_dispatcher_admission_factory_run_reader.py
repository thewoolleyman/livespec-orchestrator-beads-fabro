"""Admission's production wiring for host-wide factory hold evidence."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"


def test_admission_passes_its_production_factory_reader_to_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The admission verdict observes failed runs recorded by peer repositories."""
    admission = importlib.import_module(f"{_PACKAGE}._dispatcher_admission")
    verdicts = importlib.import_module(f"{_PACKAGE}._acp_preflight_verdict")
    rework_module = importlib.import_module(f"{_PACKAGE}._dispatcher_rework_admission")
    constructed: list[Path] = []
    resolved: list[dict[str, object]] = []

    class _FactoryRunReader:
        def __init__(self, *, repo: Path) -> None:
            constructed.append(repo)

    def _resolve(**kwargs: object) -> object:
        resolved.append(kwargs)
        return verdicts.AcpPreflightVerdict(fallback_enabled=False)

    monkeypatch.setattr(admission, "FactoryRunReader", _FactoryRunReader, raising=False)
    monkeypatch.setattr(admission, "resolve_acp_preflight", _resolve)
    monkeypatch.setattr(admission, "session_headroom_policy", lambda **_: None)
    monkeypatch.setattr(admission, "rework_pending_candidates", lambda **_: ())
    monkeypatch.setattr(admission, "filter_eligible_candidates", lambda **_: ([], []))
    monkeypatch.setattr(
        admission, "claimed_active_accounting", lambda **_: SimpleNamespace(active_count=0)
    )
    monkeypatch.setattr(
        admission, "admit_rework", lambda **_: SimpleNamespace(admitted=(), deferred=())
    )
    monkeypatch.setattr(
        admission,
        "plan_admissions",
        lambda **_: SimpleNamespace(approved=(), admitted=(), held=()),
    )
    monkeypatch.setattr(admission, "store_config", lambda **_: object())

    _ = admission.admit_and_select(
        repo=tmp_path,
        items=[],
        candidates=[],
        journal=SimpleNamespace(path=None),
        enforce_cap=False,
        rework=rework_module.ReworkPass(),
    )

    assert constructed == [tmp_path]
    assert len(resolved) == 1
    assert isinstance(resolved[0]["factory_runs"], _FactoryRunReader)
