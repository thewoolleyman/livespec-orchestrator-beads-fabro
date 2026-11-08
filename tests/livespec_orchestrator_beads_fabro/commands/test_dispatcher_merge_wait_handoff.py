"""A merge wait whose budget ends on an armed, passing pull request is handed off.

Binds the dispatching half of `SPECIFICATION/scenarios.md` Scenario 220
("An armed pull request with passing or running checks is handed off") and the
"HANDED-OFF merge wait" sentences of the `contracts.md` paragraph "Armed pull
request overtaken by the default branch", for work-item `bd-ib-bacahf`.

EVERY CASE HAS A CONTROL THAT RETURNS THE OTHER ANSWER. A merge wait that handed
off every exhausted budget would satisfy the positive case on its own, so the
unarmed pull request, the terminally failed required check and the unreadable
required-check list each keep the ending the clause gives them: the item rests at
`blocked / needs-human` with the cause `merge-poll-budget-exhausted`, or with the
terminal required-check failure it has always recorded.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from itertools import chain, repeat
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    dispatch_exit_code,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
    FabroRunResult,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_merge import (
    outcome_after_await,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._drive_cli import exit_code_for_status
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_RECORD_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_merge_wait_handoff_record"
_DECLARED_CONFIG = '{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}'
_ITEM_ID = "bd-ib-handoff"
_RUN_ID = "01M6VNKFXRA85Q8WF0JV23204B"
_MARKER = "livespec-merge-wait-handed-off"
_HEAD = "head1111"
_TENANT_CONFIG = json.dumps(
    {
        "livespec-orchestrator-beads-fabro": {
            "connection": {
                "tenant": "livespec-impl-beads",
                "prefix": "bd",
                "server_user": "livespec-impl-beads",
                "database": "livespec-impl-beads",
                "bd_path": "bd",
                "fake": True,
            }
        }
    }
)


@pytest.fixture(autouse=True)
def _fresh_tenant() -> None:
    reset_fake_singleton()


def _plan(*, repo: Path, default_branch: str = "master") -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id=_ITEM_ID,
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        config_text=_DECLARED_CONFIG,
        default_branch=default_branch,
        fabro_factory_name="petri",
    )


def _view(
    *,
    armed: bool = True,
    merge_state: str = "BLOCKED",
    rollup: list[dict[str, object]] | None = None,
) -> str:
    payload: dict[str, object] = {
        "number": 4615,
        "state": "OPEN",
        "autoMergeRequest": {"enabledAt": "now"} if armed else None,
        "mergeStateStatus": merge_state,
        "mergeCommit": None,
        "headRefOid": _HEAD,
        "baseRefOid": "base2222",
    }
    if rollup is not None:
        payload["statusCheckRollup"] = rollup
    return json.dumps(payload)


def _required_answer(*, required: list[str]) -> str:
    names = [{"name": name, "isRequired": True} for name in required]
    names.append({"name": "docs-preview", "isRequired": False})
    return json.dumps(
        {
            "data": {
                "repository": {
                    "pullRequest": {
                        "commits": {
                            "nodes": [
                                {"commit": {"statusCheckRollup": {"contexts": {"nodes": names}}}}
                            ]
                        }
                    }
                }
            }
        }
    )


_RUNNING = [
    {"name": "check-coverage", "status": "IN_PROGRESS", "conclusion": None},
    {"name": "check-lint", "status": "QUEUED", "conclusion": None},
    {"name": "docs-preview", "status": "IN_PROGRESS", "conclusion": None},
    {"name": "check-types", "status": "COMPLETED", "conclusion": "success"},
]


@dataclass(kw_only=True)
class _Forge:
    """A forge answering by argv, so no case depends on the order of its reads."""

    armed: bool = True
    merge_state: str = "BLOCKED"
    rollup: list[dict[str, object]] = field(default_factory=lambda: list(_RUNNING))
    required: list[str] = field(
        default_factory=lambda: ["check-coverage", "check-lint", "check-types"]
    )
    required_readable: bool = True
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
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        if argv[:3] == ["gh", "api", "graphql"]:
            if not self.required_readable:
                return CommandResult(exit_code=1, stdout="", stderr="graphql unavailable")
            return CommandResult(
                exit_code=0, stdout=_required_answer(required=self.required), stderr=""
            )
        if argv[:3] != ["gh", "pr", "view"]:
            return CommandResult(exit_code=0, stdout="", stderr="")
        with_rollup = "statusCheckRollup" in argv[-1]
        return CommandResult(
            exit_code=0,
            stdout=_view(
                armed=self.armed,
                merge_state=self.merge_state,
                rollup=self.rollup if with_rollup else None,
            ),
            stderr="",
        )


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)
    path: Path | None = None

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _Launcher:
    def launch(self, *, plan: DispatchPlan, runner: object, journal: object) -> FabroRunResult:
        _ = (plan, runner, journal)
        return FabroRunResult(
            command=CommandResult(exit_code=0, stdout="", stderr=""), run_id=_RUN_ID
        )


def _after_exhaustion(*, repo: Path, forge: _Forge, journal: _Journal) -> DispatchOutcome:
    return outcome_after_await(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=repo),
        runner=forge,
        journal=journal,
        merged=None,
        pr_number=4615,
        run_id=_RUN_ID,
        waited_seconds=2400,
    )


def _active_item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="active",
        title="A succeeded run whose CI outlasted the merge wait",
        description="Its pull request is armed and its checks are still running.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-11-08T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        blocked_reason=None,
    )


def _store() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


@pytest.mark.parametrize(
    ("repository", "default_branch"),
    [
        ("livespec-orchestrator-beads-fabro", "master"),
        ("livespec-runtime", "main"),
        ("livespec-overseer", "master"),
    ],
)
def test_an_armed_pull_request_with_running_required_checks_is_handed_off(
    tmp_path: Path, repository: str, default_branch: str
) -> None:
    repo = tmp_path / repository
    repo.mkdir()
    journal = _Journal()
    forge = _Forge()

    outcome = outcome_after_await(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=repo, default_branch=default_branch),
        runner=forge,
        journal=journal,
        merged=None,
        pr_number=4615,
        run_id=_RUN_ID,
        waited_seconds=2400,
    )

    assert (outcome.status, outcome.stage) == ("handed-off", "merge-poll")
    assert outcome.pr_number == 4615
    assert outcome.fabro_run_id == _RUN_ID
    assert "merge-wait-handed-off" in outcome.detail
    handed = outcome.merge_wait_handed_off
    assert handed is not None
    assert handed.waited_seconds == 2400
    assert handed.running_checks == ("check-coverage", "check-lint")
    assert handed.pr_head == _HEAD
    assert handed.factory == "petri"
    rows = [r for r in journal.records if r.get("stage") == "merge-wait-handed-off"]
    assert len(rows) == 1
    assert rows[0]["work_item_id"] == _ITEM_ID
    assert rows[0]["run_id"] == _RUN_ID
    assert rows[0]["pr_number"] == 4615
    assert rows[0]["pr_head"] == _HEAD
    assert rows[0]["waited_seconds"] == 2400
    assert rows[0]["running_checks"] == ["check-coverage", "check-lint"]


def test_a_handed_off_wait_with_every_check_passing_names_no_running_check(tmp_path: Path) -> None:
    journal = _Journal()
    forge = _Forge(rollup=[{"name": "check-types", "status": "COMPLETED", "conclusion": "success"}])

    outcome = _after_exhaustion(repo=tmp_path, forge=forge, journal=journal)

    assert outcome.status == "handed-off"
    assert outcome.merge_wait_handed_off is not None
    assert outcome.merge_wait_handed_off.running_checks == ()
    rows = [r for r in journal.records if r.get("stage") == "merge-wait-handed-off"]
    assert [r["running_checks"] for r in rows] == [[]]


def test_a_pull_request_whose_auto_merge_is_no_longer_armed_still_rests_the_item(
    tmp_path: Path,
) -> None:
    journal = _Journal()

    outcome = _after_exhaustion(repo=tmp_path, forge=_Forge(armed=False), journal=journal)

    assert (outcome.status, outcome.stage) == ("blocked", "merge-poll")
    assert "merge-poll-budget-exhausted" in outcome.detail
    assert outcome.merge_wait_handed_off is None
    assert [r for r in journal.records if r.get("stage") == "merge-wait-handed-off"] == []


def test_a_required_check_that_failed_terminally_keeps_its_ordinary_ending(
    tmp_path: Path,
) -> None:
    journal = _Journal()
    forge = _Forge(
        rollup=[
            {"name": "check-coverage", "status": "COMPLETED", "conclusion": "failure"},
            {"name": "check-lint", "status": "IN_PROGRESS", "conclusion": None},
        ]
    )

    outcome = _after_exhaustion(repo=tmp_path, forge=forge, journal=journal)

    assert (outcome.status, outcome.stage) == ("blocked", "merge-poll")
    assert "required check failed terminally: check-coverage" in outcome.detail
    assert outcome.merge_wait_handed_off is None
    assert [r for r in journal.records if r.get("stage") == "merge-wait-handed-off"] == []


def test_a_failed_check_the_forge_does_not_require_does_not_prevent_the_handoff(
    tmp_path: Path,
) -> None:
    forge = _Forge(
        rollup=[
            {"name": "docs-preview", "status": "COMPLETED", "conclusion": "failure"},
            {"name": "check-lint", "status": "IN_PROGRESS", "conclusion": None},
        ]
    )

    outcome = _after_exhaustion(repo=tmp_path, forge=forge, journal=_Journal())

    assert outcome.status == "handed-off"
    assert outcome.merge_wait_handed_off is not None
    assert outcome.merge_wait_handed_off.running_checks == ("check-lint",)


def test_unreadable_required_checks_rest_the_item_rather_than_hand_it_off(
    tmp_path: Path,
) -> None:
    journal = _Journal()

    outcome = _after_exhaustion(
        repo=tmp_path, forge=_Forge(required_readable=False), journal=journal
    )

    assert (outcome.status, outcome.stage) == ("blocked", "merge-poll")
    assert "merge-poll-budget-exhausted" in outcome.detail
    assert [r for r in journal.records if r.get("stage") == "merge-wait-handed-off"] == []


def test_a_conflicting_armed_pull_request_keeps_the_overtaken_arming_ending(
    tmp_path: Path,
) -> None:
    outcome = _after_exhaustion(
        repo=tmp_path, forge=_Forge(merge_state="DIRTY"), journal=_Journal()
    )

    assert outcome.status != "handed-off"
    assert outcome.merge_wait_handed_off is None


def test_the_merge_wait_measures_the_seconds_it_spent_on_the_poll_policys_clock(
    tmp_path: Path,
) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(_TENANT_CONFIG, encoding="utf-8")
    journal = _Journal()
    readings = chain([100.0, 2500.4], repeat(2500.4))

    outcome = run_dispatch(
        plan=_plan(repo=tmp_path),
        runner=_Forge(),
        journal=journal,
        sleep=lambda _: None,
        poll=PollPolicy(attempts=2, interval_seconds=0.0, clock=lambda: next(readings)),
        fabro_launcher=_Launcher(),
    )

    assert outcome.status == "handed-off"
    assert outcome.merge_wait_handed_off is not None
    assert outcome.merge_wait_handed_off.waited_seconds == 2400
    assert outcome.fabro_run_id == _RUN_ID


def test_a_handed_off_dispatch_exits_zero_on_both_operator_surfaces(tmp_path: Path) -> None:
    outcome = _after_exhaustion(repo=tmp_path, forge=_Forge(), journal=_Journal())

    assert dispatch_exit_code(outcomes=[outcome]) == 0
    assert exit_code_for_status(status="handed-off") == 0
    blocked = _after_exhaustion(repo=tmp_path, forge=_Forge(armed=False), journal=_Journal())
    assert dispatch_exit_code(outcomes=[blocked]) == 4


def _record_module() -> Any:
    module_path = _COMMANDS / "_dispatcher_merge_wait_handoff_record.py"
    assert module_path.is_file(), f"{module_path} does not exist yet"
    return importlib.import_module(_RECORD_MODULE)


def test_the_handoff_leaves_one_marked_ledger_comment_and_the_item_stays_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / ".livespec.jsonc").write_text(_TENANT_CONFIG, encoding="utf-8")
    append_work_item(path=_store(), item=_active_item())
    journal = _Journal()
    outcome = _after_exhaustion(repo=tmp_path, forge=_Forge(), journal=journal)

    _record_module().record_merge_wait_handed_off(
        repo=tmp_path, item=_active_item(), outcome=outcome, journal=journal
    )

    comments = read_work_item_comments(path=_store(), work_item_id=_ITEM_ID)
    marked = [c for c in comments if c.text.splitlines()[0] == _MARKER]
    assert len(marked) == 1
    text = marked[0].text
    for fact in (_RUN_ID, "petri", "4615", _HEAD, "2400", "check-coverage", "check-lint"):
        assert fact in text
    assert "docs-preview" not in text
    assert "{{" not in text
    item = next(one for one in read_work_items(path=_store()) if one.id == _ITEM_ID)
    assert (item.status, item.assignee) == ("active", "fabro")
    assert [r for r in journal.records if str(r.get("stage")).endswith("-error")] == []


def test_a_check_name_that_is_not_identifier_shaped_is_left_out_and_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / ".livespec.jsonc").write_text(_TENANT_CONFIG, encoding="utf-8")
    append_work_item(path=_store(), item=_active_item())
    odd = "coverage {{ shard }} one"
    forge = _Forge(
        rollup=[
            {"name": odd, "status": "IN_PROGRESS", "conclusion": None},
            {"name": "check-lint", "status": "IN_PROGRESS", "conclusion": None},
        ],
        required=[odd, "check-lint"],
    )
    journal = _Journal()
    outcome = _after_exhaustion(repo=tmp_path, forge=forge, journal=journal)

    _record_module().record_merge_wait_handed_off(
        repo=tmp_path, item=_active_item(), outcome=outcome, journal=journal
    )

    comments = read_work_item_comments(path=_store(), work_item_id=_ITEM_ID)
    marked = [c for c in comments if c.text.splitlines()[0] == _MARKER]
    assert len(marked) == 1
    assert "{{" not in marked[0].text
    assert "check-lint" in marked[0].text
    assert "1 names were left out" in marked[0].text


def test_a_blocked_outcome_leaves_no_handoff_comment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / ".livespec.jsonc").write_text(_TENANT_CONFIG, encoding="utf-8")
    append_work_item(path=_store(), item=_active_item())
    journal = _Journal()
    outcome = _after_exhaustion(repo=tmp_path, forge=_Forge(armed=False), journal=journal)

    _record_module().record_merge_wait_handed_off(
        repo=tmp_path, item=_active_item(), outcome=outcome, journal=journal
    )

    assert read_work_item_comments(path=_store(), work_item_id=_ITEM_ID) == ()
