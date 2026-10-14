"""What the staging journal record says about the base the run was staged at.

The record already named the dispatching checkout's HEAD, which was a complete
account only while that head WAS the base. Once a behind-origin checkout stages
elsewhere, a record carrying one commit cannot say which of the two it is, and
the triage question a failed pre-run push raises -- "what did this push carry?"
-- has no answer in the journal at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_source_staging as staging
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_source_refusals import pass_outcome

_HEAD = "a" * 40
_ORIGIN_HEAD = "b" * 40


@dataclass(kw_only=True)
class _Runner:
    """Answer the base probes; every other call is an uneventful success."""

    ancestor: bool

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del cwd, timeout_seconds, env, stdin
        if argv[:2] == ["git", "rev-parse"]:
            return CommandResult(exit_code=0, stdout=f"{_ORIGIN_HEAD}\n", stderr="")
        if argv[:2] == ["git", "merge-base"]:
            return CommandResult(exit_code=0 if self.ancestor else 1, stdout="", stderr="")
        return CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _plan(*, root: Path) -> DispatchPlan:
    return build_plan(
        repo=root,
        work_item_id="bd-ib-xavjhz",
        workflow_toml=root / "workflow.toml",
        goal_file=root / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=root / "janitor",
        default_branch="master",
    )


@pytest.mark.parametrize("ancestor", [True, False])
def test_the_staged_record_names_the_checkout_head_and_the_fetched_origin_head(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ancestor: bool
) -> None:
    monkeypatch.setattr(
        staging,
        "source_checkout_preflight",
        lambda **_: pass_outcome(
            head=_HEAD, origin_refs=("origin/master",), origin_ref="origin/master"
        ),
    )
    journal = _Journal()
    runner = staging.SourceStagingRunner(
        inner=_Runner(ancestor=ancestor),
        plan=_plan(root=tmp_path),
        journal=journal,
        worktree_root=tmp_path / ".worktrees",
    )
    assert runner.run(argv=["fabro", "run"], cwd=tmp_path, timeout_seconds=30).exit_code == 0
    staged = next(row for row in journal.records if row["stage"] == "source-checkout-stage")
    assert staged["head"] == _HEAD
    assert staged.get("default_branch_head") == _ORIGIN_HEAD
    assert staged.get("staged_at") == (_ORIGIN_HEAD if ancestor else _HEAD)
