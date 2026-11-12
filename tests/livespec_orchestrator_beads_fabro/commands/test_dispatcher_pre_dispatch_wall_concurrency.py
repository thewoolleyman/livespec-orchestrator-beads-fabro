"""The pre-dispatch wall's independent rows run concurrently and refuse as they did in sequence.

`## Dispatch pre-launch step attribution and concurrency`: pre-launch steps whose
inputs do not depend on another step's result start without waiting for one
another, a refusing step withholds the dispatch with the refusal it produces when
the steps run one after another, and nothing is submitted until every step whose
refusal would withhold the dispatch has completed.

The wall keeps its positions in order, because the ordering is what stops a
dispatch that can never run from spending or writing: the free publication and
ACP-override rows and the session-headroom screen come first and alone; the App
reach probe, the Fabro currency gate and the acceptance-criteria parse (reads
that write nothing to the ledger) form one concurrent group; and the rows that
write a ledger record or spend a model call or a provider renewal (the
Definition-of-Done judgement, the spec-change-tier classification, the
proof-asset store and the Codex credential gate) stay one after another behind
that group, so a dispatch the group refuses reaches none of them.
"""

from __future__ import annotations

import argparse
import threading
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_pre_dispatch_wall as wall

_EXIT_PRECONDITION = 3
_EXIT_UNGRADEABLE = 5
_EXIT_FAILURE = 1
_TIMEOUT_SECONDS = 5.0
_CONCURRENT_ROWS = (
    "app_reach_refusal",
    "fabro_currency_refusal",
    "pre_dispatch_criteria_refusal",
)
_LATER_ROWS = (
    "dod_judgement_refusal",
    "definition_of_done_workflow_refusal",
    "spec_change_tier_refusal",
)


class _Probe:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._lock = threading.Lock()

    def row(self, *, name: str, refusal: str | None = None) -> Callable[..., str | None]:
        def _row(**_: object) -> str | None:
            with self._lock:
                self.calls.append(name)
            return refusal

        return _row


def _install(
    *, monkeypatch: pytest.MonkeyPatch, probe: _Probe, overrides: dict[str, Any] | None = None
) -> None:
    rows = [
        "implementation_pr_override_refusal",
        "acp_node_override_refusal",
        "session_headroom_screen_refusal",
        *_CONCURRENT_ROWS,
        *_LATER_ROWS,
        "proof_assets_refusal_for_items",
        "proof_credentials_refusal_for_items",
        "codex_credential_refusal_for_items",
    ]
    for name in rows:
        monkeypatch.setattr(wall, name, probe.row(name=name))
    monkeypatch.setattr(wall, "credential_wrapper_text", lambda **_: "")
    monkeypatch.setattr(wall, "selection_credential_requirement", lambda **_: object())
    monkeypatch.setattr(wall, "codex_routing_for_dispatch", lambda **_: object())
    for name, replacement in (overrides or {}).items():
        monkeypatch.setattr(wall, name, replacement)


def _run_wall() -> int | None:
    return wall.pre_dispatch_wall_exit(
        args=argparse.Namespace(workflow_name=None),
        repo=cast("Any", None),
        items=[cast("Any", SimpleNamespace(id="bd-1"))],
        journal=cast("Any", None),
    )


