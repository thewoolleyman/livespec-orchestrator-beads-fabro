"""The janitor venue is the merged default-branch tip, and it must PROVE the merge.

Binds `SPECIFICATION/scenarios.md` Scenario 98. Both cases run against a REAL
git repository built for the situation the clause exists for -- an item merged
FIRST, a janitor-environment fix landing on the default branch AFTERWARDS -- and
drive production venue resolution and production provisioning over it, so the
claim is measured on git's own answer rather than on a stubbed one. Each is
parametrized over BOTH committed governed-repository fixtures, since the venue is
a dispatch-path seam.

THE FIRST CASE CARRIES ITS OWN CONTROL, and the control is the retired design.
"The venue contains the fix" is only evidence if a venue that could NOT contain
it is distinguishable, so the same repository is provisioned twice through the
same production argv builder: once at the resolved tip, and once at the item's
historical merge sha -- the pin that made a post-fix environment repair unable to
EVER clear a pre-fix item. The first checkout carries the fix; the second cannot.
Without that second provisioning, both designs would pass the first assertion.

THE SECOND CASE IS THE OTHER HALF OF THE SAME CLAUSE. Provisioning at the tip
keeps the guarantee the sha pin was bought with only once the tip is CONFIRMED to
contain the merge, so a tip that does not is a degraded post-merge outcome
carrying the missing point and the remedy. It is asserted through
`provision_janitor_checkout` rather than through venue resolution alone, because
"does not silently proceed" is a claim about what was NOT run: the recorded argv
list must hold the merge-presence check and NOTHING else, and no checkout may
exist on disk afterwards.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_install_recipe import (
    janitor_bootstrap_recipe_from_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_venue import (
    JanitorVenue,
    provision_janitor_checkout,
    resolve_janitor_venue,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    build_plan,
    janitor_venue_contains_merge_argv,
    janitor_worktree_add_argv,
)

from tests.integration.governed_repo_fixtures import (
    PAYLOAD_RUN_CONFIG,
    GovernedRepo,
    over_both_fixtures,
)

# Deliberately NEITHER `master` NOR `main`: a venue that named a branch this
# fleet happens to use could not be told apart from one that resolved the
# repository's own default branch.
_DEFAULT_BRANCH = "release"
_TIP = f"origin/{_DEFAULT_BRANCH}"
_GIT_TIMEOUT_SECONDS = 120.0

_ITEM_FILE = "item.txt"
_FIX_FILE = "janitor-environment.txt"
_ITEM_TEXT = "the work this item merged\n"
_FIX_TEXT = "the janitor-environment fix that landed after that merge\n"


@dataclass(frozen=True, kw_only=True)
class _MergedThenFixed:
    """A repository whose default-branch tip carries an item's merge AND a later fix."""

    root: Path
    merge_sha: str
    unmerged_sha: str


