"""Published-run recovery journeys for Scenarios 142 and 143.

The command uses the production observation, anchor and journal paths.  The
forge and factory clients are the only process boundaries replaced here, and the
test double keeps their published pull-request and dead-run records shaped as
the command reads them.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_resume_command as resume
from livespec_orchestrator_beads_fabro.commands import _dispatcher_resume_observation as observation
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_journal import RESUME_STAGE
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import (
    PR_STATE_CLOSED,
    PR_STATE_MERGED,
)
from livespec_orchestrator_beads_fabro.types import WorkItem
from returns.io import IO
from returns.result import Success

_ITEM_ID = "bd-ib-hfi52b"
_BRANCH = f"feat/{_ITEM_ID}"
_RUN_ID = "01M5RECOVERY00000000000000"
_HEAD = "a" * 40
_MOVED_HEAD = "b" * 40
_PULL_REQUEST = 142
_CRITERION = "The published draft resumes at its first unfinished stage."
_GIT_ENV = {
    "GIT_AUTHOR_NAME": "Integration Test",
    "GIT_AUTHOR_EMAIL": "integration@example.invalid",
    "GIT_COMMITTER_NAME": "Integration Test",
    "GIT_COMMITTER_EMAIL": "integration@example.invalid",
}


@dataclass(kw_only=True)
class _RecoveryRunner:
    """Forge and factory answers for one journaled published run."""

    state: str = "OPEN"
    head: str = _HEAD
    run_status: str = "completed"
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self, *, argv: list[str], cwd: Path, timeout_seconds: float, **_kwargs: object
    ) -> CommandResult:
        del cwd, timeout_seconds
        self.calls.append(argv)
        if argv[:3] == ["gh", "pr", "list"]:
            row = {"number": _PULL_REQUEST, "state": self.state, "headRefOid": self.head}
            return _result(stdout=json.dumps([row]))
        if argv[:3] == ["gh", "pr", "view"]:
            return _result(stdout=json.dumps({"comments": [{"body": _proof_body()}]}))
        if "ps" in argv:
            run = {"run_id": _RUN_ID, "status": {"kind": self.run_status}}
            return _result(stdout=json.dumps([run]))
        if "inspect" in argv:
            record = {"checkpoints": [{"checkpoint": {"next_node_id": "implement"}}]}
            return _result(stdout=json.dumps([record]))
        raise AssertionError(f"unexpected recovery command: {argv}")


def _result(*, stdout: str = "", exit_code: int = 0) -> CommandResult:
    return CommandResult(exit_code=exit_code, stdout=stdout, stderr="")


def _proof_body() -> str:
    return "\n".join(
        [
            f"Proof of Done — verified — run {_RUN_ID} — 2026-10-26T00:00:00Z",
            "",
            f"Publish-branch head: {_HEAD}",
            "",
            "## Assertion 1",
            _CRITERION,
            "Reproduced: yes.",
        ]
    )


def _item() -> WorkItem:
    return _item_with()


def _item_with(*, status: str = "ready", criterion: str = _CRITERION) -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status=status,
        title="Resumable published run",
        description=f"## Definition of Done\n\n- {criterion}\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-26T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _git(*argv: str, cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *argv], cwd=cwd, check=True, capture_output=True, env=_GIT_ENV, text=True
    )
    return completed.stdout.strip()


def _published_repo(*, tmp_path: Path) -> tuple[Path, Path]:
    """A real origin carrying the draft branch whose state the command must not alter."""
    origin = tmp_path / "origin.git"
    repo = tmp_path / "repo"
    _ = _git("init", "--bare", str(origin), cwd=tmp_path)
    _ = _git("init", str(repo), cwd=tmp_path)
    _ = _git("config", "user.name", "Integration Test", cwd=repo)
    _ = _git("config", "user.email", "integration@example.invalid", cwd=repo)
    (repo / "published.txt").write_text("published\n", encoding="utf-8")
    _ = _git("add", "published.txt", cwd=repo)
    _ = _git("commit", "-m", "published draft", cwd=repo)
    _ = _git("branch", "-M", _BRANCH, cwd=repo)
    _ = _git("remote", "add", "origin", str(origin), cwd=repo)
    _ = _git("push", "origin", f"HEAD:refs/heads/{_BRANCH}", cwd=repo)
    return origin, repo


def _args(*, repo: Path) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(repo),
        item=_ITEM_ID,
        journal=str(repo / "tmp" / "journal.jsonl"),
        fabro_bin="fabro",
        workflow=None,
        workflow_name=None,
        as_json=False,
    )


def _journal(*, repo: Path) -> JournalFile:
    journal = JournalFile(path=repo / "tmp" / "journal.jsonl")
    journal.append(
        record={
            "stage": "dispatch-id",
            "work_item_id": _ITEM_ID,
            "run_id": _RUN_ID,
            "dispatch_id": "dispatch-recovery",
            "workflow_name": "implement-work-item",
        }
    )
    return journal


def _wire_command(
    *,
    monkeypatch: pytest.MonkeyPatch,
    item: WorkItem,
    journal: JournalFile,
    runner: _RecoveryRunner,
) -> list[argparse.Namespace]:
    dispatched: list[argparse.Namespace] = []
    monkeypatch.setattr(resume, "dispatch_preamble", lambda **_kwargs: (None, None))
    monkeypatch.setattr(resume, "arm_otel_egress", lambda **_kwargs: None)
    monkeypatch.setattr(resume, "prepare", lambda **_kwargs: ([item], journal))
    monkeypatch.setattr(
        resume, "apply_factory_size_dispatch_entry", lambda **_kwargs: Success(IO(()))
    )
    monkeypatch.setattr(resume, "ShellCommandRunner", lambda: runner)
    monkeypatch.setattr(resume, "pre_dispatch_wall_exit", lambda **_kwargs: None)
    monkeypatch.setattr(resume, "dispatch_tail_exit", lambda **_kwargs: 0)

    def _dispatch(**kwargs: object) -> DispatchOutcome:
        dispatched.append(kwargs["args"])
        return DispatchOutcome(
            work_item_id=_ITEM_ID,
            status="green",
            stage="done",
            pr_number=_PULL_REQUEST,
            merge_sha=None,
            detail="resumed",
        )

    monkeypatch.setattr(resume, "_admit_and_dispatch_resume", _dispatch)
    return dispatched


def test_scenario142_resumes_a_journaled_dead_run_from_its_published_draft_pr_at_first_unfinished_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario 142: a dead published run resumes at the factory's unfinished node."""
    _origin, repo = _published_repo(tmp_path=tmp_path)
    journal = _journal(repo=repo)
    dispatched = _wire_command(
        monkeypatch=monkeypatch, item=_item(), journal=journal, runner=_RecoveryRunner()
    )

    assert resume.run_resume_command(args=_args(repo=repo)) == 0

    assert dispatched[0].resume_entry_node == "implement"
    assert dispatched[0].resume_head == _HEAD
    assert dispatched[0].workflow_name == "implement-work-item"
    records = read_journal_records(journal_path=journal.path)
    resumed = next(record for record in records if record["stage"] == RESUME_STAGE)
    assert resumed == {
        **resumed,
        "work_item_id": _ITEM_ID,
        "earlier_run_ids": [_RUN_ID, "dispatch-recovery"],
        "pull_request": _PULL_REQUEST,
        "head": _HEAD,
        "resumed_at": "implement",
        "resumed_at_source": "factory-run-record",
    }


