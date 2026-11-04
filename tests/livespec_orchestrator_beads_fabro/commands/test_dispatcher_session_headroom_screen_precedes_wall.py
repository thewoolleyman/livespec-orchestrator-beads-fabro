"""The session-headroom admission screen runs BEFORE the expensive pre-dispatch rows.

`bd-ib-tsrkqf`. The Dispatcher's admission session-headroom assessment used to run
inside the admission valve, which every dispatch reaches only AFTER the whole
pre-dispatch wall. A dispatch that assessment was going to refuse therefore paid
for the App reach probe, the Definition-of-Done judgement (a model call), the
proof-asset store and the Codex credential gate first, and threw all of it away
at the refusal. Measured 2026-10-28 on the petri factory: about 14 minutes per
refused attempt.

The refusal is correct and designed; only its position was the waste. These cases
bind the new position without changing the decision:

- A dispatch whose assessment empties an admission-required node journals the
  headroom assessment and then `acp-preflight-refusal`, and NONE of the expensive
  rows run -- including the judgement's model call.
- A dispatch whose assessment keeps a candidate for every node journals nothing
  from the screen and reaches the same rows, in the same order, as before.
- An idle pass (an empty selection) takes no reading at all.

The expensive rows are recorded as an ordered EVENT LIST rather than as journal
stages, because several of them journal nothing on a pass; a missing stage would
read as "did not run" for a row that ran and stayed silent.
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import _dispatcher_admission as admission
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_gate as headroom_gate,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_records import (
    SESSION_HEADROOM_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    ACP_PREFLIGHT_REFUSAL_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_deadline import (
    CredentialLifetimeRequirement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_projection import (
    CODEX_FRESHNESS_MARGIN_SECONDS,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_NOW = "2026-10-28T15:31:00Z"
_TOKEN = "projected-token"
_WALL_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_pre_dispatch_wall"
_EXIT_FAILURE = 1

_REQUIREMENT = CredentialLifetimeRequirement(
    execution_allowance_seconds=18_000 - CODEX_FRESHNESS_MARGIN_SECONDS,
    credential_use_window_seconds=180_000,
    credential_queue_allowance_seconds=86_400,
    margin_seconds=CODEX_FRESHNESS_MARGIN_SECONDS,
    detail="test-resolved requirement",
)

_EXPENSIVE_ROWS = (
    "app-reach",
    "fabro-currency",
    "criteria",
    "dod-judgement",
    "definition-of-done-workflow",
    "proof-assets",
    "proof-credentials",
    "codex-credential-gate",
)


def _work_item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="bug",
        status="ready",
        title="Run the session-headroom admission check first",
        description="Move the headroom screen ahead of the expensive pre-dispatch rows.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-28T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _repo(*, tmp_path: Path) -> Path:
    """A repository declaring no ACP configuration: one built-in Claude candidate per node."""
    repo = tmp_path / "governed"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text("{}\n", encoding="utf-8")
    return repo


def _args(*, repo: Path) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(repo),
        journal=str(repo / "journal.jsonl"),
        item="bd-ib-tsrkqf",
        as_json=False,
        skip_ledger_check=True,
        workflow_name=None,
    )


def _stub_rows(*, monkeypatch: pytest.MonkeyPatch, wall: ModuleType) -> list[str]:
    """Replace every expensive row with a recorder, and return the ordered event list."""
    events: list[str] = []
    routing = importlib.import_module(f"{wall.__package__}._dispatcher_codex_routing")
    decision = routing.CodexRouting(routes_codex=False, detail="no codex routing")

    def recorder(name: str) -> Any:
        def record(**_kwargs: Any) -> None:
            events.append(name)

        return record

    monkeypatch.setattr(wall, "codex_routing_for_dispatch", lambda **_kwargs: decision)
    monkeypatch.setattr(wall, "implementation_pr_override_refusal", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "app_reach_refusal", recorder("app-reach"))
    monkeypatch.setattr(wall, "fabro_currency_refusal", recorder("fabro-currency"))
    monkeypatch.setattr(wall, "pre_dispatch_criteria_refusal", recorder("criteria"))
    monkeypatch.setattr(wall, "dod_judgement_refusal", recorder("dod-judgement"))
    monkeypatch.setattr(
        wall, "definition_of_done_workflow_refusal", recorder("definition-of-done-workflow")
    )
    monkeypatch.setattr(wall, "proof_assets_refusal_for_items", recorder("proof-assets"))
    monkeypatch.setattr(wall, "proof_credentials_refusal_for_items", recorder("proof-credentials"))
    monkeypatch.setattr(wall, "credential_wrapper_text", lambda **_kwargs: "")
    monkeypatch.setattr(wall, "selection_credential_requirement", lambda **_kwargs: _REQUIREMENT)
    monkeypatch.setattr(
        wall, "codex_credential_refusal_for_items", recorder("codex-credential-gate")
    )
    return events


def _install_headroom(
    *, monkeypatch: pytest.MonkeyPatch, utilization: int, reads: list[str | None]
) -> None:
    """Route the admission policy's provider read to a counted stand-in."""
    reading = headroom.session_headroom_reading(
        credential_identity="cred-screen", observed_at=_NOW, utilization=utilization
    )

    def counting_read(*, token: str | None, observed_at: str) -> headroom.SessionHeadroomReading:
        _ = observed_at
        reads.append(token)
        return reading

    def policy(**kwargs: Any) -> headroom.SessionHeadroomPolicy:
        return headroom_gate.session_headroom_policy(**{**kwargs, "read": counting_read})

    monkeypatch.setattr(admission, "session_headroom_policy", policy)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _TOKEN)


