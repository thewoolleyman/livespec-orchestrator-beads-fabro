"""Integration-tier acceptance for the pull-primary half of Scenario 32.

Binds the third gherkin block of `SPECIFICATION/scenarios.md` "Scenario 32 —
Adopter-target dispatch compatibility" — a target whose default branch is not
this fleet's, whose post-merge janitor pull-primary stage resolves that
repository's default branch, pulls that ref, and never hardcodes `master` — and
the `SPECIFICATION/contracts.md` default-branch-resolution clause it realizes,
which requires a dispatch-path stage referencing the target's primary branch to
resolve it through the one shared resolution.

DRIVING THE STAGE RATHER THAN THE ARGV BUILDER is the whole point of putting this
case at this tier. `pull_primary_argv` is already asserted by
`test_governed_repo_seams_scenario102`, and that assertion is about a function:
it cannot show that the post-merge flow REACHES it, in the position the stage
occupies, with the plan's own resolved contract. So the real `post_merge` runs
here, over a real on-disk journal, and the command is read off the stage's own
record and off the runner it was spawned through.

THE BRANCH IS NEITHER `master` NOR `main`, which is what makes the case able to
fail for the right reason. A fixture probing `main` would be satisfied by a stage
carrying a two-name fallback, and one probing `master` by a stage carrying the
literal the clause retires — so the fixture's branch is this tier's shared
`release`, chosen for exactly that reason, and the absence of both fleet names is
asserted across the WHOLE recorded sequence rather than in the pull alone.

THE POSITIVE CONTROL IS THE RESOLVED CONTRACT ITSELF. "No command named `master`"
is satisfied just as well by a janitor that ran nothing at all, so the pull is
asserted present, FIRST, and naming the probed branch — and the plan's resolved
`default_branch` is asserted to be that same probed value, so the stage is shown
reading the one resolution rather than agreeing with a constant this fixture
happens to share.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_janitor import post_merge
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_argv import pull_primary_argv
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, PrView
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import build_plan

from tests.integration.governed_repo_fixtures import (
    ADOPTER,
    PAYLOAD_RUN_CONFIG,
    PROBED_DEFAULT_BRANCH,
)

_PULL_PRIMARY_STAGE = "pull-primary"
_FLEET_BRANCH_NAMES: tuple[str, ...] = ("master", "main")
_MERGED = PrView(
    number=11,
    state="MERGED",
    auto_merge_armed=True,
    merge_state_status="CLEAN",
    merge_sha="cafe02",
    terminal_required_check_failures=(),
)


@dataclass(kw_only=True)
class _AlwaysOk:
    """A `CommandRunner` that succeeds, so the WHOLE post-merge sequence is recorded.

    Succeeding everywhere is what makes the sequence observable: a runner that
    failed the pull would stop the flow at the stage under test and the case could
    not then assert what the rest of the janitor named.
    """

    calls: list[tuple[list[str], Path]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del timeout_seconds, env, stdin
        self.calls.append((argv, cwd))
        return CommandResult(exit_code=0, stdout="", stderr="")


def _adopter_target(*, tmp_path: Path) -> Path:
    """An adopter checkout carrying the committed adopter fixture's declaration."""
    repo = tmp_path / "adopter-target"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(ADOPTER.config_text, encoding="utf-8")
    return repo


def _plan(*, repo: Path) -> DispatchPlan:
    """One dispatch plan for the adopter, built exactly as the Dispatcher builds one.

    `default_branch` is handed in because the plan build is where the ratified
    resolve-once rule puts it: the two-route probe runs before the plan exists and
    its answer rides the contract from there, which is what every later stage —
    this one included — is required to read rather than re-probing.
    """
    return build_plan(
        repo=repo,
        work_item_id="ad-1",
        workflow_toml=repo / "workflow.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-checkout",
        config_text=(repo / ".livespec.jsonc").read_text(encoding="utf-8"),
        default_branch=PROBED_DEFAULT_BRANCH,
        committed_workflow_text=PAYLOAD_RUN_CONFIG.read_text(encoding="utf-8"),
    )


def _records(*, journal_path: Path) -> list[dict[str, object]]:
    """Every record the post-merge flow wrote, in order.

    Deliberately NOT guarded onto an empty list for a missing file: a missing
    journal reads identically to a journal carrying no pull-primary record, which
    is half of what the case below asserts.
    """
    text = journal_path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line]


def test_scenario32_the_pull_primary_stage_pulls_the_targets_own_default_branch(
    tmp_path: Path,
) -> None:
    """The stage resolves the target's default branch, pulls that ref, names no fleet one.

    All three of the block's `Then` lines are properties of ONE stage execution,
    which is why they are one case: a build satisfying any two of them is a build
    that fails the third silently — a pull of the right ref that the flow never
    reaches, a reached stage pulling a literal, or a `master`-free sequence in
    which nothing was pulled at all.

    BOTH instruments the flow offers are read, and they answer different halves.
    The runner shows WHAT was spawned, which is the command that actually
    refreshes the checkout; the stage's journal row shows THAT the stage ran under
    its own ratified identifier and what it concluded, which is what an operator
    reads afterwards — the row carries no argv of its own, so neither instrument
    can stand in for the other.
    """
    repo = _adopter_target(tmp_path=tmp_path)
    plan = _plan(repo=repo)
    runner = _AlwaysOk()
    journal_path = tmp_path / "journal.jsonl"

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=JournalFile(path=journal_path),
        merged=_MERGED,
    )
    argvs = [argv for argv, _ in runner.calls]
    records = _records(journal_path=journal_path)
    pulls = [record for record in records if record["stage"] == _PULL_PRIMARY_STAGE]

    assert outcome.work_item_id == plan.work_item_id
    # The plan carries the PROBED branch, so the assertions below are about a
    # projection of the one resolution rather than about a constant this fixture
    # happens to share with the stage.
    assert plan.integration.contract.default_branch == PROBED_DEFAULT_BRANCH
    assert PROBED_DEFAULT_BRANCH not in _FLEET_BRANCH_NAMES
    # The stage ran, FIRST, and pulled the resolved ref.
    expected = ["git", "-C", str(repo), "pull", "--ff-only", "origin", PROBED_DEFAULT_BRANCH]
    assert argvs[0] == expected
    assert pull_primary_argv(plan=plan) == expected
    # The stage ran under its own ratified identifier, exactly once, and concluded
    # green — which is what tells "the pull ran as this stage" apart from a `git
    # pull` some other step of the flow happened to spawn.
    assert len(pulls) == 1
    assert pulls[0]["exit_code"] == 0
    # And no command of the WHOLE post-merge sequence names a fleet branch, which
    # is where a surviving literal would otherwise sit: the janitor checkout, the
    # merge-containment probe and the worktree removal each reference a branch too.
    assert [argv for argv in argvs if any(name in argv for name in _FLEET_BRANCH_NAMES)] == []