@pytest.mark.parametrize(
    ("case", "state", "head", "run_status", "item_status", "criterion", "runner_updates"),
    [
        ("not-ready", "OPEN", _HEAD, "completed", "backlog", _CRITERION, {}),
        ("moved-head", "OPEN", _MOVED_HEAD, "completed", "ready", _CRITERION, {}),
        (
            "changed-definition-of-done",
            "OPEN",
            _HEAD,
            "completed",
            "ready",
            "A newly groomed assertion.",
            {},
        ),
        ("live-run", "OPEN", _HEAD, "running", "ready", _CRITERION, {}),
        ("live-lock", "OPEN", _HEAD, "completed", "ready", _CRITERION, {"live_lock": True}),
        ("closed-pr", PR_STATE_CLOSED, _HEAD, "completed", "ready", _CRITERION, {}),
        ("merged-pr", PR_STATE_MERGED, _HEAD, "completed", "ready", _CRITERION, {}),
        (
            "nothing-to-resume",
            "OPEN",
            _HEAD,
            "completed",
            "ready",
            _CRITERION,
            {"has_pull_request": False},
        ),
        ("third-resume", "OPEN", _HEAD, "completed", "ready", _CRITERION, {"earlier_resumes": 2}),
        (
            "unobservable-forge",
            "OPEN",
            _HEAD,
            "completed",
            "ready",
            _CRITERION,
            {"forge_observed": False},
        ),
        (
            "unobservable-factory",
            "OPEN",
            _HEAD,
            "completed",
            "ready",
            _CRITERION,
            {"factory_observed": False},
        ),
        (
            "unobservable-pull-request-head",
            "OPEN",
            _HEAD,
            "completed",
            "ready",
            _CRITERION,
            {"pull_request_head_observed": False},
        ),
        (
            "unreadable-proof-records",
            "OPEN",
            _HEAD,
            "completed",
            "ready",
            _CRITERION,
            {"records_observed": False},
        ),
        (
            "headless-proof-record",
            "OPEN",
            _HEAD,
            "completed",
            "ready",
            _CRITERION,
            {"has_anchor": False},
        ),
    ],
)
def test_scenario143_every_resume_refusal_exits_before_a_run_and_leaves_branch_and_pr_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    case: str,
    state: str,
    head: str,
    run_status: str,
    item_status: str,
    criterion: str,
    runner_updates: dict[str, object],
) -> None:
    """Scenario 143: each recovery mismatch declines before launch or ref mutation."""
    origin, repo = _published_repo(tmp_path=tmp_path)
    before_branch = _git("--git-dir", str(origin), "rev-parse", f"refs/heads/{_BRANCH}", cwd=repo)
    journal = _journal(repo=repo)
    runner = _RecoveryRunner(state=state, head=head, run_status=run_status)
    for attribute, value in runner_updates.items():
        setattr(runner, attribute, value)
    if runner_updates.get("earlier_resumes"):
        for index in range(int(runner_updates["earlier_resumes"])):
            journal.append(
                record={
                    "stage": RESUME_STAGE,
                    "work_item_id": _ITEM_ID,
                    "earlier_run_ids": [f"earlier-{index}"],
                    "pull_request": _PULL_REQUEST,
                }
            )
            journal.append(
                record={"stage": "fabro-run", "work_item_id": _ITEM_ID, "run_id": f"run-{index}"}
            )
    if runner_updates.get("live_lock"):
        monkeypatch.setattr(
            observation,
            "live_dispatch_lock",
            lambda **_kwargs: type("Lock", (), {"started_at_epoch": time.time() - 10})(),
        )
    dispatched = _wire_command(
        monkeypatch=monkeypatch,
        item=_item_with(status=item_status, criterion=criterion),
        journal=journal,
        runner=runner,
    )
    before_pull_request = (runner.state, runner.head)

    assert resume.run_resume_command(args=_args(repo=repo)) == 3

    assert not dispatched
    assert (
        _git("--git-dir", str(origin), "rev-parse", f"refs/heads/{_BRANCH}", cwd=repo)
        == before_branch
    )
    assert (runner.state, runner.head) == before_pull_request, case
    assert not [
        record
        for record in read_journal_records(journal_path=journal.path)
        if record["stage"] == RESUME_STAGE
    ]
    assert "ERROR: resume refused" in capsys.readouterr().err


def test_recovery_runner_rejects_an_unrecognized_command(tmp_path: Path) -> None:
    """The recovery fake fails loudly if the command grows an unmodeled boundary."""
    with pytest.raises(AssertionError, match="unexpected recovery command"):
        _RecoveryRunner().run(argv=["unexpected"], cwd=tmp_path, timeout_seconds=1)
