"""The host's merge confirmation obeys the CURRENT merge hold, not its launch snapshot.

`DispatchPlan.merge_hold` is a LAUNCH SNAPSHOT, and that is what the two seams the
ratified per-item merge hold names read: the sandbox's pr stage reads it as the
`merge_hold` workflow input, and the host's auto-merge argv reads it off the plan.
Neither is authoritative, and neither can see a hold a maintainer applies DURING the
run -- which is the window the hold exists to open.

Measured 2026-10-05 on pull request 2607 of this repository. Run
01M467KFF0Z07Y0RMGW7NN873V launched with `merge_hold=false`; the operator set the
live hold while it ran; the pr stage obeyed the live hold and ended with
`autoMergeRequest=null` at 16:31:43Z; and the HOST journaled `pr-arm-fallback` at
16:32:00Z, arming the merge the ledger forbade. The hold had to be re-applied by
hand to disarm it.

So every case here holds the plan's snapshot at `false` and puts the hold ONLY in the
tenant, because a case built on `plan.merge_hold=True` cannot fail the way the
incident did: the defect is the DISAGREEMENT between the snapshot and the ledger, and
a test that makes the two agree has removed its own subject. Each case is driven at
the `run_dispatch` boundary over a real fake tenant rather than through an injected
hold value, so the ledger read is the one the host actually performs.

Two of the claims are ABSENCES -- no `gh pr merge` reaches the forge -- and an absence
is asserted over the WHOLE call list (every forge call was a read) rather than by
searching it for a flag. The unheld case is their control: it drives the identical
open, unarmed pull request through the identical runner and DOES arm it, which is
what makes the absences mean something.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro._store_merge_hold import update_work_item_merge_hold
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
    FabroRunResult,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-m5vgxh"
_TENANT = "livespec-impl-beads"

# The repository declaration the PLAN resolves its contract from -- a declared
# janitor-core pin plus the probed default branch, which together make the resolved
# merge mode the fleet default `rebase`. It is a separate source from the tenant
# connection file below, which is what the host's hold read resolves.
_DECLARED_CONFIG = '{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}'

# The committed connection block the host's hold read needs. Without it
# `resolve_store_config` raises on the absent `connection.prefix`, which is exactly
# the unreadable-authority case below -- so its ABSENCE is a fixture choice, not an
# oversight.
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

_PR_NUMBER = 7
_VIEW_ARGV_HEAD = ("gh", "pr", "view")
_ARM_ARGV = [
    "gh",
    "pr",
    "merge",
    str(_PR_NUMBER),
    "--rebase",
    "--auto",
    "--delete-branch",
]
_DISARM_ARGV = ["gh", "pr", "merge", str(_PR_NUMBER), "--disable-auto"]
_MERGE_SHA = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"


def _store() -> StoreConfig:
    return StoreConfig(
        tenant=_TENANT,
        prefix="bd",
        server_user=_TENANT,
        database=_TENANT,
        bd_path="bd",
        fake=True,
    )


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="Host fallback arming must honor a merge hold applied after dispatch",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-05T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _tenant(*, repo: Path, held: bool) -> None:
    """Provision the repo's connection block and one item, held or not."""
    _ = (repo / ".livespec.jsonc").write_text(_TENANT_CONFIG, encoding="utf-8")
    config = _store()
    append_work_item(path=config, item=_item())
    if held:
        update_work_item_merge_hold(path=config, item_id=_ITEM_ID, value=True)


def _plan(*, repo: Path) -> DispatchPlan:
    """A plan whose snapshot says UNHELD -- the stale half of every case here."""
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
        merge_hold=False,
    )


def _view(*, armed: bool) -> CommandResult:
    return CommandResult(
        exit_code=0,
        stdout=json.dumps(
            {
                "number": _PR_NUMBER,
                "state": "OPEN",
                "autoMergeRequest": {"enabledAt": "2026-10-05T16:31:59Z"} if armed else None,
                "mergeStateStatus": "CLEAN",
                "mergeCommit": None,
                "statusCheckRollup": [],
            }
        ),
        stderr="",
    )


