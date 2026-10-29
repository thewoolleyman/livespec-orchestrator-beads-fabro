"""The post-merge / reconcile janitor VENUE: the merged default-branch tip.

The venue is the target repository's default-branch tip that CONTAINS the
item's merge -- never the item's historical merge sha. Pinning it to the merge
sha deadlocks every item that merged before a janitor-environment fix landed,
because each reconcile re-provisions a checkout from before the fix existed.

The branch itself is READ OFF THE PLAN'S RESOLVED INTEGRATION CONTRACT, whose
`default_branch` field carries what the ratified two-route resolution answered
at plan build, so these cases declare it on the plan rather than queueing a
probe result for the venue to read.

Every behavioural case is driven through `post_merge`, the published entry
point both the post-merge flow and the reconcile-merged valve call, so the
assertions are about what the janitor actually provisions rather than about a
helper's return value.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_engine_janitor,
    _dispatcher_reconcile_merged,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_core_provisioning_view import (
    FLEET_JANITOR_CORE_REPO_URL,
    JANITOR_CORE_PINNED_KEY,
    JANITOR_CORE_REPO_KEY,
    UNRESOLVED_JANITOR_CORE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_janitor import post_merge
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_venue import (
    fleet_toolchain_is_the_host_janitor_premise,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    build_plan,
    janitor_reconcile_checkout_path,
)

_MERGE_SHA = "16fe3ac"


# The venue cases are about WHERE the janitor runs, so every one of them
# declares a janitor-core ref: an undeclared pin degrades before the venue is
# ever resolved.
_DECLARED_CONFIG = '{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}'

# The same repository with BOTH host-janitor points declared, which is what makes
# the fleet toolchain not a premise of its venue.
_ADOPTER_CONFIG = (
    '{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}, "dispatcher": '
    '{"janitor": {"check_suite": ["make", "verify"]}, '
    '"janitor_bootstrap": {"recipe": ["make", "install-hooks"]}}}}'
)


def _plan(
    *, repo: Path, default_branch: str | None = "master", config_text: str = _DECLARED_CONFIG
) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id="x-1",
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        config_text=config_text,
        default_branch=default_branch,
    )


@dataclass(kw_only=True)
class Runner:
    queue: list[CommandResult]
    calls: list[tuple[list[str], Path]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = env
        assert timeout_seconds > 0
        self.calls.append((argv, cwd))
        return self.queue.pop(0)


@dataclass(kw_only=True)
class Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _ok() -> CommandResult:
    return CommandResult(exit_code=0, stdout="", stderr="")


def _err(*, stderr: str = "") -> CommandResult:
    return CommandResult(exit_code=1, stdout="", stderr=stderr)


def _merged(*, merge_sha: str | None = _MERGE_SHA) -> PrView:
    return PrView(
        number=7,
        state="MERGED",
        auto_merge_armed=True,
        merge_state_status="CLEAN",
        merge_sha=merge_sha,
    )


def test_janitor_venue_module_owns_provisioning_and_old_privates_are_gone() -> None:
    module_path = (
        Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
        / "_dispatcher_janitor_venue.py"
    )
    venue_public_names = {
        "UNRESOLVED_VENUE",
        "JanitorVenue",
        "fleet_toolchain_is_the_host_janitor_premise",
        "provision_janitor_checkout",
        "remove_janitor_core_checkout",
        "resolve_janitor_venue",
    }

    assert module_path.is_file()
    venue = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_venue"
    )
    assert set(venue.__all__) == venue_public_names
    for name in venue_public_names:
        assert hasattr(venue, name)
    # The provisioning moved out of the flow module wholesale, and the shaper
    # both halves need is public on the degraded module rather than duplicated.
    assert not hasattr(_dispatcher_engine_janitor, "_provision_janitor_checkout")
    assert not hasattr(_dispatcher_engine_janitor, "_degraded_step")


def test_post_merge_provisions_the_venue_at_the_merged_default_branch_tip(tmp_path: Path) -> None:
    """The deadlock-cleared case: the venue is the tip, so a later fix is present.

    An item merged before a janitor-environment fix landed is provisioned at the
    CURRENT default-branch tip, which carries both its merge and the later fix --
    where a venue pinned to the item's merge sha could only ever re-fail.
    """
    plan = _plan(repo=tmp_path, default_branch="main")
    runner = Runner(queue=[_ok(), *[_ok() for _ in range(9)]])
    journal = Journal()

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("green", "done")
    argvs = [argv for argv, _ in runner.calls]
    assert [
        "git",
        "-C",
        str(tmp_path),
        "merge-base",
        "--is-ancestor",
        _MERGE_SHA,
        "origin/main",
    ] in argvs
    add = next(argv for argv in argvs if argv[3:5] == ["worktree", "add"])
    assert add[-1] == "origin/main"
    # The merge sha is what the venue is PROVEN AGAINST, never what it is pinned
    # to: it appears in the containment probe and nowhere else.
    assert [argv for argv in argvs if _MERGE_SHA in argv] == [
        ["git", "-C", str(tmp_path), "merge-base", "--is-ancestor", _MERGE_SHA, "origin/main"]
    ]


def test_post_merge_provisions_the_janitor_checkout_itself_before_the_check_suite(
    tmp_path: Path,
) -> None:
    """The per-checkout bootstrap leg: a provisioning recipe run IN the fresh checkout.

    The hook-install leg installs into the SHARED `.git/hooks` and is therefore
    correctly run from the primary, which is why it never provisioned anything
    the janitor checkout owns on its own. The worktree-discipline pack is exactly
    that: gitignored, so a newly added worktree has none of it, its check suite
    fails `worktree_pack_absent` on a fully conformant repository, and an
    already-merged GREEN item strands in `active`.

    Both legs are asserted together, because the fix is worthless if it moved the
    hooks leg off the primary rather than adding a second leg beside it.
    """
    plan = _plan(repo=tmp_path, default_branch="main")
    runner = Runner(queue=[_ok(), *[_ok() for _ in range(9)]])
    journal = Journal()

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("green", "done")
    assert (["mise", "exec", "--", "just", "install-worktree-pack"], plan.janitor_checkout) in (
        runner.calls
    )
    # The hooks leg still runs where the shared hooks dir is, so this ADDED a
    # per-checkout leg rather than relocating the one that was already right.
    hooks = next(
        cwd
        for argv, cwd in runner.calls
        if argv == ["mise", "exec", "--", "just", "install-commit-refuse-hooks"]
    )
    assert hooks == tmp_path
    stages = [record["stage"] for record in journal.records]
    # Ordering is the whole point: the pack has to be installed BEFORE the check
    # suite reads it, and after the trust step whose `mise` the recipe rides.
    assert stages.index("janitor-checkout-trust") < stages.index(
        "janitor-checkout-bootstrap-in-checkout"
    )
    assert stages.index("janitor-checkout-bootstrap-in-checkout") < stages.index(
        "janitor-post-merge"
    )


def test_post_merge_provisioning_steps_journal_both_streams(tmp_path: Path) -> None:
    """A bootstrap that FAILS OPEN is invisible unless both streams are journaled.

    `detail` alone carries whichever stream the exit code selected, so a step
    that exits 0 having provisioned nothing -- with its diagnosis on stderr --
    journals a record indistinguishable from one that worked. The bootstrap legs
    are where that matters, and the fixture is exactly that shape: exit 0, an
    empty stdout, and a real complaint on stderr.
    """
    plan = _plan(repo=tmp_path, default_branch="main")
    fail_open = CommandResult(exit_code=0, stdout="", stderr="warning: nothing to install")
    runner = Runner(queue=[_ok(), _ok(), _ok(), _ok(), _ok(), fail_open, fail_open, *[_ok()] * 3])
    journal = Journal()

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("green", "done")
    bootstrap_records = [
        record
        for record in journal.records
        if record["stage"]
        in {"janitor-checkout-bootstrap", "janitor-checkout-bootstrap-in-checkout"}
    ]
    assert len(bootstrap_records) == 2
    for record in bootstrap_records:
        assert record["exit_code"] == 0
        assert record["stdout"] == ""
        assert record["stderr"] == "warning: nothing to install"
    # The control: `detail` alone selected stdout on a zero exit, so the record
    # without the streams says nothing at all about what went wrong.
    assert {record["detail"] for record in bootstrap_records} == {""}


def test_post_merge_degrades_when_the_janitor_checkout_provisioning_fails(
    tmp_path: Path,
) -> None:
    """A failed per-checkout leg degrades naming the checkout, with no step id.

    The closed step vocabulary is what a pre-dispatch refusal reads, and this leg
    is not one of its members: it is a host-environment failure with no
    integration point an adopter could provide, so it must not stand up a refusal
    the adopter has no way to clear.
    """
    plan = _plan(repo=tmp_path, default_branch="main")
    runner = Runner(
        queue=[
            _ok(),
            _ok(),
            _ok(),
            _ok(),
            _ok(),
            _ok(),
            _err(stderr="just: no recipe"),
            *[_ok()] * 3,
        ]
    )
    journal = Journal()

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("green", "janitor-env-degraded")
    assert "per-worktree dev-tooling pack" in outcome.detail
    assert str(plan.janitor_checkout) in outcome.detail
    assert "just: no recipe" in outcome.detail
    assert outcome.step is None
    # The janitor never ran against an unprovisioned checkout.
    assert "janitor-post-merge" not in [record["stage"] for record in journal.records]


def test_post_merge_emits_no_checkout_bootstrap_when_the_venue_runs_declared_commands(
    tmp_path: Path,
) -> None:
    """An adopter's venue is never handed this fleet's per-checkout recipe either.

    The pack is a livespec-dev-tooling artifact, so installing it is a PREMISE of
    the fleet-default host-janitor commands rather than an obligation every
    governed repository owes -- the same reasoning that gates the trust step, and
    the same resolution ARM. The member case above is the positive control for
    this absence: it runs the same code path and DOES emit the leg.
    """
    plan = _plan(repo=tmp_path, default_branch="main", config_text=_ADOPTER_CONFIG)
    runner = Runner(queue=[_ok(), *[_ok() for _ in range(9)]])
    journal = Journal()

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("green", "done")
    assert "janitor-checkout-bootstrap-in-checkout" not in [
        record["stage"] for record in journal.records
    ]
    assert [argv for argv, _ in runner.calls if "install-worktree-pack" in argv] == []


def test_reconcile_valve_provisions_its_own_janitor_checkout_through_the_same_seam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reconcile venue inherits the per-checkout leg because it IS the same seam.

    The reconcile valve differs from a live dispatch only in the checkout it
    names, so the provisioning it gets is whatever `post_merge` provisions --
    which is what makes a fix here reach both venues rather than one. Both halves
    are asserted: that the valve calls this entry point, and that the leg lands in
    the reconcile checkout rather than in a live-dispatch one.

    The reconcile checkout path is rooted at the invoking user's HOME, and the
    janitor lock is written beside it, so HOME is redirected into `tmp_path`
    rather than letting a unit test deposit directories in the real one.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    checkout = janitor_reconcile_checkout_path(repo=tmp_path, work_item_id="x-1")
    plan = replace(_plan(repo=tmp_path, default_branch="main"), janitor_checkout=checkout)
    runner = Runner(queue=[_ok(), *[_ok() for _ in range(9)]])
    journal = Journal()

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("green", "done")
    assert _dispatcher_reconcile_merged.post_merge is post_merge
    assert checkout.name.startswith("janitor-reconcile-")
    assert (["mise", "exec", "--", "just", "install-worktree-pack"], checkout) in runner.calls


def test_post_merge_emits_no_trust_step_when_the_venue_runs_declared_commands(
    tmp_path: Path,
) -> None:
    """A repository declaring BOTH host-janitor points never gets this fleet's trust step.

    The trust command is a premise of the fleet-default check-suite and bootstrap
    recipe, not something every governed repository owes. Where both resolved
    `Declared` the venue runs the repository's own commands, so imposing a tool it
    does not carry would fail the step and degrade a post-merge outcome for a
    premise nobody declared.

    The member case above is the positive control for this absence: it runs the
    same code path, resolves both points to `FleetDefault`, and DOES emit the
    step -- so an argv list that could never contain it is not what is being read
    here.
    """
    plan = _plan(repo=tmp_path, default_branch="main", config_text=_ADOPTER_CONFIG)
    runner = Runner(queue=[_ok(), *[_ok() for _ in range(9)]])
    journal = Journal()

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("green", "done")
    assert fleet_toolchain_is_the_host_janitor_premise(plan=plan) is False
    assert "janitor-checkout-trust" not in [record["stage"] for record in journal.records]
    assert [argv for argv, _ in runner.calls if argv == ["mise", "trust"]] == []


def test_post_merge_degrades_when_the_resolved_tip_does_not_contain_the_merge(
    tmp_path: Path,
) -> None:
    plan = _plan(repo=tmp_path, default_branch="main")
    runner = Runner(queue=[_ok(), _err(), *[_ok() for _ in range(9)]])
    journal = Journal()

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("green", "janitor-env-degraded")
    assert "does NOT contain" in outcome.detail
    assert (
        outcome.missing_integration_point
        == f"a origin/main tip containing the item's merge {_MERGE_SHA}"
    )
    assert outcome.remedy is not None
    assert "re-run the reconcile" in outcome.remedy
    # The venue is not a step of the closed vocabulary, so the degradation
    # carries no step id and stands up no pre-dispatch refusal.
    assert outcome.step is None
    # Nothing is provisioned against a tip that cannot prove the merge landed.
    assert [record["stage"] for record in journal.records] == ["pull-primary"]


def test_post_merge_degrades_when_no_default_branch_can_be_resolved(tmp_path: Path) -> None:
    """Both probe routes silent at plan build leaves the REQUIRED field unresolved."""
    plan = _plan(repo=tmp_path, default_branch=None)
    runner = Runner(queue=[_ok(), *[_ok() for _ in range(9)]])
    journal = Journal()

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("green", "janitor-env-degraded")
    assert (
        outcome.missing_integration_point == "a resolvable default branch for the target repository"
    )
    assert outcome.remedy is not None
    assert "git remote set-head origin --auto" in outcome.remedy
    assert [record["stage"] for record in journal.records] == ["pull-primary"]


def test_post_merge_venue_skips_the_containment_probe_when_no_merge_sha_is_known(
    tmp_path: Path,
) -> None:
    """No merge sha is nothing to confirm, not a degradation."""
    plan = _plan(repo=tmp_path, default_branch="master")
    runner = Runner(queue=[_ok(), *[_ok() for _ in range(9)]])
    journal = Journal()

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=_merged(merge_sha=None),
    )

    assert (outcome.status, outcome.stage) == ("green", "done")
    argvs = [argv for argv, _ in runner.calls]
    # `origin/master` here is RESOLVED, not a literal fallback: the contract
    # carries a declared branch, and it is the absence of a merge sha -- not of a
    # default branch -- that leaves the containment probe unmade.
    assert plan.integration.contract.default_branch == "master"
    assert not [argv for argv in argvs if "merge-base" in argv]
    add = next(argv for argv in argvs if argv[3:5] == ["worktree", "add"])
    assert add[-1] == "origin/master"


def test_post_merge_degrades_naming_the_undeclared_janitor_core_declaration(
    tmp_path: Path,
) -> None:
    """An unresolved janitor-core pin degrades BEFORE anything is provisioned for it.

    The plan carries the sentinel rather than a moving `master`, and the
    degradation names the committed key the operator has to write -- where the
    clone's own stderr would name a branch the repository never declared.
    """
    plan = replace(_plan(repo=tmp_path), janitor_core_ref=UNRESOLVED_JANITOR_CORE)
    runner = Runner(queue=[_ok(), *[_ok() for _ in range(9)]])
    journal = Journal()

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("green", "janitor-env-degraded")
    assert JANITOR_CORE_PINNED_KEY in outcome.detail
    assert (
        outcome.missing_integration_point
        == "a declared livespec-core ref for the target repository"
    )
    assert outcome.remedy is not None
    assert JANITOR_CORE_REPO_KEY.rsplit(".", maxsplit=1)[-1] in outcome.remedy
    # Janitor-core provisioning is not a step of the closed vocabulary.
    assert outcome.step is None
    # Nothing is provisioned, and the venue is never even resolved.
    assert [record["stage"] for record in journal.records] == ["pull-primary"]


def test_post_merge_degrades_naming_an_unusable_core_repo_declaration(tmp_path: Path) -> None:
    """A present-but-unusable `core_repo` refuses instead of sliding onto the fleet default."""
    plan = replace(_plan(repo=tmp_path), janitor_core_repo_url=UNRESOLVED_JANITOR_CORE)
    runner = Runner(queue=[_ok(), *[_ok() for _ in range(9)]])
    journal = Journal()

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("green", "janitor-env-degraded")
    assert JANITOR_CORE_REPO_KEY in outcome.detail
    assert FLEET_JANITOR_CORE_REPO_URL not in outcome.detail
