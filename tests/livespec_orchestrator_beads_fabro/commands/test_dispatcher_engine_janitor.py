"""Tests for the Dispatcher's post-merge janitor engine slice."""

from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_janitor import post_merge
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    build_plan,
)


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id="x-1",
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
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
    runner = Runner(queue=[_ok(), _ok(), _err(stderr=long_error)])

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

    assert (outcome.status, outcome.stage) == ("failed", "janitor-checkout-locked")
    assert "Wait for that janitor to finish" in outcome.detail
    assert runner.calls == []
    assert journal.records == []


def test_post_merge_releases_lock_after_green(tmp_path: Path) -> None:
    plan = _plan(repo=tmp_path)
    lock = plan.janitor_checkout.with_name(f"{plan.janitor_checkout.name}.lock")
    runner = Runner(queue=[_ok() for _ in range(8)])
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
        "janitor-core-provision",
        "janitor-post-merge",
        "janitor-checkout-remove",
    ]
