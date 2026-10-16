"""Tests for the Dispatcher's post-merge janitor engine slice."""

import json
from dataclasses import dataclass, field
from pathlib import Path

import livespec_orchestrator_beads_fabro.commands._dispatcher_engine_janitor as janitor_module
import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_janitor import post_merge
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_install_recipe import (
    JANITOR_BOOTSTRAP_KEY,
    JanitorBootstrapRecipe,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    build_plan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_step_ids import JANITOR_BOOTSTRAP

# A declaration carrying the two REQUIRED contract fields: an undeclared
# janitor-core pin, or an unresolved default branch, degrades the post-merge
# flow before any of these cases is reached.
_DECLARED_CONFIG = '{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}'


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id="x-1",
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        config_text=_DECLARED_CONFIG,
        default_branch="master",
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


def _err(*, stderr: str) -> CommandResult:
    return CommandResult(exit_code=1, stdout="", stderr=stderr)


def _branch() -> CommandResult:
    """What `git symbolic-ref --short refs/remotes/origin/HEAD` answers.

    The venue resolution runs between pull-primary and the preclean, so every
    queue that reaches provisioning names the default branch here and then
    answers the merge-containment probe.
    """
    return CommandResult(exit_code=0, stdout="origin/master\n", stderr="")


def _provisioning_queue() -> list[CommandResult]:
    """pull-primary, the venue resolution, and every stage after it, all green."""
    return [_ok(), _branch(), *[_ok() for _ in range(9)]]


# A declaration that additionally selects the CLUSTER venue for the janitor's
# own check suite, which is what this repository itself declares.
_CLUSTER_VENUE_CONFIG = (
    '{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}, '
    '"dispatcher": {"janitor": {"venue": "cluster_job"}}}}'
)

# Where the janitor's own check-suite stage sits in the runner's call log:
# pull-primary, the venue merge-containment probe, the preclean, the checkout
# add, the trust step, the bootstrap, the per-checkout bootstrap and the core
# provision all precede it.
_CHECK_SUITE_CALL = 8


def _gate(*, state: str) -> CommandResult:
    """What the delegated-gate client reports on its own JSON log line.

    `exit_code` follows that client's PUSH-oriented contract -- 0 only when the
    gate passed AND its green token was written -- which the janitor
    deliberately does not read: the token authorises a push and the Job's
    verdict is the only thing a post-merge gate is asking about.
    """
    return CommandResult(
        exit_code=0 if state == "PASSED" else 1,
        stdout="",
        stderr=json.dumps({"event": "delegated gate", "state": state, "detail": "tree 0ff1ce"}),
    )


def _cluster_queue(*, gate: CommandResult) -> list[CommandResult]:
    """pull-primary, the venue resolution, provisioning, the gate run, the cleanup."""
    return [_ok(), _branch(), *[_ok() for _ in range(6)], gate, _ok()]


def _write_cluster_venue(*, repo: Path) -> None:
    _ = (repo / ".livespec.jsonc").write_text(_CLUSTER_VENUE_CONFIG, encoding="utf-8")


def _merged() -> PrView:
    return PrView(
        number=7,
        state="MERGED",
        auto_merge_armed=True,
        merge_state_status="CLEAN",
        merge_sha="cafe08",
        terminal_required_check_failures=(),
    )


def test_post_merge_degraded_detail_truncates_long_checkout_error(tmp_path: Path) -> None:
    long_error = "prefix-" + ("x" * 600) + "-suffix"
    runner = Runner(queue=[_ok(), _branch(), _ok(), _ok(), _err(stderr=long_error)])

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=Journal(),
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("green", "janitor-env-degraded")
    assert "-suffix" in outcome.detail
    assert "prefix-" not in outcome.detail


def test_post_merge_degrades_when_primary_pull_fails_after_merge(tmp_path: Path) -> None:
    runner = Runner(
        queue=[
            _err(
                stderr=(
                    "error: Your local changes to the following files would be overwritten "
                    "by merge:\n\tplan/foreman/handoff.md\nPlease commit your changes or "
                    "stash them before you merge. Aborting"
                )
            )
        ]
    )

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=Journal(),
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("green", "janitor-env-degraded")
    assert (outcome.pr_number, outcome.merge_sha) == (7, "cafe08")
    assert "refreshing the primary checkout" in outcome.detail
    assert "plan/foreman/handoff.md" in outcome.detail
    assert "not a work-item failure" in outcome.detail


def test_post_merge_degrades_on_a_defective_recipe_instead_of_running_an_empty_argv(
    tmp_path: Path,
) -> None:
    """A present-but-unusable declaration resolves NO argv, so nothing is provisioned.

    The post-merge path is reached on a first dispatch, where no standing
    degradation exists for the pre-dispatch re-verification to have refused on,
    so this is the only place the defect is caught. Running the bootstrap stage
    anyway would hand the runner an empty command AFTER the merge has landed --
    a crash where the design has a named degraded outcome.
    """
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": '
        '{"janitor_bootstrap": {"owner": "dana"}}}}',
        encoding="utf-8",
    )
    plan = _plan(repo=tmp_path)
    runner = Runner(queue=_provisioning_queue())
    journal = Journal()

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("green", "janitor-env-degraded")
    # Named as the ratified step, so the degradation persists into the next
    # dispatch's refusal exactly as a failed bootstrap does.
    assert outcome.step == JANITOR_BOOTSTRAP
    assert outcome.missing_integration_point is not None
    assert outcome.remedy is not None
    assert JANITOR_BOOTSTRAP_KEY in outcome.detail
    # The primary checkout is still refreshed; nothing past it is provisioned.
    assert [record["stage"] for record in journal.records] == ["pull-primary"]
    assert not plan.janitor_checkout.exists()