def test_independent_rows_start_without_waiting_for_one_another(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _Probe()
    lock = threading.Lock()
    arrived: list[str] = []
    all_arrived = threading.Event()
    overlapped: list[bool] = []

    def waiting_row(**_: object) -> str | None:
        with lock:
            arrived.append("row")
            if len(arrived) == len(_CONCURRENT_ROWS):
                all_arrived.set()
        overlapped.append(all_arrived.wait(timeout=_TIMEOUT_SECONDS))
        return None

    _install(
        monkeypatch=monkeypatch,
        probe=probe,
        overrides={name: waiting_row for name in _CONCURRENT_ROWS},
    )

    assert _run_wall() is None
    assert overlapped == [True] * len(_CONCURRENT_ROWS)


def test_a_refusing_row_withholds_with_the_refusal_the_sequence_produced(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe = _Probe()
    _install(
        monkeypatch=monkeypatch,
        probe=probe,
        overrides={
            "app_reach_refusal": probe.row(name="app_reach_refusal", refusal="reach"),
            "fabro_currency_refusal": probe.row(name="fabro_currency_refusal", refusal="currency"),
        },
    )

    assert _run_wall() == _EXIT_PRECONDITION
    assert capsys.readouterr().err == "reach"
    assert set(_CONCURRENT_ROWS) <= set(probe.calls)
    assert not set(_LATER_ROWS) & set(probe.calls)
    assert "proof_assets_refusal_for_items" not in probe.calls
    assert "codex_credential_refusal_for_items" not in probe.calls


def test_the_exit_code_is_the_refusing_rows_own(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe = _Probe()
    _install(
        monkeypatch=monkeypatch,
        probe=probe,
        overrides={
            "pre_dispatch_criteria_refusal": probe.row(
                name="pre_dispatch_criteria_refusal", refusal="criteria"
            )
        },
    )

    assert _run_wall() == _EXIT_UNGRADEABLE
    assert capsys.readouterr().err == "criteria"


def test_rows_behind_the_group_still_run_one_after_another(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe = _Probe()
    _install(
        monkeypatch=monkeypatch,
        probe=probe,
        overrides={
            "dod_judgement_refusal": probe.row(name="dod_judgement_refusal", refusal="judgement"),
        },
    )

    assert _run_wall() == _EXIT_UNGRADEABLE
    assert capsys.readouterr().err == "judgement"
    assert "spec_change_tier_refusal" not in probe.calls
    assert "proof_assets_refusal_for_items" not in probe.calls


def test_the_dispatch_is_withheld_only_after_a_slow_refusing_row_completes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _Probe()
    release = threading.Event()
    slow_finished: list[bool] = []

    def slow_refusal(**_: object) -> str | None:
        _ = release.wait(timeout=_TIMEOUT_SECONDS)
        slow_finished.append(True)
        return "slow"

    def releasing_row(**_: object) -> str | None:
        release.set()
        return None

    _install(
        monkeypatch=monkeypatch,
        probe=probe,
        overrides={
            "app_reach_refusal": slow_refusal,
            "pre_dispatch_criteria_refusal": releasing_row,
        },
    )

    assert _run_wall() == _EXIT_PRECONDITION
    assert slow_finished == [True]


def test_a_row_that_raises_after_the_refusing_row_does_not_replace_the_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _Probe()

    def raising(**_: object) -> str | None:
        raise RuntimeError("later row")

    _install(
        monkeypatch=monkeypatch,
        probe=probe,
        overrides={
            "app_reach_refusal": probe.row(name="app_reach_refusal", refusal="reach"),
            "pre_dispatch_criteria_refusal": raising,
        },
    )

    assert _run_wall() == _EXIT_PRECONDITION


def test_a_row_that_raises_before_any_refusal_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _Probe()

    def raising(**_: object) -> str | None:
        raise RuntimeError("earlier row")

    _install(
        monkeypatch=monkeypatch,
        probe=probe,
        overrides={
            "app_reach_refusal": raising,
            "pre_dispatch_criteria_refusal": probe.row(
                name="pre_dispatch_criteria_refusal", refusal="criteria"
            ),
        },
    )

    with pytest.raises(RuntimeError, match="earlier row"):
        _ = _run_wall()


def test_a_screen_refusal_runs_none_of_the_concurrent_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _Probe()
    _install(
        monkeypatch=monkeypatch,
        probe=probe,
        overrides={
            "session_headroom_screen_refusal": probe.row(
                name="session_headroom_screen_refusal", refusal="headroom"
            )
        },
    )

    assert _run_wall() == _EXIT_FAILURE
    assert not set(_CONCURRENT_ROWS) & set(probe.calls)
