"""The merge wait's ending for an armed pull request the default branch overtook.

Scenario 184 of `SPECIFICATION/scenarios.md`, sub-scenario "An armed pull
request overtaken by a conflicting commit rests at needs-human with a named
cause", and the v145 "Armed pull request overtaken by the default branch"
clause of `contracts.md`.

THE CONSTANTS ARE SPELLED AS LITERALS AND BOUND TO THE EXPORTED NAMES INSIDE
EACH TEST BODY, which is the pattern the plan-epoch and currency modules
established here: this Red predates the module that declares them, so a
top-level import would make the Red a COLLECTION error that proves only
unimportability. The literal is what the clause ratifies; the `getattr`
assertion beside it is what stops the literal and the exported name drifting
apart.

EVERY CASE HAS A CONTROL THAT COULD RETURN THE OTHER ANSWER. A wait that ended
blocked on EVERY poll would satisfy the four positive cases on its own, so the
three negative cases below are what make them evidence: one conflicting poll,
an UNARMED conflicting pull request, and an exhausted budget with no conflict
at all must each keep the wait's existing behaviour. The unarmed control is the
load-bearing one — the clause scopes this ending to a pull request a run ARMED,
and a reading that dropped that term would end a perfectly ordinary conflicting
pull request at needs-human.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_blocked import (
    escalate_needs_human_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    dispatch_exit_code,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
    PollPolicy,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_merge import await_merge
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_DECLARED_CONFIG = '{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}'

# The clause's own name for this ending, and the marker line its ledger comment
# opens with. Literals here; bound to the exported names in the tests below.
_CAUSE = "base-advanced-after-arming"

# GitHub's `mergeStateStatus` for a pull request the forge reports as
# conflicting with its base. It is the reading the clause means by "in conflict
# with the default branch"; `BEHIND` is the refreshable reading the wait
# already repairs with `update-branch`, and is deliberately NOT this ending.
_CONFLICTING = "DIRTY"

_ITEM_ID = "bd-ib-overtaken"


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
        fabro_factory_name="hp",
    )


@dataclass(kw_only=True)
class _Runner:
    """A runner whose LAST queued result repeats once the queue runs dry.

    Deliberately not the pop-from-list runner the sibling merge tests use. The
    cases below hand the wait a poll budget far larger than the number of polls
    the ending may take, and a runner that raised `IndexError` on exhaustion
    would turn "the wait kept polling" into a collection-time error rather than
    the assertion failure that reports it.
    """

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
        _ = (cwd, timeout_seconds, env)
        assert timeout_seconds > 0
        self.calls.append(argv)
        if len(self.queue) > 1:
            return self.queue.pop(0)
        return self.queue[0]


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _ok(stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _pr_json(
    *,
    state: str = "OPEN",
    armed: bool = True,
    merge_state: str = _CONFLICTING,
    head: str | None = "head1111",
    base: str | None = "base2222",
) -> str:
    return json.dumps(
        {
            "number": 7,
            "state": state,
            "autoMergeRequest": {"enabledAt": "now"} if armed else None,
            "mergeStateStatus": merge_state,
            "mergeCommit": None,
            "statusCheckRollup": [],
            "headRefOid": head,
            "baseRefOid": base,
        }
    )


def _await(
    *,
    repo: Path,
    runner: _Runner,
    journal: _Journal | None = None,
    attempts: int = 8,
) -> PrViewOrOutcome:
    return await_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=repo),
        runner=runner,
        journal=journal if journal is not None else _Journal(),
        sleep=lambda _: None,
        poll=PollPolicy(attempts=attempts, interval_seconds=0.0),
    )


# `await_merge` answers three ways; the alias keeps the helper's annotation
# honest without importing a union spelling the engine does not export.
PrViewOrOutcome = object


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
        title="An armed pull request the default branch overtook",
        description="Its auto-merge request outlived the base it was armed for.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-15T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        blocked_reason=None,
    )


def test_two_consecutive_conflicting_polls_end_blocked_at_merge_poll_with_the_named_cause(
    tmp_path: Path,
) -> None:
    runner = _Runner(queue=[_ok(stdout=_pr_json())])

    outcome = _await(repo=tmp_path, runner=runner)

    assert isinstance(outcome, DispatchOutcome)
    assert (outcome.status, outcome.stage) == ("blocked", "merge-poll")
    assert _CAUSE in outcome.detail
    from livespec_orchestrator_beads_fabro.commands import _dispatcher_base_advance as module

    assert module.BASE_ADVANCED_AFTER_ARMING == _CAUSE


def test_the_ending_stops_before_the_poll_budget(tmp_path: Path) -> None:
    """Two polls decide it, so the wait must not spend the other six.

    The count is read off the SEAM rather than off the outcome, because an
    ending that polled the whole budget and then reported the same blocked
    outcome is indistinguishable from this one at every other assertion — and
    it is the one the clause forbids ("the wait MUST stop before the poll
    budget").
    """
    runner = _Runner(queue=[_ok(stdout=_pr_json())])

    outcome = _await(repo=tmp_path, runner=runner, attempts=8)

    assert isinstance(outcome, DispatchOutcome)
    assert [argv[:3] for argv in runner.calls] == [["gh", "pr", "view"]] * 2


def test_the_ending_reports_exit_code_four(tmp_path: Path) -> None:
    runner = _Runner(queue=[_ok(stdout=_pr_json())])

    outcome = _await(repo=tmp_path, runner=runner)

    assert isinstance(outcome, DispatchOutcome)
    assert dispatch_exit_code(outcomes=[outcome]) == 4


def test_the_item_rests_at_blocked_needs_human(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ending rests the item through the EXISTING needs-human transition.

    The clause requires the same transition and the same `needs-human-blocked`
    journal row a `needs_human` terminal produces, so this asserts the row's
    stage name as well as the ledger state: a bespoke transition that happened
    to leave the same two fields would satisfy the status assertion alone.
    """
    monkeypatch.chdir(tmp_path)
    _write_config(project_root=tmp_path)
    append_work_item(path=_config(), item=_active_item())
    runner = _Runner(queue=[_ok(stdout=_pr_json())])
    journal = _Journal()

    outcome = _await(repo=tmp_path, runner=runner)

    assert isinstance(outcome, DispatchOutcome)
    escalate_needs_human_block(repo=tmp_path, item=_active_item(), outcome=outcome, journal=journal)
    rested = next(item for item in read_work_items(path=_config()) if item.id == _ITEM_ID)
    assert (rested.status, rested.blocked_reason) == ("blocked", "needs-human")
    assert [
        record for record in journal.records if record.get("stage") == "needs-human-blocked"
    ] != []


def test_a_single_conflicting_poll_does_not_end_the_wait(tmp_path: Path) -> None:
    """One reading is not two. The clause says CONSECUTIVE, so a conflict that
    clears on the next poll must leave the wait running and reach the merge."""
    runner = _Runner(
        queue=[
            _ok(stdout=_pr_json()),
            _ok(stdout=_pr_json(state="MERGED", merge_state="CLEAN")),
        ]
    )

    outcome = _await(repo=tmp_path, runner=runner)

    assert not isinstance(outcome, DispatchOutcome)


def test_an_unarmed_conflicting_pull_request_keeps_the_existing_outcome(tmp_path: Path) -> None:
    """The control for the clause's "After a run arms auto-merge" scope.

    An unarmed conflicting pull request is an ordinary one nobody asked the
    forge to merge, so the wait keeps its existing exhausted-budget answer and
    this ending never fires.
    """
    runner = _Runner(queue=[_ok(stdout=_pr_json(armed=False))])

    outcome = _await(repo=tmp_path, runner=runner, attempts=3)

    assert outcome is None


def test_an_exhausted_budget_with_no_conflict_keeps_its_existing_outcome(tmp_path: Path) -> None:
    """ "An exhausted poll budget on a pull request the forge does not report as
    conflicting keeps its existing outcome" — the clause's own last sentence."""
    runner = _Runner(queue=[_ok(stdout=_pr_json(merge_state="BLOCKED"))])

    outcome = _await(repo=tmp_path, runner=runner, attempts=3)

    assert outcome is None