def _merged_view() -> CommandResult:
    return CommandResult(
        exit_code=0,
        stdout=json.dumps(
            {
                "number": _PR_NUMBER,
                "state": "MERGED",
                "autoMergeRequest": None,
                "mergeStateStatus": "CLEAN",
                "mergeCommit": {"oid": _MERGE_SHA},
                "statusCheckRollup": [],
            }
        ),
        stderr="",
    )


@dataclass(kw_only=True)
class _Runner:
    """Records every argv; answers an exhausted queue with an open, unarmed view.

    The default answer is load-bearing. These cases assert what the host did and did
    NOT send to the forge, and a queue that ran dry would raise `IndexError` -- making
    the fixture the verdict instead of the engine. `default` overrides it for the one
    case whose forge has MERGED the pull request: there every later read must report
    the merge, and a fixed open answer would make the queue length decide the outcome.
    """

    queue: list[CommandResult] = field(default_factory=list)
    calls: list[list[str]] = field(default_factory=list)
    default: CommandResult | None = None

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
        if self.queue:
            return self.queue.pop(0)
        return _view(armed=False) if self.default is None else self.default


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _Launcher:
    """A `fabro run` that succeeded and reported no run id."""

    def launch(self, *, plan: DispatchPlan, runner: object, journal: object) -> FabroRunResult:
        _ = (plan, runner, journal)
        return FabroRunResult(command=CommandResult(exit_code=0, stdout="", stderr=""))


@dataclass(frozen=True, kw_only=True)
class _Dispatched:
    """One dispatch's terminal outcome beside the waits it performed.

    The waits ride along because "the run never waits" is not readable off an
    outcome: a poll budget spent and then reported green would carry the same
    status and stage as a run that short-circuited.
    """

    outcome: DispatchOutcome
    sleeps: tuple[float, ...]


def _dispatch(*, repo: Path, runner: _Runner, journal: _Journal) -> _Dispatched:
    """One dispatch with a poll budget of TWO, so a run that waits can be seen to."""
    sleeps: list[float] = []
    outcome = run_dispatch(
        plan=_plan(repo=repo),
        runner=runner,
        journal=journal,
        sleep=sleeps.append,
        poll=PollPolicy(attempts=2, interval_seconds=0.0),
        fabro_launcher=_Launcher(),
    )
    return _Dispatched(outcome=outcome, sleeps=tuple(sleeps))


def _forge_verbs(*, runner: _Runner) -> set[tuple[str, ...]]:
    return {tuple(argv[:3]) for argv in runner.calls}


def test_the_host_arms_nothing_when_the_ledger_currently_holds_an_item_dispatched_unheld(
    tmp_path: Path,
) -> None:
    """The reversal measured on pull request 2607, asserted at the host boundary."""
    _tenant(repo=tmp_path, held=True)
    runner = _Runner(queue=[_view(armed=False)])

    _ = _dispatch(repo=tmp_path, runner=runner, journal=_Journal())

    assert _forge_verbs(runner=runner) == {_VIEW_ARGV_HEAD}


def test_the_host_disarms_a_pull_request_it_finds_armed_while_the_item_is_now_held(
    tmp_path: Path,
) -> None:
    """An already-armed pull request under a current hold is a merge nobody chose.

    Leaving it armed would honor the hold's letter -- this host armed nothing -- while
    the merge the hold forbids lands anyway on the next green check run.
    """
    _tenant(repo=tmp_path, held=True)
    runner = _Runner(queue=[_view(armed=True), CommandResult(exit_code=0, stdout="", stderr="")])
    journal = _Journal()

    dispatched = _dispatch(repo=tmp_path, runner=runner, journal=journal)

    assert _DISARM_ARGV in runner.calls
    assert _ARM_ARGV not in runner.calls
    assert "pr-disarm-held" in [record["stage"] for record in journal.records]
    # The exhausted queue answers the authoritative re-read UNARMED, so the disarm
    # took effect and the held terminal is earned. This is the control for the two
    # refusals below, and it is the SAME outcome a pull request that was never armed
    # produces -- which is correct here and is exactly what made the refusals
    # invisible before them.
    assert (dispatched.outcome.status, dispatched.outcome.stage) == ("green", "pr")


