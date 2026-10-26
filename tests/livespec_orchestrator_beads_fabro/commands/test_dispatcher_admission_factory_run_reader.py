"""Admission's production wiring for host-wide factory hold evidence."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"


class _Journal:
    path = None

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _patch_admission_basics(
    *, admission: object, monkeypatch: pytest.MonkeyPatch, resolved: list[dict[str, object]]
) -> None:
    verdicts = importlib.import_module(f"{_PACKAGE}._acp_preflight_verdict")

    def _resolve(**kwargs: object) -> object:
        resolved.append(kwargs)
        return verdicts.AcpPreflightVerdict(fallback_enabled=False)

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


def test_admission_confirmation_callback_runs_and_journals_one_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The admission-only callback turns preflight confirmation into a factory attempt."""
    admission = importlib.import_module(f"{_PACKAGE}._dispatcher_admission")
    rework_module = importlib.import_module(f"{_PACKAGE}._dispatcher_rework_admission")
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    resolved: list[dict[str, object]] = []
    calls: list[dict[str, object]] = []

    def _run(**kwargs: object) -> object:
        calls.append(kwargs)
        return SimpleNamespace(
            ending="turn-completed",
            hold_record={"stage": "acp-availability-observed"},
            journal_record={"stage": "acp-availability-confirmation"},
            attempt_cost_record={"stage": "attempt-cost"},
        )

    _patch_admission_basics(admission=admission, monkeypatch=monkeypatch, resolved=resolved)
    monkeypatch.setattr(admission, "run_availability_probe", _run, raising=False)
    journal = _Journal()
    owner = SimpleNamespace(id="bd-ib-owner")

    _ = admission.admit_and_select(
        repo=tmp_path,
        items=[owner],
        candidates=[owner],
        journal=journal,
        enforce_cap=False,
        rework=rework_module.ReworkPass(),
    )

    confirm = resolved[0]["confirm"]
    assert callable(confirm)
    candidate = schema.AcpCandidate(
        adapter=adapters.AcpAdapter(command="claude-code-acp"),
        identity=schema.AcpCandidateIdentity(
            display_name="Claude", candidate_key="claude", availability_key="anthropic"
        ),
    )
    assert (
        confirm(
            candidate=candidate,
            builtin=True,
            observation_ids=("expired-observation",),
            timeout_seconds=120,
        )
        == "turn-completed"
    )
    assert calls == [
        {
            "repo": tmp_path,
            "candidate": candidate,
            "builtin": True,
            "work_item_id": "bd-ib-owner",
            "observation_ids": ("expired-observation",),
            "now_iso": resolved[0]["now_iso"],
            "timeout_seconds": 120,
        }
    ]
    assert journal.records == [
        {"stage": "acp-availability-observed"},
        {"stage": "acp-availability-confirmation"},
        {"stage": "attempt-cost"},
    ]


def test_loop_wave_passes_its_production_factory_reader_to_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wait's pre-admission verdict shares the factory-native evidence source."""
    wave = importlib.import_module(f"{_PACKAGE}._dispatcher_loop_wave")
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

    monkeypatch.setattr(wave, "FactoryRunReader", _FactoryRunReader, raising=False)
    monkeypatch.setattr(wave, "resolve_acp_preflight", _resolve)
    monkeypatch.setattr(wave, "await_usable_credential", lambda **_: None)
    monkeypatch.setattr(wave, "_admit_and_dispatch_loop_wave", lambda **_: [])

    outcomes = wave.dispatch_loop_wave(
        args=SimpleNamespace(budget=1),
        repo=tmp_path,
        items=[],
        selected_candidates=[],
        journal=SimpleNamespace(path=None),
        janitor=None,
        rework=rework_module.ReworkPass(),
    )

    assert outcomes == []
    assert constructed == [tmp_path]
    assert len(resolved) == 1
    assert isinstance(resolved[0]["factory_runs"], _FactoryRunReader)
