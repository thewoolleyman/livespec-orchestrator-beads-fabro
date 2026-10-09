"""Scenario 166: reconcile terminal success separately from run-store loss.

The incident shape is preserved here rather than simplified to a generic failed
run: the engine's conclusion says the worker exited before persisting a terminal
event, while its newest checkpoint records the final successful workflow stage
selecting the configured green exit.  The forge seam then reports the pull
request published from that checkpoint's exact commit.

Every case drives ``run_dispatch`` itself.  Only the engine, forge, and checkout
commands leave the process, so those transports are controlled; terminal
classification, pull-request reconciliation, merge handling, and journaling are
production code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_terminal_publication
from livespec_orchestrator_beads_fabro.commands._dispatcher_current_merge_hold import (
    CurrentMergeHold,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
    DispatchOutcome,
    FabroRunResult,
    JournalWriter,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    build_plan,
)

_RUN_ID = "01PROOFTERMINAL"
_HEAD = "a" * 40
_MERGE_SHA = "c" * 40
_REPOSITORY = "thewoolleyman/proof-repo"
_WORKER_EXIT_MESSAGE = "Worker exited before emitting a terminal run event: exit status: 0"
_REPO_ROOT = Path(__file__).parents[2]
_WORKFLOW = _REPO_ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.toml"
_SUCCESSFUL_NODES = (
    "start",
    "dod_gate",
    "implement",
    "implementation_diff",
    "janitor",
    "publish_draft",
    "proof_capture",
    "review",
    "proof_verify",
    "pr",
    "verify_pr",
)
_CONFIG = '{"livespec-orchestrator-beads-fabro":{"compat":{"pinned":"master"}}}'


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _Launcher:
    stderr: str = _WORKER_EXIT_MESSAGE

    def launch(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        journal: JournalWriter,
    ) -> FabroRunResult:
        _ = (plan, runner, journal)
        return FabroRunResult(
            command=CommandResult(
                exit_code=1,
                stdout=f"Run: {_RUN_ID}\n",
                stderr=self.stderr,
            ),
            run_id=_RUN_ID,
        )


@dataclass(kw_only=True)
class _Runner:
    plan: DispatchPlan
    inspect_record: dict[str, object] = field(default_factory=dict)
    pr_overrides: dict[str, object] = field(default_factory=dict)
    pr_available: bool = True
    repository_slug: str = _REPOSITORY
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
        _ = (timeout_seconds, env, stdin)
        self.calls.append((argv, cwd))
        if argv[:2] == ["synthetic-fabro", "inspect"]:
            return _ok(stdout=json.dumps([self.inspect_record]))
        if argv[:3] == ["gh", "repo", "view"]:
            return _ok(stdout=json.dumps({"nameWithOwner": self.repository_slug}))
        if argv[:3] == ["gh", "pr", "view"]:
            if not self.pr_available:
                return CommandResult(exit_code=1, stdout="", stderr="not found")
            return _ok(
                stdout=json.dumps(
                    {
                        **_pull_request(plan=self.plan),
                        **self.pr_overrides,
                    }
                )
            )
        if argv[:2] == ["gh", "api"]:
            return _ok(stdout=json.dumps([{"number": 41}]))
        return _ok()


def _ok(*, stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _held_merge(*, repo: Path, work_item_id: str) -> CurrentMergeHold:
    _ = (repo, work_item_id)
    return "held"


def _plan(*, root: Path) -> DispatchPlan:
    root.mkdir(parents=True, exist_ok=True)
    repo = root / "repo"
    repo.mkdir()
    return build_plan(
        repo=repo,
        work_item_id="proof-terminal",
        workflow_toml=_WORKFLOW,
        goal_file=root / "goal.md",
        fabro_bin="synthetic-fabro",
        janitor=("mise", "exec", "--", "just", "check"),
        janitor_checkout=root / "janitor",
        config_text=_CONFIG,
        default_branch="master",
    )


def _successful_checkpoint(*, completed_exit: bool = False) -> dict[str, object]:
    completed = [*_SUCCESSFUL_NODES, "exit"] if completed_exit else list(_SUCCESSFUL_NODES)
    outcomes = {node: {"status": "succeeded"} for node in completed}
    return {
        "timestamp": "2026-10-09T03:15:20.178706428Z",
        "current_node": "exit" if completed_exit else "verify_pr",
        "next_node_id": None if completed_exit else "exit",
        "completed_nodes": completed,
        "git_commit_sha": _HEAD,
        "node_outcomes": outcomes,
    }


def _failed_inspect(
    *,
    checkpoint: dict[str, object] | None,
    run_id: str = _RUN_ID,
    status_kind: str = "failed",
    failure_message: str = _WORKER_EXIT_MESSAGE,
    earlier_checkpoints: tuple[dict[str, object], ...] = (),
) -> dict[str, object]:
    record: dict[str, object] = {
        "run_id": run_id,
        "status": {"kind": status_kind, "reason": "terminated"},
        "conclusion": {
            "status": status_kind,
            "failure": {
                "reason": "terminated",
                "detail": {
                    "category": "deterministic",
                    "message": failure_message,
                },
            },
        },
    }
    if earlier_checkpoints:
        record["checkpoints"] = [{"checkpoint": item} for item in earlier_checkpoints]
    if checkpoint is not None:
        record["checkpoint"] = checkpoint
    return record


def _pull_request(*, plan: DispatchPlan) -> dict[str, object]:
    return {
        "number": 41,
        "state": "MERGED",
        "headRefName": plan.branch,
        "headRefOid": _HEAD,
        "headRepository": {"nameWithOwner": _REPOSITORY},
        "mergeCommit": {"oid": _MERGE_SHA},
        "autoMergeRequest": None,
        "mergeStateStatus": "CLEAN",
        "statusCheckRollup": [],
        "additions": 1,
        "deletions": 1,
    }


def _dispatch(
    *,
    root: Path,
    inspect_record: dict[str, object] | None = None,
    pr_overrides: dict[str, object] | None = None,
    pr_available: bool = True,
    repository_slug: str = _REPOSITORY,
    launcher_stderr: str = _WORKER_EXIT_MESSAGE,
) -> tuple[DispatchOutcome, _Journal, _Runner]:
    plan = _plan(root=root)
    runner = _Runner(
        plan=plan,
        inspect_record=(
            _failed_inspect(checkpoint=_successful_checkpoint())
            if inspect_record is None
            else inspect_record
        ),
        pr_overrides=pr_overrides or {},
        pr_available=pr_available,
        repository_slug=repository_slug,
    )
    journal = _Journal()
    outcome = run_dispatch(
        plan=plan,
        runner=runner,
        journal=journal,
        sleep=lambda _seconds: None,
        poll=PollPolicy(attempts=1, interval_seconds=0),
        fabro_launcher=_Launcher(stderr=launcher_stderr),
    )
    return outcome, journal, runner


def test_store_loss_after_success_continues_the_normal_merge_reconciliation(
    tmp_path: Path,
) -> None:
    outcome, _journal, runner = _dispatch(root=tmp_path)

    assert (outcome.status, outcome.stage, outcome.pr_number, outcome.merge_sha) == (
        "green",
        "done",
        41,
        _MERGE_SHA,
    )
    assert any(argv[:3] == ["gh", "pr", "view"] for argv, _cwd in runner.calls)


def test_publication_must_match_the_checkpoint_head_and_reports_merge_state(
    tmp_path: Path,
) -> None:
    matching, _journal, _runner = _dispatch(
        root=tmp_path / "matching",
    )
    stale, _journal, _runner = _dispatch(
        root=tmp_path / "stale",
        pr_overrides={"headRefOid": "b" * 40},
    )

    assert (matching.status, matching.stage, matching.pr_number, matching.merge_sha) == (
        "green",
        "done",
        41,
        _MERGE_SHA,
    )
    assert (stale.status, stale.stage, stale.pr_number) == (
        "failed",
        "fabro-run",
        None,
    )


def test_journal_separates_conflict_checkpoint_publication_and_classification(
    tmp_path: Path,
) -> None:
    outcome, journal, _runner = _dispatch(root=tmp_path)
    records = {str(record.get("stage")): record for record in journal.records}

    assert outcome.status == "green"
    assert {
        "fabro-terminal-conflict",
        "fabro-terminal-checkpoint",
        "fabro-terminal-publication",
        "fabro-terminal-classification",
    }.issubset(records)
    assert records["fabro-terminal-conflict"] == {
        "stage": "fabro-terminal-conflict",
        "work_item_id": "proof-terminal",
        "run_id": _RUN_ID,
        "engine_status": "failed",
        "failure_cause": _WORKER_EXIT_MESSAGE,
        "failure_category": "deterministic",
    }
    assert records["fabro-terminal-checkpoint"] == {
        "stage": "fabro-terminal-checkpoint",
        "work_item_id": "proof-terminal",
        "run_id": _RUN_ID,
        "timestamp": "2026-10-09T03:15:20.178706428Z",
        "current_node": "verify_pr",
        "next_node_id": "exit",
        "commit_sha": _HEAD,
    }
    assert records["fabro-terminal-publication"] == {
        "stage": "fabro-terminal-publication",
        "work_item_id": "proof-terminal",
        "run_id": _RUN_ID,
        "pr_number": 41,
        "state": "MERGED",
        "branch": "feat/proof-terminal",
        "head": _HEAD,
        "repository": "thewoolleyman/proof-repo",
    }
    assert records["fabro-terminal-classification"] == {
        "stage": "fabro-terminal-classification",
        "work_item_id": "proof-terminal",
        "run_id": _RUN_ID,
        "classification": "successful-workflow",
        "evidence": "checkpoint+publication",
    }


def test_scenario_166_authenticates_terminal_success_and_preserves_non_green_controls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final_stage, _journal, _runner = _dispatch(root=tmp_path / "final-stage")
    completed_exit, _journal, _runner = _dispatch(
        root=tmp_path / "completed-exit",
        inspect_record=_failed_inspect(checkpoint=_successful_checkpoint(completed_exit=True)),
    )

    assert (final_stage.status, final_stage.stage, final_stage.pr_number) == (
        "green",
        "done",
        41,
    )
    assert (completed_exit.status, completed_exit.stage, completed_exit.pr_number) == (
        "green",
        "done",
        41,
    )

    intermediate = _successful_checkpoint()
    intermediate.update(current_node="pr", next_node_id="verify_pr")
    failed_required = _successful_checkpoint()
    failed_required["node_outcomes"] = {
        **{node: {"status": "succeeded"} for node in _SUCCESSFUL_NODES},
        "review": {"status": "failed"},
    }
    needs_human = _successful_checkpoint()
    needs_human.update(current_node="needs_human", next_node_id=None)
    cases: tuple[tuple[str, dict[str, object], dict[str, object], bool, str], ...] = (
        ("missing-checkpoint", _failed_inspect(checkpoint=None), {}, True, _REPOSITORY),
        (
            "other-run",
            _failed_inspect(checkpoint=_successful_checkpoint(), run_id="01OTHER"),
            {},
            True,
            _REPOSITORY,
        ),
        (
            "earlier-success",
            _failed_inspect(
                checkpoint=intermediate,
                earlier_checkpoints=(_successful_checkpoint(),),
            ),
            {},
            True,
            _REPOSITORY,
        ),
        ("intermediate", _failed_inspect(checkpoint=intermediate), {}, True, _REPOSITORY),
        ("required-failed", _failed_inspect(checkpoint=failed_required), {}, True, _REPOSITORY),
        (
            "cancelled",
            _failed_inspect(
                checkpoint=_successful_checkpoint(),
                status_kind="cancelled",
                failure_message="cancelled by operator",
            ),
            {},
            True,
            _REPOSITORY,
        ),
        ("needs-human", _failed_inspect(checkpoint=needs_human), {}, True, _REPOSITORY),
        (
            "missing-pr",
            _failed_inspect(checkpoint=_successful_checkpoint()),
            {},
            False,
            _REPOSITORY,
        ),
        (
            "wrong-head",
            _failed_inspect(checkpoint=_successful_checkpoint()),
            {"headRefOid": "b" * 40},
            True,
            _REPOSITORY,
        ),
        (
            "wrong-branch",
            _failed_inspect(checkpoint=_successful_checkpoint()),
            {"headRefName": "feat/unrelated"},
            True,
            _REPOSITORY,
        ),
        (
            "wrong-repository",
            _failed_inspect(checkpoint=_successful_checkpoint()),
            {},
            True,
            "someone-else/proof-repo",
        ),
        (
            "closed-unmerged",
            _failed_inspect(checkpoint=_successful_checkpoint()),
            {"state": "CLOSED", "mergeCommit": None},
            True,
            _REPOSITORY,
        ),
        (
            "worker-nonzero",
            _failed_inspect(
                checkpoint=_successful_checkpoint(),
                failure_message="Worker exited before emitting a terminal run event: exit status: 2",
            ),
            {},
            True,
            _REPOSITORY,
        ),
    )
    for name, inspect_record, pr_overrides, pr_available, repository_slug in cases:
        outcome, journal, _runner = _dispatch(
            root=tmp_path / name,
            inspect_record=inspect_record,
            pr_overrides=pr_overrides,
            pr_available=pr_available,
            repository_slug=repository_slug,
        )
        assert (outcome.status, outcome.stage, outcome.pr_number) == (
            "failed",
            "fabro-run",
            None,
        ), name
        assert not any(
            record.get("stage") == "fabro-terminal-classification" for record in journal.records
        ), name

    monkeypatch.setattr(
        _dispatcher_terminal_publication,
        "read_current_merge_hold",
        _held_merge,
    )
    held, held_journal, _runner = _dispatch(
        root=tmp_path / "held",
        pr_overrides={"state": "OPEN", "mergeCommit": None},
    )
    assert (held.status, held.stage, held.pr_number, held.merge_sha) == (
        "green",
        "pr",
        41,
        None,
    )
    assert any(
        record.get("stage") == "fabro-terminal-classification" for record in held_journal.records
    )