@over_both_fixtures
def test_a_post_merge_environment_fix_clears_an_item_merged_before_the_fix_landed(
    governed: GovernedRepo,
    tmp_path: Path,
) -> None:
    """The venue is the tip, it carries both commits, and no override was needed."""
    repo = _merged_then_fixed(tmp_path=tmp_path)
    shell = ShellCommandRunner()
    at_tip = _plan(governed=governed, repo=repo, checkout=tmp_path / "venue-at-tip")
    at_merge_sha = _plan(governed=governed, repo=repo, checkout=tmp_path / "venue-at-merge-sha")

    venue = resolve_janitor_venue(plan=at_tip, runner=shell, merge_sha=repo.merge_sha)
    provisioned = shell.run(
        argv=janitor_worktree_add_argv(plan=at_tip, tip=venue.ref),
        cwd=repo.root,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    pinned = shell.run(
        argv=janitor_worktree_add_argv(plan=at_merge_sha, tip=repo.merge_sha),
        cwd=repo.root,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )

    assert venue == JanitorVenue(ref=_TIP)
    assert provisioned.exit_code == 0, provisioned.stderr
    assert (at_tip.janitor_checkout / _ITEM_FILE).read_text(encoding="utf-8") == _ITEM_TEXT
    assert (at_tip.janitor_checkout / _FIX_FILE).read_text(encoding="utf-8") == _FIX_TEXT
    # The check-suite the janitor would run comes off the repository's own
    # committed declaration, so the item clears with no `--janitor` override.
    assert at_tip.janitor == governed.janitor_check_suite
    # The control: the retired sha-pinned venue provisions a checkout that
    # carries the merge and CANNOT carry the later fix.
    assert pinned.exit_code == 0, pinned.stderr
    assert (at_merge_sha.janitor_checkout / _ITEM_FILE).is_file()
    assert not (at_merge_sha.janitor_checkout / _FIX_FILE).exists()


@over_both_fixtures
def test_a_resolved_tip_that_does_not_contain_the_merge_degrades_rather_than_proceeding(
    governed: GovernedRepo,
    tmp_path: Path,
) -> None:
    """A tip that cannot prove the merge landed provisions NOTHING and says why."""
    repo = _merged_then_fixed(tmp_path=tmp_path)
    plan = _plan(governed=governed, repo=repo, checkout=tmp_path / "venue-unproven")
    runner = _Recording(inner=ShellCommandRunner())
    # The REAL append-only journal, so "no provisioning stage was journaled" is
    # read off the artifact a dispatch actually leaves rather than off a stand-in.
    journal_path = tmp_path / "journal" / "fabro-dispatch-journal.jsonl"

    outcome = provision_janitor_checkout(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=JournalFile(path=journal_path),
        merged=_merged(merge_sha=repo.unmerged_sha),
        recipe=janitor_bootstrap_recipe_from_block(block=dispatcher_block(cwd=governed.root)),
    )

    assert outcome is not None
    assert (outcome.status, outcome.stage) == ("green", "janitor-env-degraded")
    assert outcome.missing_integration_point is not None
    assert _TIP in outcome.missing_integration_point
    assert repo.unmerged_sha in outcome.missing_integration_point
    assert outcome.remedy is not None
    assert _TIP in outcome.remedy
    # The venue is NOT a step of the closed vocabulary, so the degradation
    # carries its missing point and remedy without one.
    assert outcome.step is None
    # Nothing was provisioned: the merge-presence check is the ONLY command that
    # ran, and no checkout was left behind for a janitor to run in.
    assert runner.argvs == [
        janitor_venue_contains_merge_argv(plan=plan, tip=_TIP, merge_sha=repo.unmerged_sha)
    ]
    assert not plan.janitor_checkout.exists()
    assert not journal_path.exists()


@dataclass(frozen=True, kw_only=True)
class _Recording:
    """A `CommandRunner` that records every argv and delegates to the real one.

    Recording is what the no-silent-proceed assertion needs -- the claim is about
    the commands that were NOT run -- and delegating is what keeps git's own
    answer, rather than a canned one, deciding whether the tip contains the merge.
    """

    inner: ShellCommandRunner
    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        self.argvs.append(argv)
        return self.inner.run(argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env)


def _merged_then_fixed(*, tmp_path: Path) -> _MergedThenFixed:
    """A real repository: seed, the item's merge, then a LATER environment fix.

    The fourth commit is the one the second case needs -- a real commit that the
    default-branch tip does not contain, made by branching off the seed rather
    than off the tip, so `git merge-base --is-ancestor` genuinely answers no.
    """
    root = tmp_path / "governed"
    root.mkdir()
    _git(root, "init", "-b", _DEFAULT_BRANCH)
    _git(root, "config", "user.email", "venue-test@example.invalid")
    _git(root, "config", "user.name", "Venue Test")
    seed = _commit(root=root, name="seed.txt", text="seed\n", message="seed")
    merge_sha = _commit(root=root, name=_ITEM_FILE, text=_ITEM_TEXT, message="the item's merge")
    _ = _commit(root=root, name=_FIX_FILE, text=_FIX_TEXT, message="the janitor-environment fix")
    remote = tmp_path / "governed-origin.git"
    _git(tmp_path, "init", "--bare", str(remote))
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "-u", "origin", _DEFAULT_BRANCH)
    _git(root, "checkout", "-b", "side", seed)
    unmerged_sha = _commit(root=root, name="side.txt", text="side\n", message="never merged")
    _git(root, "checkout", _DEFAULT_BRANCH)
    return _MergedThenFixed(root=root, merge_sha=merge_sha, unmerged_sha=unmerged_sha)


def _commit(*, root: Path, name: str, text: str, message: str) -> str:
    _ = (root / name).write_text(text, encoding="utf-8")
    _git(root, "add", name)
    _git(root, "commit", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _merged(*, merge_sha: str) -> PrView:
    return PrView(
        number=98,
        state="MERGED",
        auto_merge_armed=True,
        merge_state_status="CLEAN",
        merge_sha=merge_sha,
    )


def _plan(*, governed: GovernedRepo, repo: _MergedThenFixed, checkout: Path) -> DispatchPlan:
    """A dispatch plan for the real repository, off this fixture's own declaration."""
    return build_plan(
        repo=repo.root,
        work_item_id="fixture-98",
        workflow_toml=repo.root / "workflow.toml",
        goal_file=repo.root / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=checkout,
        config_text=governed.config_text,
        default_branch=_DEFAULT_BRANCH,
        committed_workflow_text=PAYLOAD_RUN_CONFIG.read_text(encoding="utf-8"),
    )