def _stages(*, journal_path: Path) -> list[str]:
    if not journal_path.exists():
        return []
    return [
        json.loads(line)["stage"]
        for line in journal_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_a_dispatch_the_headroom_assessment_refuses_runs_none_of_the_expensive_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal is journaled first, and nothing it would have thrown away is spent."""
    wall = importlib.import_module(_WALL_MODULE)
    events = _stub_rows(monkeypatch=monkeypatch, wall=wall)
    reads: list[str | None] = []
    _install_headroom(monkeypatch=monkeypatch, utilization=95, reads=reads)
    repo = _repo(tmp_path=tmp_path)
    journal_path = tmp_path / "journal.jsonl"

    exit_code = wall.pre_dispatch_wall_exit(
        args=_args(repo=repo),
        repo=repo,
        items=[_work_item(item_id="bd-ib-tsrkqf")],
        journal=JournalFile(path=journal_path),
    )

    assert exit_code == _EXIT_FAILURE
    assert reads == [_TOKEN]
    assert _stages(journal_path=journal_path) == [
        SESSION_HEADROOM_STAGE,
        ACP_PREFLIGHT_REFUSAL_STAGE,
    ]
    # The Definition-of-Done judgement is the row that spends a model call, and
    # it is named here beside the rest so a build that ran only the cheap rows
    # first would still fail this case.
    assert events == []


def test_a_dispatch_the_headroom_assessment_admits_runs_every_row_in_its_old_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CONTROL: a passing screen adds no row, and reorders none of the others."""
    wall = importlib.import_module(_WALL_MODULE)
    events = _stub_rows(monkeypatch=monkeypatch, wall=wall)
    reads: list[str | None] = []
    _install_headroom(monkeypatch=monkeypatch, utilization=0, reads=reads)
    repo = _repo(tmp_path=tmp_path)
    journal_path = tmp_path / "journal.jsonl"

    exit_code = wall.pre_dispatch_wall_exit(
        args=_args(repo=repo),
        repo=repo,
        items=[_work_item(item_id="bd-ib-tsrkqf")],
        journal=JournalFile(path=journal_path),
    )

    assert exit_code is None
    assert events == list(_EXPENSIVE_ROWS)
    # The screen journals only when it refuses, so the admission valve's own
    # assessment stays the one record of a dispatch that proceeds.
    assert _stages(journal_path=journal_path) == []


def test_an_idle_pass_takes_no_headroom_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty selection has nothing to refuse, so it pays for no provider request."""
    wall = importlib.import_module(_WALL_MODULE)
    _ = _stub_rows(monkeypatch=monkeypatch, wall=wall)
    reads: list[str | None] = []
    _install_headroom(monkeypatch=monkeypatch, utilization=95, reads=reads)
    repo = _repo(tmp_path=tmp_path)

    exit_code = wall.pre_dispatch_wall_exit(
        args=_args(repo=repo),
        repo=repo,
        items=[],
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
    )

    assert exit_code is None
    assert reads == []
