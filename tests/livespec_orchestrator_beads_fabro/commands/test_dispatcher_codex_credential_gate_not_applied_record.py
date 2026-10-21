"""The journal record a dispatch leaves when the Codex credential gate is SKIPPED.

`bd-ib-meejjz`. Scoping the gate to dispatches that route a node to `codex-acp`
removes a refusal, and a removed refusal is invisible: every surface a reader
has -- the exit code, the operator's stderr, the item's status -- is identical
for "the gate ran and admitted" and "the gate never ran at all". The two have
different causes and different remedies, so the dispatch journal records which
one happened.

IT NAMES THE ROUTING, NOT MERELY THE SKIP. A line saying only that the gate was
not applied cannot be checked against the dispatch it describes: an operator
reading it afterwards has no way to tell a correctly-scoped all-Claude dispatch
from a routing resolution that went wrong and happened to answer "no Codex".
The routing's own `detail` -- the resolved candidate keys it read -- is the
evidence, and it is carried from the single decision rather than re-derived
here, so the record and the gate cannot describe different measurements.

THE TWO CONTROLS ARE WHAT MAKE THE RECORD MEAN ANYTHING:

- A Codex-routed dispatch writes NO such record. Without that, a build
  journaling the line unconditionally would satisfy every assertion below while
  saying nothing about any dispatch.
- An IDLE pass -- an empty selection, which is the drain's common case --
  writes no such record either. The gate returns before the routing is even
  resolved, and a line per idle poll would bury the real ones.
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_deadline import (
    CredentialLifetimeRequirement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_projection import (
    CODEX_FRESHNESS_MARGIN_SECONDS,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_REQUIRED_REMAINING = 18_000

_REQUIREMENT = CredentialLifetimeRequirement(
    execution_allowance_seconds=_REQUIRED_REMAINING - CODEX_FRESHNESS_MARGIN_SECONDS,
    # Deliberately wider than the allowance, so the EXECUTION ALLOWANCE governs
    # and these cases keep grading the one figure they were written against.
    credential_use_window_seconds=_REQUIRED_REMAINING * 10,
    credential_queue_allowance_seconds=86_400,
    margin_seconds=CODEX_FRESHNESS_MARGIN_SECONDS,
    detail="test-resolved requirement",
)

# The routing an all-Claude dispatch resolves, worded as the production
# decision words it. The record has to carry this text, which is what binds the
# line to the measurement rather than to a restatement of it.
_ALL_CLAUDE_DETAIL = (
    "no resolved ACP candidate key names the codex-acp agent; resolved candidate "
    "keys: claude-acp/anthropic/claude-opus-5"
)
_CODEX_DETAIL = "resolved ACP candidate keys naming the codex-acp agent: codex-acp/openai/gpt-5.1"

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_WALL_MODULE = f"{_PACKAGE}._dispatcher_pre_dispatch_wall"
_GATE_MODULE = f"{_PACKAGE}._dispatcher_codex_credential_gate"
_ROUTING_MODULE = f"{_PACKAGE}._dispatcher_codex_routing"


class _RecordingJournal:
    """A journal that keeps what was appended instead of serializing it."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def append(self, *, record: dict[str, Any]) -> None:
        self.records.append(record)


def _work_item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="bug",
        status="ready",
        title="Scope the Codex credential gate to dispatches that route to Codex",
        description="Record which dispatches the gate was not applied to.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-14T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _wall_args(*, repo: Path) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(repo),
        journal=str(repo / "journal.jsonl"),
        item="bd-ib-meejjz",
        as_json=False,
        skip_ledger_check=True,
        workflow_name=None,
    )


