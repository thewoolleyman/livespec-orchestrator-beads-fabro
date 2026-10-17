"""Tests for the Dispatcher's post-merge janitor engine slice."""

from dataclasses import dataclass, field
from pathlib import Path

import livespec_orchestrator_beads_fabro.commands._dispatcher_engine_janitor as janitor_module
import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_janitor import (
    JANITOR_REMOVED_ENV_VARS,
    janitor_env_delta,
    janitor_removed_env_vars,
    post_merge,
)
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


def test_janitor_env_delta_adds_the_core_root_and_removes_every_scrubbed_name() -> None:
    """The delta is one addition plus one removal entry per scrubbed variable.

    The scrub set is asserted by LITERAL name rather than by comparing the
    delta against the constant it is built from: the point of the entry is
    WHICH variables it names, and a self-comparison would hold for a set that
    named none of them.
    """
    delta = janitor_env_delta(core_plugin_root="/janitor-co/.livespec-core/.claude-plugin")

    assert delta == {
        "LIVESPEC_CORE_PLUGIN_ROOT": "/janitor-co/.livespec-core/.claude-plugin",
        "LIVESPEC_FABRO_FACTORY": None,
        "LIVESPEC_INVOKER": None,
    }
    assert JANITOR_REMOVED_ENV_VARS == ("LIVESPEC_FABRO_FACTORY", "LIVESPEC_INVOKER")


def test_janitor_removed_env_vars_reports_only_the_names_the_environment_carries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The row's account is a READING, while the delta states the whole set.

    Both arms matter and they are different claims: the delta may name a
    variable this process does not carry, because removing an absent name is a
    no-op, but the row must not claim to have removed one.
    """
    monkeypatch.setenv("LIVESPEC_FABRO_FACTORY", "hp-candidate")
    monkeypatch.delenv("LIVESPEC_INVOKER", raising=False)

    assert janitor_removed_env_vars() == ("LIVESPEC_FABRO_FACTORY",)

    monkeypatch.delenv("LIVESPEC_FABRO_FACTORY")

    assert janitor_removed_env_vars() == ()