def test_a_held_pull_request_still_armed_after_a_failed_disarm_refuses_instead_of_green(
    tmp_path: Path,
) -> None:
    """The forge REFUSED the disarm, so the hold is not enforced and must not be claimed.

    Caught in review of this item's own pull request 2614. The host reported
    `green` at the held boundary with a detail reading "PR #7 is open with no
    auto-merge armed" while the pull request was armed, so the merge the hold
    forbids would land on the next green check run and the dispatch result said the
    opposite. A refusal that is only as strong as a forge write it never checked is
    not a refusal.
    """
    _tenant(repo=tmp_path, held=True)
    runner = _Runner(
        queue=[
            _view(armed=True),
            CommandResult(exit_code=1, stdout="", stderr="GraphQL: Could not resolve to a node"),
            _view(armed=True),
        ]
    )

    dispatched = _dispatch(repo=tmp_path, runner=runner, journal=_Journal())

    assert (dispatched.outcome.status, dispatched.outcome.stage) == (
        "failed",
        "merge-hold-unenforced",
    )
    assert dispatched.outcome.pr_number == _PR_NUMBER
    assert dispatched.outcome.merge_sha is None
    # It must not WAIT either: the pull request is armed and may merge at any moment,
    # so polling for that merge would be waiting for the very thing being refused.
    assert dispatched.sleeps == ()
    assert "no auto-merge armed" not in dispatched.outcome.detail
    assert _ITEM_ID in dispatched.outcome.detail
    assert f"gh pr merge {_PR_NUMBER} --disable-auto" in dispatched.outcome.detail


def test_a_disarm_reporting_success_without_taking_effect_refuses_the_same_way(
    tmp_path: Path,
) -> None:
    """A forge write can report success and not take effect, and that is the worse arm.

    Keyed on the AUTHORITATIVE post-disarm view rather than on the disarm command's
    exit code, because the exit code can lie in both directions -- a non-zero exit
    whose pull request is nonetheless unarmed is the control above -- and the re-read
    cannot. The disarm command's own result stays in the `pr-disarm-held` journal
    row, which is where an operator tells a refused write from an ineffective one.
    """
    _tenant(repo=tmp_path, held=True)
    runner = _Runner(
        queue=[
            _view(armed=True),
            CommandResult(exit_code=0, stdout="", stderr=""),
            _view(armed=True),
        ]
    )

    dispatched = _dispatch(repo=tmp_path, runner=runner, journal=_Journal())

    assert (dispatched.outcome.status, dispatched.outcome.stage) == (
        "failed",
        "merge-hold-unenforced",
    )
    assert dispatched.sleeps == ()


def test_a_pull_request_that_merges_during_the_disarm_takes_the_ordinary_post_merge_path(
    tmp_path: Path,
) -> None:
    """The MERGED race, which the held terminal must keep letting through.

    A pull request that merged between the disarm write and the re-read is past the
    hold entirely: terminating green-with-no-merge there would skip the post-merge
    janitor and the acceptance valve on work that HAS merged. The refusal above must
    not be reached by widening into this arm, so it is asserted beside them rather
    than left to be noticed by its absence.
    """
    _tenant(repo=tmp_path, held=True)
    runner = _Runner(
        queue=[_view(armed=True), CommandResult(exit_code=0, stdout="", stderr="")],
        default=_merged_view(),
    )

    dispatched = _dispatch(repo=tmp_path, runner=runner, journal=_Journal())

    assert dispatched.outcome.stage != "merge-hold-unenforced"
    assert dispatched.outcome.merge_sha == _MERGE_SHA


def test_the_host_writes_nothing_to_the_forge_when_the_hold_authority_is_unreadable(
    tmp_path: Path,
) -> None:
    """Fail CLOSED. A host that cannot ask the ledger must not answer for it.

    The repo carries no connection block, so the hold read refuses rather than
    reporting a release. Arming on that reading would turn a substrate hiccup into
    the merge of work a maintainer may have just held.
    """
    runner = _Runner(queue=[_view(armed=False)])

    _ = _dispatch(repo=tmp_path, runner=runner, journal=_Journal())

    assert _forge_verbs(runner=runner) == {_VIEW_ARGV_HEAD}