def _stub_wall(
    *, monkeypatch: pytest.MonkeyPatch, wall: ModuleType, routes_codex: bool, detail: str
) -> None:
    """Neutralize every sibling refusal and declare this dispatch's routing.

    The requirement is stood in for the reason the sibling refusals are: it
    reads the selected workflow off a repository that does not exist here, and
    a workflow-fault deferral would skip the gate for a reason unrelated to
    routing -- which would make the record's absence prove nothing.
    """
    routing = importlib.import_module(_ROUTING_MODULE)
    decision = routing.CodexRouting(routes_codex=routes_codex, detail=detail)
    monkeypatch.setattr(wall, "codex_routing_for_dispatch", lambda **_kwargs: decision)
    monkeypatch.setattr(wall, "implementation_pr_override_refusal", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "fabro_currency_refusal", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "pre_dispatch_criteria_refusal", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "proof_assets_refusal_for_items", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "proof_credentials_refusal_for_items", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "credential_wrapper_text", lambda **_kwargs: "")
    monkeypatch.setattr(wall, "selection_credential_requirement", lambda **_kwargs: _REQUIREMENT)


def _not_applied_records(*, journal: _RecordingJournal, gate: ModuleType) -> list[dict[str, Any]]:
    """Every record under the not-applied stage, selected by STAGE not position.

    The Fabro currency gate journals ahead of this one for a target that
    declares no server, so index 0 is not this gate's record.
    """
    return [
        record
        for record in journal.records
        if record["stage"] == gate.CODEX_CREDENTIAL_GATE_NOT_APPLIED_STAGE
    ]


def test_an_all_claude_dispatch_records_the_gate_as_not_applied_with_its_routing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One record, naming the items it covered and the routing that decided it."""
    wall = importlib.import_module(_WALL_MODULE)
    gate = importlib.import_module(_GATE_MODULE)
    journal = _RecordingJournal()
    _stub_wall(monkeypatch=monkeypatch, wall=wall, routes_codex=False, detail=_ALL_CLAUDE_DETAIL)

    exit_code = wall.pre_dispatch_wall_exit(
        args=_wall_args(repo=tmp_path),
        repo=tmp_path,
        items=[_work_item(item_id="bd-ib-meejjz"), _work_item(item_id="bd-ib-qieqc6")],
        journal=journal,
    )

    assert exit_code is None
    records = _not_applied_records(journal=journal, gate=gate)
    assert len(records) == 1
    record = records[0]
    assert record["work_item_ids"] == ["bd-ib-meejjz", "bd-ib-qieqc6"]
    assert record["routing"] == _ALL_CLAUDE_DETAIL
    # The stage name is its own value: a reader filtering the journal must be
    # able to tell this line from the gate's REFUSAL line, which is a different
    # finding with a different remedy.
    assert record["stage"] != gate.CODEX_CREDENTIAL_GATE_STAGE
    # Nothing credential-shaped reaches the record. The gate read no credential
    # at all on this path, so there is nothing to redact -- and that is the
    # property worth pinning, because a build that journaled its grade here
    # would have had to take one.
    assert "token" not in json.dumps(record, sort_keys=True)


def test_a_codex_routed_dispatch_records_no_not_applied_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CONTROL: the record is about the dispatches the gate was skipped for."""
    wall = importlib.import_module(_WALL_MODULE)
    gate = importlib.import_module(_GATE_MODULE)
    journal = _RecordingJournal()
    _stub_wall(monkeypatch=monkeypatch, wall=wall, routes_codex=True, detail=_CODEX_DETAIL)

    _ = wall.pre_dispatch_wall_exit(
        args=_wall_args(repo=tmp_path),
        repo=tmp_path,
        items=[_work_item(item_id="bd-ib-meejjz")],
        journal=journal,
    )

    assert _not_applied_records(journal=journal, gate=gate) == []


def test_an_idle_pass_records_no_not_applied_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The drain's common case writes nothing: there was no selection to cover.

    The routing stand-in here is the all-Claude one, so a build that journaled
    before checking the selection would produce exactly the line this case
    forbids -- which is what makes the empty journal evidence about the ORDER
    rather than about the routing.
    """
    wall = importlib.import_module(_WALL_MODULE)
    gate = importlib.import_module(_GATE_MODULE)
    journal = _RecordingJournal()
    _stub_wall(monkeypatch=monkeypatch, wall=wall, routes_codex=False, detail=_ALL_CLAUDE_DETAIL)

    exit_code = wall.pre_dispatch_wall_exit(
        args=_wall_args(repo=tmp_path), repo=tmp_path, items=[], journal=journal
    )

    assert exit_code is None
    assert _not_applied_records(journal=journal, gate=gate) == []