def test_post_merge_lock_contention_refuses_before_preclean(tmp_path: Path) -> None:
    plan = _plan(repo=tmp_path)
    lock = plan.janitor_checkout.with_name(f"{plan.janitor_checkout.name}.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    _ = lock.write_text("work_item_id=x-1\n", encoding="utf-8")
    runner = Runner(queue=[])
    journal = Journal()

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("green", "janitor-env-degraded")
    assert (outcome.pr_number, outcome.merge_sha) == (7, "cafe08")
    assert "remove the stale lock file before retrying" in outcome.detail
    assert "janitor checkout lock" in outcome.detail
    assert runner.calls == []
    assert journal.records == []


def test_post_merge_releases_lock_when_locked_body_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan(repo=tmp_path)
    lock = plan.janitor_checkout.with_name(f"{plan.janitor_checkout.name}.lock")

    def raise_from_locked_body(
        *,
        outcome_type: type[DispatchOutcome],
        plan: DispatchPlan,
        runner: Runner,
        journal: Journal,
        merged: PrView,
        recipe: JanitorBootstrapRecipe,
    ) -> DispatchOutcome:
        _ = outcome_type
        _ = plan
        _ = runner
        _ = journal
        _ = merged
        _ = recipe
        raise RuntimeError("janitor body exploded")

    monkeypatch.setattr(janitor_module, "_post_merge_locked", raise_from_locked_body)

    with pytest.raises(RuntimeError, match="janitor body exploded"):
        post_merge(
            outcome_type=DispatchOutcome,
            plan=plan,
            runner=Runner(queue=[]),
            journal=Journal(),
            merged=_merged(),
        )

    assert not lock.exists()


def test_post_merge_reclaims_stale_pid_lock_before_preclean(tmp_path: Path) -> None:
    plan = _plan(repo=tmp_path)
    lock = plan.janitor_checkout.with_name(f"{plan.janitor_checkout.name}.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    _ = lock.write_text(
        '{"pid": 999999999, "started_at_epoch": 1.0, "work_item_id": "x-1"}',
        encoding="utf-8",
    )
    runner = Runner(queue=_provisioning_queue())
    journal = Journal()

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("green", "done")
    assert not lock.exists()
    assert next(record["stage"] for record in journal.records) == "pull-primary"


def test_post_merge_releases_lock_after_green(tmp_path: Path) -> None:
    plan = _plan(repo=tmp_path)
    lock = plan.janitor_checkout.with_name(f"{plan.janitor_checkout.name}.lock")
    runner = Runner(queue=_provisioning_queue())
    journal = Journal()

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("green", "done")
    assert not lock.exists()
    assert [record["stage"] for record in journal.records] == [
        "pull-primary",
        "janitor-checkout-preclean",
        "janitor-checkout-add",
        "janitor-checkout-trust",
        "janitor-checkout-bootstrap",
        "janitor-checkout-bootstrap-in-checkout",
        "janitor-core-provision",
        "janitor-post-merge",
        "janitor-checkout-remove",
    ]


def test_post_merge_cluster_venue_reports_green_from_the_gate_jobs_verdict(
    tmp_path: Path,
) -> None:
    """The declared cluster venue runs the delegated gate, not a local check suite.

    The Job's own verdict is what the janitor reports, so a PASSED gate closes
    the post-merge gate green exactly as a green local suite did -- and the
    command the host ran is the gate client in the fresh checkout rather than
    the check suite itself.
    """
    _write_cluster_venue(repo=tmp_path)
    plan = _plan(repo=tmp_path)
    runner = Runner(queue=_cluster_queue(gate=_gate(state="PASSED")))

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=Journal(),
        merged=_merged(),
    )

    gate_argv, gate_cwd = runner.calls[_CHECK_SUITE_CALL]
    assert "gate_remote_delegate" in " ".join(gate_argv)
    assert gate_argv[-1] == "run"
    assert gate_cwd == plan.janitor_checkout
    assert (outcome.status, outcome.stage) == ("green", "done")
    assert outcome.detail == "merged, post-merge janitor green"


def test_post_merge_cluster_venue_no_verdict_is_red_naming_the_missing_verdict(
    tmp_path: Path,
) -> None:
    """A gate that was asked and did not answer is RED, and says so as that.

    It is deliberately NOT the `janitor-env-degraded` outcome, which reports
    `green` at its own stage for a venue that could not be provisioned: a
    submitted gate whose verdict was lost is a gate that decided nothing, and
    an item must never close on a reading nobody took.
    """
    _write_cluster_venue(repo=tmp_path)
    runner = Runner(queue=_cluster_queue(gate=_gate(state="NO_VERDICT")))

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=Journal(),
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("failed", "janitor-post-merge")
    assert (outcome.pr_number, outcome.merge_sha) == (7, "cafe08")
    detail = outcome.detail.lower()
    assert "reached no verdict" in detail
    assert "missing cluster verdict" in detail


def test_post_merge_cluster_venue_failed_job_is_red_naming_the_jobs_own_verdict(
    tmp_path: Path,
) -> None:
    """The CONTROL for the case above: a real red verdict is reported as one.

    Without it, a no-verdict wording that fired on every non-pass would satisfy
    the missing-verdict assertion while telling an operator their red tree was
    a plumbing fault -- two conditions whose remedies are opposite.
    """
    _write_cluster_venue(repo=tmp_path)
    runner = Runner(queue=_cluster_queue(gate=_gate(state="FAILED")))

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path),
        runner=runner,
        journal=Journal(),
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("failed", "janitor-post-merge")
    detail = outcome.detail.lower()
    assert "reported a failed verdict" in detail
    assert "missing cluster verdict" not in detail