def test_an_unreadable_hold_authority_refuses_the_host_merge_instead_of_waiting(
    tmp_path: Path,
) -> None:
    """The refusal half of failing closed, and it has to be EXPLICIT.

    Writing nothing to the forge is only half an answer: a host that then fell
    through to the merge poll would spend the whole budget waiting for a merge it
    had just declined to arm, and report "PR did not reach MERGED within the poll
    budget" -- a diagnosis that names the pull request as the problem and never
    mentions the ledger it could not read. So the stage is its own, the detail names
    the item and the hold, and the poll-budget sentence is asserted ABSENT: an
    operator reading this result must not be sent to look at the forge.
    """
    runner = _Runner(queue=[_view(armed=False)])

    dispatched = _dispatch(repo=tmp_path, runner=runner, journal=_Journal())

    assert (dispatched.outcome.status, dispatched.outcome.stage) == (
        "failed",
        "merge-hold-authority",
    )
    assert dispatched.outcome.pr_number == _PR_NUMBER
    assert dispatched.outcome.merge_sha is None
    assert dispatched.sleeps == ()
    assert _ITEM_ID in dispatched.outcome.detail
    assert "merge hold" in dispatched.outcome.detail
    assert "poll budget" not in dispatched.outcome.detail


def test_an_unheld_item_keeps_the_host_fallback_arming_with_its_journaled_merge_method(
    tmp_path: Path,
) -> None:
    """The control, and the non-regression claim beside it.

    The fallback exists for a pr stage that could not arm, so an unheld item must
    still be armed -- with the merge method this dispatch's own resolved contract
    journaled, never one re-derived later from configuration.
    """
    _tenant(repo=tmp_path, held=False)
    runner = _Runner(
        queue=[
            _view(armed=False),
            CommandResult(exit_code=0, stdout="", stderr=""),
            _view(armed=True),
        ]
    )
    journal = _Journal()

    dispatched = _dispatch(repo=tmp_path, runner=runner, journal=journal)

    assert _ARM_ARGV in runner.calls
    assert "pr-arm-fallback" in [record["stage"] for record in journal.records]
    # And it WAITS for the merge it just armed. This is the control for the held
    # terminal below: without it, "the held run never waited" is equally consistent
    # with a merge poll that no dispatch reaches any more.
    assert dispatched.outcome.stage == "merge-poll"
    assert dispatched.sleeps == (0.0,)


def test_a_run_held_after_dispatch_terminates_green_at_the_held_publication_boundary(
    tmp_path: Path,
) -> None:
    """The hold's TERMINAL, keyed on the hold the ledger carries NOW.

    Nothing may merge a held pull request, so a run that polled for its merge could
    only spend the whole budget and then report a FAILURE for work that succeeded --
    which is precisely what the stale-snapshot build did to a run held mid-flight,
    because its terminal classification read the same launch snapshot its arming did.

    Green is also what reclaims the claim under the ordinary green-terminal rule, so
    a held item holds no capacity slot while it waits for a person; and the green
    carries NO merge sha, because nothing merged.
    """
    _tenant(repo=tmp_path, held=True)
    # Stocked with everything the unheld control needed, so the held run is short of
    # nothing: a one-answer fixture would make an exhausted queue the verdict.
    runner = _Runner(queue=[_view(armed=False)] * 4)

    dispatched = _dispatch(repo=tmp_path, runner=runner, journal=_Journal())

    assert (dispatched.outcome.status, dispatched.outcome.stage) == ("green", "pr")
    assert dispatched.outcome.pr_number == _PR_NUMBER
    assert dispatched.outcome.merge_sha is None
    assert dispatched.sleeps == ()
    assert len(runner.calls) == 1
    assert f"set-merge-hold:{_ITEM_ID}:off" in dispatched.outcome.detail
