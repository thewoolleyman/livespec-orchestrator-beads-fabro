"""The WIP-capture receipt is written AFTER the state change it must not delay."""

from __future__ import annotations

import argparse
import importlib
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_grade import (
    ACTION_ABSENT_RUN_RELEASE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_recovery import (
    ClaimRecoveryRequest,
)

_SELECTION = "livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection"
_RECOVERY = "livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_recovery"
_RUN = "01ORDERRUN"


@dataclass(frozen=True, kw_only=True)
class _Outcome:
    status: str = "blocked"
    stage: str = "fabro-run"
    detail: str = "ordinary terminal"
    merge_sha: str | None = None
    fabro_run_id: str | None = _RUN
    merge_wait_handed_off: bool = False


def _spy(*, calls: list[str], name: str, result: Any = None) -> Any:
    def spy(*_args: object, **_kwargs: object) -> Any:
        calls.append(name)
        return result

    return spy


def test_loop_selection_records_receipt_after_every_state_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    selection = importlib.import_module(_SELECTION)
    calls: list[str] = []
    for name, result in (
        ("record_provider_exhaustion_if_observed", None),
        ("record_dead_implementer_truncation_if_observed", None),
        ("preserve_terminated_run_work", None),
        ("record_groom_draft", False),
        ("record_base_advanced_after_arming", None),
        ("record_merge_wait_handed_off", None),
        ("escalate_needs_human_block", None),
        ("record_needs_human_cause", None),
        ("dispose_terminal_routing", None),
        ("emit_calibration", None),
        ("record_wip_capture_receipt", None),
    ):
        monkeypatch.setattr(selection, name, _spy(calls=calls, name=name, result=result))
    journal = SimpleNamespace(path=tmp_path / "journal", append=_spy(calls=[], name="append"))
    outcome = _Outcome()

    selection.post_run_dispositions(
        args=argparse.Namespace(close_on_merge=False, fabro_factory_target=None),
        repo=tmp_path,
        item=SimpleNamespace(id="bd-ib-order"),
        outcome=outcome,
        journal=journal,
        wall_clock_seconds=0.0,
        dispatch_context_size=0,
        token_supplier=lambda: "",
    )

    assert calls[-1] == "record_wip_capture_receipt"
    assert calls.index("record_wip_capture_receipt") > calls.index("escalate_needs_human_block")


@pytest.mark.parametrize(
    ("bounces", "detail", "expected_detail"),
    [
        (
            True,
            "ordinary failed terminal",
            "LIVESPEC_NON_CONVERGED: an adopted cycle ceiling was exceeded",
        ),
        # Equality produces no contributor, so a healthy terminal remains owned
        # by its ordinary routing instead of manufacturing a bounce.
        (False, "ordinary failed terminal", "ordinary failed terminal"),
        (
            True,
            "LIVESPEC_NEEDS_HUMAN: operator decision",
            "LIVESPEC_NEEDS_HUMAN: operator decision",
        ),
        (
            True,
            "LIVESPEC_RECAPTURE_EXHAUSTED: proof record",
            "LIVESPEC_RECAPTURE_EXHAUSTED: proof record",
        ),
    ],
)
def test_terminal_runtime_verdict_routes_only_an_unowned_failed_outcome(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    bounces,
    detail: str,
    expected_detail: str,
) -> None:
    """A terminal ceiling verdict reaches the existing sanctioned bounce."""
    selection = importlib.import_module(_SELECTION)
    routed: list[_Outcome] = []
    for name, result in (
        ("record_provider_exhaustion_if_observed", None),
        ("record_dead_implementer_truncation_if_observed", None),
        ("preserve_terminated_run_work", None),
        ("record_groom_draft", False),
        ("record_base_advanced_after_arming", None),
        ("record_merge_wait_handed_off", None),
        ("escalate_needs_human_block", None),
        ("record_needs_human_cause", None),
        ("emit_calibration", None),
        ("record_wip_capture_receipt", None),
    ):
        monkeypatch.setattr(selection, name, _spy(calls=[], name=name, result=result))
    monkeypatch.setattr(
        selection,
        "record_dispatch_runtime_convergence",
        lambda **_: SimpleNamespace(
            bounces=bounces, as_reason=lambda: "an adopted cycle ceiling was exceeded"
        ),
    )
    monkeypatch.setattr(
        selection,
        "dispose_terminal_routing",
        lambda **kwargs: routed.append(kwargs["outcome"]),
    )

    selection.post_run_dispositions(
        args=argparse.Namespace(close_on_merge=False, fabro_factory_target=None),
        repo=tmp_path,
        item=SimpleNamespace(id="bd-ib-order"),
        outcome=_Outcome(status="failed", detail=detail),
        journal=SimpleNamespace(path=tmp_path / "journal", append=lambda **_: None),
        wall_clock_seconds=0.0,
        dispatch_context_size=0,
        token_supplier=lambda: "",
    )

    assert [outcome.detail for outcome in routed] == [expected_detail]


def test_stranded_release_records_receipt_only_after_the_transition(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recovery = importlib.import_module(_RECOVERY)
    calls: list[str] = []
    monkeypatch.setattr(recovery, "record_wip_capture_receipt", _spy(calls=calls, name="receipt"))
    monkeypatch.setattr(
        recovery, "establish_journal_record", _spy(calls=calls, name="journal", result="written")
    )
    monkeypatch.setattr(
        recovery, "establish_comment", _spy(calls=calls, name="comment", result="written")
    )
    monkeypatch.setattr(recovery, "claim_row", _spy(calls=calls, name="reread", result=object()))
    monkeypatch.setattr(recovery, "claim_unchanged", lambda **_kwargs: True)
    monkeypatch.setattr(recovery, "_transition", _spy(calls=calls, name="transition"))
    request = ClaimRecoveryRequest(
        item=SimpleNamespace(id="bd-ib-order"),  # type: ignore[arg-type]
        run_id=_RUN,
        factory_name="petri",
        factory_server_url=None,
        action=ACTION_ABSENT_RUN_RELEASE,
    )

    recovery._write_release_effects(  # noqa: SLF001
        repo=tmp_path,
        journal=SimpleNamespace(),  # type: ignore[arg-type]
        request=request,
    )

    assert calls == ["journal", "comment", "reread", "transition", "receipt"]


def test_stranded_release_writes_no_receipt_when_the_transition_holds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recovery = importlib.import_module(_RECOVERY)
    calls: list[str] = []
    monkeypatch.setattr(recovery, "record_wip_capture_receipt", _spy(calls=calls, name="receipt"))
    monkeypatch.setattr(recovery, "establish_journal_record", lambda **_kwargs: "written")
    monkeypatch.setattr(recovery, "establish_comment", lambda **_kwargs: "written")
    monkeypatch.setattr(recovery, "claim_row", lambda **_kwargs: object())
    monkeypatch.setattr(recovery, "claim_unchanged", lambda **_kwargs: True)
    monkeypatch.setattr(recovery, "_transition", lambda **_kwargs: "effect-unobservable")
    request = ClaimRecoveryRequest(
        item=SimpleNamespace(id="bd-ib-order"),  # type: ignore[arg-type]
        run_id=_RUN,
        factory_name="petri",
        factory_server_url=None,
        action=ACTION_ABSENT_RUN_RELEASE,
    )

    recovery._write_release_effects(  # noqa: SLF001
        repo=tmp_path,
        journal=SimpleNamespace(),  # type: ignore[arg-type]
        request=request,
    )

    assert calls == []
