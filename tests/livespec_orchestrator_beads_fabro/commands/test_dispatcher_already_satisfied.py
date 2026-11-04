"""A `red` turn that declares the work already satisfied ends the run as already satisfied.

The sandbox's `already_satisfied` node prints one `LIVESPEC_ALREADY_SATISFIED:` line
naming the dispatch base when `red` declared the Definition of Done already holds and
the tree is unchanged. These cases bind what the Dispatcher does with it: the run ends
with its own outcome instead of reaching the pull-request lookup and the generic
dead-implementer truncation, the factory claim is released, and the item rests in
`acceptance` with the route by which its Proof of Done can still be obtained.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro import store
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_lifecycle_writes as lifecycle_writes,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_selection
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_BASE = "d" * 40
_LINE = (
    f"LIVESPEC_ALREADY_SATISFIED: base={_BASE} red declared the work already satisfied "
    "on the unchanged dispatch base"
)
_SCRIPT_SOURCE_LINE = (
    'LIVESPEC_ALREADY_SATISFIED: base=$(git rev-parse "origin/master") red declared the work'
)
_TENANT_CONFIG = """{
  "livespec-orchestrator-beads-fabro": {
    "connection": {
      "tenant": "livespec-impl-beads",
      "prefix": "bd",
      "server_user": "livespec-impl-beads",
      "database": "livespec-impl-beads",
      "bd_path": "bd",
      "fake": true
    }
  }
}
"""


@dataclass(kw_only=True)
class _FakeRunner:
    queue: list[CommandResult]
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        assert timeout_seconds > 0
        _ = (cwd, env, stdin)
        self.calls.append(argv)
        return self.queue.pop(0)


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _ok(stdout: str = "", stderr: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr=stderr)


def _pr_json(*, state: str, sha: str | None) -> str:
    return json.dumps(
        {
            "number": 73,
            "state": state,
            "autoMergeRequest": {"enabledAt": "now"},
            "mergeStateStatus": "CLEAN",
            "mergeCommit": {"oid": sha} if sha is not None else None,
            "statusCheckRollup": [],
        }
    )


def _dispatch(*, repo: Path, fabro_stderr: str) -> tuple[DispatchOutcome, _FakeRunner]:
    _ = (repo / ".livespec.jsonc").write_text(_TENANT_CONFIG, encoding="utf-8")
    runner = _FakeRunner(
        queue=[
            _ok(stderr=fabro_stderr),
            _ok(stdout=_pr_json(state="OPEN", sha=None)),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe01")),
            _ok(stdout=json.dumps([{"number": 73}])),
            _ok(),
            _ok(stdout="master"),
            _ok(stdout="master"),
            *[_ok() for _ in range(8)],
        ]
    )
    plan = build_plan(
        repo=repo,
        work_item_id="bd-ib-1",
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        config_text='{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}',
        default_branch="master",
    )
    outcome = run_dispatch(
        plan=plan,
        runner=runner,
        journal=_Journal(),
        sleep=lambda _seconds: None,
        poll=PollPolicy(attempts=3, interval_seconds=0.5),
    )
    return outcome, runner


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-1",
        type="task",
        status="active",
        title="A dispatched task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-11-03T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


@dataclass(kw_only=True)
class _Ledger:
    statuses: list[tuple[str, str, bool]] = field(default_factory=list)
    comments: list[tuple[str, str]] = field(default_factory=list)
    reconciled: list[tuple[str, str]] = field(default_factory=list)
    fail_status: bool = False
    fail_comment: bool = False


def _stub_ledger(*, monkeypatch: pytest.MonkeyPatch, ledger: _Ledger) -> None:
    def _status(
        *, path: StoreConfig, item_id: str, status: str, clear_assignee: bool = False, **_: object
    ) -> None:
        _ = path
        if ledger.fail_status:
            raise BeadsCommandError(command="bd update", exit_code=1, stderr="refused")
        ledger.statuses.append((item_id, status, clear_assignee))

    def _comment(*, path: StoreConfig, work_item_id: str, body: str) -> None:
        _ = path
        if ledger.fail_comment:
            raise BeadsCommandError(command="bd comment", exit_code=1, stderr="refused")
        ledger.comments.append((work_item_id, body))

    def _reconcile(*, path: StoreConfig, item_id: str, status: str) -> None:
        _ = path
        ledger.reconciled.append((item_id, status))

    monkeypatch.setattr(store, "update_work_item_status", _status)
    monkeypatch.setattr(store, "append_work_item_comment", _comment)
    monkeypatch.setattr(lifecycle_writes, "reconcile_after_lifecycle_write", _reconcile)
    for name in (
        "preserve_terminated_run_work",
        "escalate_needs_human_block",
        "dispose_terminal_routing",
        "emit_calibration",
    ):
        monkeypatch.setattr(_dispatcher_loop_selection, name, lambda **_: None)


def _dispositions(*, tmp_path: Path, outcome: DispatchOutcome) -> list[dict[str, object]]:
    _revised, records = _revised_and_dispositions(tmp_path=tmp_path, outcome=outcome)
    return records


def _revised_and_dispositions(
    *, tmp_path: Path, outcome: DispatchOutcome
) -> tuple[DispatchOutcome, list[dict[str, object]]]:
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    revised = _dispatcher_loop_selection.post_run_dispositions(
        args=argparse.Namespace(close_on_merge=True),
        repo=tmp_path,
        item=_item(),
        outcome=outcome,
        journal=journal,
        wall_clock_seconds=1.0,
        dispatch_context_size=1,
        token_supplier=lambda: "token",
    )
    text = journal.path.read_text(encoding="utf-8")
    return revised, [json.loads(line) for line in text.splitlines()]


def test_a_declared_already_satisfied_run_ends_without_reaching_the_pull_request_lookup(
    tmp_path: Path,
) -> None:
    outcome, runner = _dispatch(repo=tmp_path, fabro_stderr=_LINE)

    assert outcome.status == "green"
    assert outcome.stage == "already-satisfied"
    assert outcome.pr_number is None
    assert "bd-ib-1" in outcome.detail
    assert _BASE in outcome.detail
    assert len(runner.calls) == 1


def test_the_script_source_line_without_a_dispatch_base_is_not_the_ending(
    tmp_path: Path,
) -> None:
    outcome, _runner = _dispatch(repo=tmp_path, fabro_stderr=_SCRIPT_SOURCE_LINE)

    assert outcome.stage != "already-satisfied"


def test_an_ordinary_run_is_not_the_ending(tmp_path: Path) -> None:
    outcome, _runner = _dispatch(repo=tmp_path, fabro_stderr="")

    assert outcome.stage != "already-satisfied"


def test_the_ending_releases_the_claim_rests_the_item_in_acceptance_and_names_the_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = _Ledger()
    _stub_ledger(monkeypatch=monkeypatch, ledger=ledger)
    outcome, _runner = _dispatch(repo=tmp_path, fabro_stderr=_LINE)

    records = _dispositions(tmp_path=tmp_path, outcome=outcome)

    assert ledger.statuses == [("bd-ib-1", "acceptance", True)]
    assert ledger.reconciled == [("bd-ib-1", "acceptance")]
    stages = [str(record["stage"]) for record in records]
    assert stages.index("already-satisfied") < stages.index("outcome")
    assert "ledger-complete" not in stages
    assert "dead-implementer-truncation" not in stages
    satisfied = next(record for record in records if record["stage"] == "already-satisfied")
    assert satisfied["work_item_id"] == "bd-ib-1"
    assert satisfied["dispatch_base"] == _BASE
    assert [item_id for item_id, _body in ledger.comments] == ["bd-ib-1"]
    body = ledger.comments[0][1]
    assert _BASE in body
    assert "reconcile-merged" in body
    assert "proof-only run against the dispatch base" in body


def test_a_refused_rest_is_journaled_and_does_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = _Ledger(fail_status=True)
    _stub_ledger(monkeypatch=monkeypatch, ledger=ledger)
    outcome, _runner = _dispatch(repo=tmp_path, fabro_stderr=_LINE)

    records = _dispositions(tmp_path=tmp_path, outcome=outcome)

    stages = [str(record["stage"]) for record in records]
    assert "already-satisfied-rest-failed" in stages
    assert ledger.comments == []


def test_a_refused_rest_is_reported_as_a_failed_outcome_not_the_green_ending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = _Ledger(fail_status=True)
    _stub_ledger(monkeypatch=monkeypatch, ledger=ledger)
    outcome, _runner = _dispatch(repo=tmp_path, fabro_stderr=_LINE)

    revised, records = _revised_and_dispositions(tmp_path=tmp_path, outcome=outcome)

    assert revised.status == "failed"
    assert revised.stage == "already-satisfied-rest-failed"
    assert "bd-ib-1" in revised.detail
    assert "still active and claimed" in revised.detail
    journaled = next(record for record in records if record["stage"] == "outcome")
    assert journaled["outcome"]["status"] == "failed"  # type: ignore[index]


def test_a_rested_item_keeps_the_green_ending_as_its_reported_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = _Ledger()
    _stub_ledger(monkeypatch=monkeypatch, ledger=ledger)
    outcome, _runner = _dispatch(repo=tmp_path, fabro_stderr=_LINE)

    revised, _records = _revised_and_dispositions(tmp_path=tmp_path, outcome=outcome)

    assert revised.status == "green"
    assert revised.stage == "already-satisfied"


def test_a_refused_comment_is_journaled_and_the_item_still_rests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = _Ledger(fail_comment=True)
    _stub_ledger(monkeypatch=monkeypatch, ledger=ledger)
    outcome, _runner = _dispatch(repo=tmp_path, fabro_stderr=_LINE)

    records = _dispositions(tmp_path=tmp_path, outcome=outcome)

    stages = [str(record["stage"]) for record in records]
    assert ledger.statuses == [("bd-ib-1", "acceptance", True)]
    assert "already-satisfied-comment-failed" in stages
