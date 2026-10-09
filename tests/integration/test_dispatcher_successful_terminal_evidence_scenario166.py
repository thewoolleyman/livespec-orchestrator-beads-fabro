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

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
    FabroRunResult,
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
    def launch(
        self,
        *,
        plan: DispatchPlan,
        runner: _Runner,
        journal: _Journal,
    ) -> FabroRunResult:
        _ = (plan, runner, journal)
        return FabroRunResult(
            command=CommandResult(
                exit_code=1,
                stdout=f"Run: {_RUN_ID}\n",
                stderr=_WORKER_EXIT_MESSAGE,
            ),
            run_id=_RUN_ID,
        )


@dataclass(kw_only=True)
class _Runner:
    plan: DispatchPlan
    pr_overrides: dict[str, object] = field(default_factory=dict)
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
            return _ok(stdout=json.dumps([_failed_inspect()]))
        if argv[:3] == ["gh", "pr", "view"]:
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


def _failed_inspect() -> dict[str, object]:
    return {
        "run_id": _RUN_ID,
        "status": {"kind": "failed", "reason": "terminated"},
        "conclusion": {
            "status": "failed",
            "failure": {
                "reason": "terminated",
                "detail": {
                    "category": "deterministic",
                    "message": _WORKER_EXIT_MESSAGE,
                },
            },
        },
        "checkpoint": {
            "timestamp": "2026-10-09T03:15:20.178706428Z",
            "current_node": "verify_pr",
            "next_node_id": "exit",
            "completed_nodes": list(_SUCCESSFUL_NODES),
            "git_commit_sha": _HEAD,
            "node_outcomes": {node: {"status": "succeeded"} for node in _SUCCESSFUL_NODES},
        },
    }


def _pull_request(*, plan: DispatchPlan) -> dict[str, object]:
    return {
        "number": 41,
        "state": "MERGED",
        "headRefName": plan.branch,
        "headRefOid": _HEAD,
        "headRepository": {"nameWithOwner": "thewoolleyman/proof-repo"},
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
    pr_overrides: dict[str, object] | None = None,
) -> tuple[DispatchOutcome, _Journal, _Runner]:
    plan = _plan(root=root)
    runner = _Runner(plan=plan, pr_overrides=pr_overrides or {})
    journal = _Journal()
    outcome = run_dispatch(
        plan=plan,
        runner=runner,
        journal=journal,
        sleep=lambda _seconds: None,
        poll=PollPolicy(attempts=1, interval_seconds=0),
        fabro_launcher=_Launcher(),
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
