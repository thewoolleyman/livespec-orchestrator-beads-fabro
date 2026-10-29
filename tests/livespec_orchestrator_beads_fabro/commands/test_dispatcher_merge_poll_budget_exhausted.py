"""An exhausted merge-poll budget on an open pull request rests the item for resume.

Scenario 220 of `SPECIFICATION/scenarios.md`, and the final sentences of the
"Armed pull request overtaken by the default branch" paragraph of
`contracts.md`: when the poll budget is exhausted the Dispatcher reads the pull
request once more, proceeds on MERGED, and otherwise rests the item at
`blocked / needs-human` with the cause `merge-poll-budget-exhausted`.

EVERY CASE HAS A CONTROL THAT COULD RETURN THE OTHER ANSWER. A disposition that
rested the item on every exhausted budget would satisfy the positive case on its
own, so the MERGED, conflicting, closed and unreadable final reads each keep the
outcome the clause leaves them.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands import _dispatcher_engine_merge as merge_module
from livespec_orchestrator_beads_fabro.commands._dispatcher_blocked import (
    escalate_needs_human_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    dispatch_exit_code,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_merge import (
    outcome_after_await,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_DECLARED_CONFIG = '{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}'
_ITEM_ID = "bd-ib-exhausted"
_RUN_ID = "01M62WN80GEFPBFVFT5XHZN27P"
_CAUSE = "merge-poll-budget-exhausted"
_MARKER = "livespec-merge-poll-budget-exhausted"


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id=_ITEM_ID,
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        config_text=_DECLARED_CONFIG,
        default_branch="master",
        fabro_factory_name="petri",
    )


@dataclass(kw_only=True)
class _Runner:
    queue: list[CommandResult]
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (cwd, env)
        assert timeout_seconds > 0
        self.calls.append(argv)
        return self.queue.pop(0)


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _pr_json(*, state: str = "OPEN", merge_state: str = "BLOCKED") -> str:
    return json.dumps(
        {
            "number": 3913,
            "state": state,
            "autoMergeRequest": {"enabledAt": "now"},
            "mergeStateStatus": merge_state,
            "mergeCommit": {"oid": "cafe05"} if state == "MERGED" else None,
            "headRefOid": "head1111",
            "baseRefOid": "base2222",
        }
    )


def _after_exhaustion(*, repo: Path, runner: _Runner) -> DispatchOutcome:
    return outcome_after_await(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=repo),
        runner=runner,
        journal=_Journal(),
        merged=None,
        pr_number=3913,
        run_id=_RUN_ID,
    )


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _write_config(*, project_root: Path) -> None:
    _ = (project_root / ".livespec.jsonc").write_text(
        json.dumps(
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
        ),
        encoding="utf-8",
    )


def _active_item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="active",
        title="A succeeded run whose merge wait ran out of budget",
        description="Its pull request stayed open past the poll budget.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-29T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        blocked_reason=None,
    )


def test_an_open_non_conflicting_pull_request_at_expiry_ends_blocked_with_the_named_cause(
    tmp_path: Path,
) -> None:
    runner = _Runner(queue=[CommandResult(exit_code=0, stdout=_pr_json(), stderr="")])

    outcome = _after_exhaustion(repo=tmp_path, runner=runner)

    assert (outcome.status, outcome.stage) == ("blocked", "merge-poll")
    assert _CAUSE in outcome.detail
    assert outcome.pr_number == 3913
    assert outcome.fabro_run_id == _RUN_ID
    assert [argv[:3] for argv in runner.calls] == [["gh", "pr", "view"]]
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance"
    )
    assert module.MERGE_POLL_BUDGET_EXHAUSTED == _CAUSE  # type: ignore[attr-defined]


def test_the_outcome_detail_names_resolve_blocked_then_resume(tmp_path: Path) -> None:
    runner = _Runner(queue=[CommandResult(exit_code=0, stdout=_pr_json(), stderr="")])

    outcome = _after_exhaustion(repo=tmp_path, runner=runner)

    chain = f"`resolve-blocked:{_ITEM_ID}:ready`"
    assert chain in outcome.detail
    assert f"`resume --item {_ITEM_ID}`" in outcome.detail
    assert outcome.detail.index(chain) < outcome.detail.index("resume --item")


def test_the_ending_reports_exit_code_four(tmp_path: Path) -> None:
    runner = _Runner(queue=[CommandResult(exit_code=0, stdout=_pr_json(), stderr="")])

    outcome = _after_exhaustion(repo=tmp_path, runner=runner)

    assert dispatch_exit_code(outcomes=[outcome]) == 4


def test_the_item_rests_at_blocked_needs_human_and_the_cause_is_recorded_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(project_root=tmp_path)
    append_work_item(path=_config(), item=_active_item())
    runner = _Runner(queue=[CommandResult(exit_code=0, stdout=_pr_json(), stderr="")])
    journal = _Journal()
    outcome = _after_exhaustion(repo=tmp_path, runner=runner)
    record_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance_record"
    )

    record_module.record_base_advanced_after_arming(  # type: ignore[attr-defined]
        repo=tmp_path, item=_active_item(), outcome=outcome, journal=journal
    )
    escalate_needs_human_block(repo=tmp_path, item=_active_item(), outcome=outcome, journal=journal)

    rested = next(item for item in read_work_items(path=_config()) if item.id == _ITEM_ID)
    assert (rested.status, rested.blocked_reason) == ("blocked", "needs-human")
    comments = read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)
    marked = [c for c in comments if c.text.splitlines()[0] == _MARKER]
    assert len(marked) == 1
    assert _RUN_ID in marked[0].text
    assert "petri" in marked[0].text
    assert "3913" in marked[0].text
    assert [r for r in journal.records if r.get("stage") == "needs-human-blocked"] != []


def test_a_pull_request_merged_on_the_final_read_proceeds_as_a_merge_within_the_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = DispatchOutcome(
        work_item_id=_ITEM_ID,
        status="green",
        stage="done",
        pr_number=3913,
        merge_sha="cafe05",
        detail="merged",
    )
    seen: list[str] = []

    def _post_merge(**kwargs: object) -> DispatchOutcome:
        merged = kwargs["merged"]
        seen.append(getattr(merged, "state", "?"))
        return sentinel

    monkeypatch.setattr(merge_module, "post_merge", _post_merge)
    monkeypatch.setattr(merge_module, "pr_view_for_merge_sha", lambda **kwargs: kwargs["merged"])
    runner = _Runner(queue=[CommandResult(exit_code=0, stdout=_pr_json(state="MERGED"), stderr="")])

    outcome = _after_exhaustion(repo=tmp_path, runner=runner)

    assert outcome is sentinel
    assert seen == ["MERGED"]


@pytest.mark.parametrize(
    "final_read",
    [
        CommandResult(exit_code=0, stdout=_pr_json(merge_state="DIRTY"), stderr=""),
        CommandResult(exit_code=0, stdout=_pr_json(state="CLOSED"), stderr=""),
        CommandResult(exit_code=1, stdout="", stderr="gh failed"),
        CommandResult(exit_code=0, stdout="not json", stderr=""),
    ],
    ids=["conflicting", "closed", "unreadable", "garbled"],
)
def test_any_other_final_read_keeps_the_existing_failed_outcome(
    tmp_path: Path, final_read: CommandResult
) -> None:
    runner = _Runner(queue=[final_read])

    outcome = _after_exhaustion(repo=tmp_path, runner=runner)

    assert (outcome.status, outcome.stage) == ("failed", "merge-poll")
    assert outcome.detail == "PR did not reach MERGED within the poll budget"
    assert outcome.pr_number == 3913
    assert outcome.fabro_run_id == _RUN_ID
