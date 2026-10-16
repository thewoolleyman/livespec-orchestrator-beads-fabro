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


def _gate_reply(*, state: str, detail: str) -> CommandResult:
    """What the delegated cluster gate's own structured output looks like.

    The gate client streams the Job's pod logs to its caller BEFORE it renders
    its verdict, so the verdict object is the last structured line on the
    stream rather than the only thing on it. The fake reply carries an
    unstructured line ahead of it for that reason: a reader that took the first
    line, or that required the whole stream to parse, would pass against a
    stream that never happens in production.
    """
    verdict_line = json.dumps(
        {
            "state": state,
            "detail": detail,
            "event": "delegated gate",
            "level": "info",
            "timestamp": "2026-10-16T00:00:00Z",
        }
    )
    return CommandResult(
        exit_code=0 if state == "PASSED" else 1,
        stdout="",
        stderr=f"a pod log line that is not structured\n{verdict_line}\n",
    )


def _cluster_queue(*, reply: CommandResult) -> list[CommandResult]:
    """`_provisioning_queue` with the cluster gate where the local suite ran.

    The gate stands at the same position in the queue the host-local check
    suite occupied, which is the point: the stages BEFORE it provision the
    fresh checkout either way, and the stage after it removes that checkout.
    """
    return [_ok(), _branch(), *[_ok() for _ in range(6)], reply, _ok()]


# The index of the janitor gate's own call in `_cluster_queue`, named rather
# than counted at each use so a provisioning stage added later moves one
# constant instead of silently re-aiming every assertion at its neighbour.
_GATE_CALL_INDEX = 8


def _cluster_repo(*, tmp_path: Path) -> Path:
    """A target repository whose committed configuration selects the cluster."""
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": '
        '{"janitor_gate_venue": "cluster_job"}}}',
        encoding="utf-8",
    )
    return tmp_path


def _merged() -> PrView:
    return PrView(
        number=7,
        state="MERGED",
        auto_merge_armed=True,
        merge_state_status="CLEAN",
        merge_sha="cafe08",
        terminal_required_check_failures=(),
    )


def test_post_merge_green_comes_from_the_cluster_jobs_passed_verdict(tmp_path: Path) -> None:
    """A cluster-venue merge is gated by a Job, and its green IS that verdict.

    Both halves are asserted because either alone is satisfied by the wrong
    implementation: a green outcome alone is what the host-local suite already
    produces, and a cluster stage alone would be satisfied by a stage whose
    verdict nothing read. The host-local check-suite stage is asserted ABSENT
    for the same reason — a janitor that ran both would report a green the
    cluster had no part in.
    """
    plan = _plan(repo=_cluster_repo(tmp_path=tmp_path))
    runner = Runner(
        queue=_cluster_queue(reply=_gate_reply(state="PASSED", detail="the gate passed on cafe08"))
    )
    journal = Journal()

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=plan,
        runner=runner,
        journal=journal,
        merged=_merged(),
    )

    stages = [record["stage"] for record in journal.records]
    assert (outcome.status, outcome.stage) == ("green", "done")
    assert "janitor-post-merge-cluster" in stages
    assert "janitor-post-merge" not in stages
    gate_argv, gate_cwd = runner.calls[_GATE_CALL_INDEX]
    assert gate_cwd == plan.janitor_checkout
    assert tuple(gate_argv) != plan.janitor


def test_post_merge_reports_red_when_the_cluster_jobs_verdict_is_failed(tmp_path: Path) -> None:
    """A red Job is the janitor's red, and it carries the Job's own reason."""
    runner = Runner(
        queue=_cluster_queue(
            reply=_gate_reply(
                state="FAILED", detail="the gate Job gate-abc ended Failed on tree cafe08"
            )
        )
    )

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=_cluster_repo(tmp_path=tmp_path)),
        runner=runner,
        journal=Journal(),
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("failed", "janitor-post-merge-cluster")
    assert "ended Failed on tree cafe08" in outcome.detail


def test_post_merge_names_the_missing_verdict_when_the_cluster_returns_none(
    tmp_path: Path,
) -> None:
    """A cluster that said nothing is red, and the detail SAYS it said nothing.

    Never green, and never described as a gate that reported a result: a merge
    the cluster did not gate has not been gated, and the remedy for an absent
    verdict is on the cluster or in the credential that reaches it rather than
    in the repository. Reporting it as a failed gate would send an operator to
    read a check that never ran.
    """
    runner = Runner(
        queue=_cluster_queue(
            reply=_gate_reply(
                state="NO_VERDICT",
                detail="await-gate-terminal did not complete, so the gate reached no verdict",
            )
        )
    )

    outcome = post_merge(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=_cluster_repo(tmp_path=tmp_path)),
        runner=runner,
        journal=Journal(),
        merged=_merged(),
    )

    assert (outcome.status, outcome.stage) == ("failed", "janitor-post-merge-cluster")
    assert "NO VERDICT" in outcome.detail
    assert "nothing gated this merge" in outcome.detail
    assert "await-gate-terminal did not complete" in outcome.detail


def test_post_merge_keeps_the_host_process_venue_when_none_is_declared(tmp_path: Path) -> None:
    """A repository that declares no venue keeps the host-local check suite.

    The opt-out is what makes the cluster path this repository's SETTING rather
    than every governed repository's new premise, so it is asserted here rather
    than left to the venue resolver's own unit coverage: a default that only
    held inside the resolver would still move every adopter's janitor.
    """
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

    stages = [record["stage"] for record in journal.records]
    assert (outcome.status, outcome.stage) == ("green", "done")
    assert "janitor-post-merge" in stages
    assert "janitor-post-merge-cluster" not in stages
    assert tuple(runner.calls[_GATE_CALL_INDEX][0]) == plan.janitor


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
