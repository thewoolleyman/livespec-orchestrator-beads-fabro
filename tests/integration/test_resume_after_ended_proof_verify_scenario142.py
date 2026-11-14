"""Scenario 142: a resume after a `proof_verify` that ended with no record enters at `proof_verify`.

Work-item `bd-ib-bwwkne`. The command uses the production observation, anchor and
journal paths. The forge and factory clients are the only process boundaries
replaced here; the factory record is shaped as the Petri engine writes it, with
the per-stage results in the top-level `stages` map keyed `<node>@<visit>`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_recovery_resume_protection as resume_protection,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_resume_command as resume
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_journal import RESUME_STAGE
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


_STAGES = {
    "implement@1": "succeeded",
    "proof_capture@1": "succeeded",
    "review@1": "succeeded",
    "proof_verify@1": "failed",
    "needs_human@1": "succeeded",
}


@dataclass(kw_only=True)
class _RecoveryRunner:
    """Forge and factory answers for one journaled run that ended at `proof_verify`."""

    factory_holds_run: bool = True
    stages: dict[str, str] = field(default_factory=lambda: dict(_STAGES))
    calls: list[list[str]] = field(default_factory=list)

    def _inspect(self) -> CommandResult:
        """The Petri engine's record: results in `stages`, no per-node outcome map."""
        record = {
            "stages": {
                key: {"handler": "agent", "state": state} for key, state in self.stages.items()
            },
            "checkpoints": [{"checkpoint": {"current_node": "needs_human"}}],
        }
        return _result(stdout=json.dumps([record]))

    def run(
        self, *, argv: list[str], cwd: Path, timeout_seconds: float, **_kwargs: object
    ) -> CommandResult:
        del cwd, timeout_seconds
        self.calls.append(argv)
        if argv[:3] == ["git", "ls-remote", "origin"]:
            ref = f"refs/heads/{_BRANCH}"
            return _result(stdout=f"{_HEAD}\t{ref}\n" if ref in argv[3:] else "")
        if argv[:3] == ["gh", "pr", "list"]:
            row = {"number": _PULL_REQUEST, "state": "OPEN", "headRefOid": _HEAD}
            return _result(stdout=json.dumps([row]))
        if argv[:3] == ["gh", "pr", "view"]:
            return _result(stdout=json.dumps({"comments": [{"body": _proof_body()}]}))
        if "ps" in argv:
            runs = (
                [{"run_id": _RUN_ID, "status": {"kind": "failed"}}]
                if self.factory_holds_run
                else []
            )
            return _result(stdout=json.dumps(runs))
        return self._inspect()


def _result(*, stdout: str = "", exit_code: int = 0) -> CommandResult:
    return CommandResult(exit_code=exit_code, stdout=stdout, stderr="")


def _proof_body() -> str:
    return "\n".join(
        [
            f"Proof of Done — captured — run {_RUN_ID} — 2026-10-26T00:00:00Z",
            "",
            f"Publish-branch head: {_HEAD}",
            "",
            "## Assertion 1",
            _CRITERION,
            "Reproduced: yes.",
        ]
    )


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="Resumable published run",
        description=f"## Definition of Done\n\n- {_CRITERION}\n",
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
    monkeypatch.setattr(resume_protection, "ShellCommandRunner", lambda: runner)
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


def _resumed(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: _RecoveryRunner
) -> tuple[argparse.Namespace, dict[str, object]]:
    """Drive `resume --item` once and return the dispatched args and the journaled resume row."""
    _origin, repo = _published_repo(tmp_path=tmp_path)
    journal = _journal(repo=repo)
    dispatched = _wire_command(
        monkeypatch=monkeypatch, item=_item(), journal=journal, runner=runner
    )

    assert resume.run_resume_command(args=_args(repo=repo)) == 0

    records = read_journal_records(journal_path=journal.path)
    return dispatched[0], next(record for record in records if record["stage"] == RESUME_STAGE)


def test_scenario142_a_resume_after_an_ended_proof_verify_enters_at_proof_verify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The factory record decides `proof_verify` on the head the captured record names."""
    args, resumed = _resumed(tmp_path=tmp_path, monkeypatch=monkeypatch, runner=_RecoveryRunner())

    assert args.resume_entry_node == "proof_verify"
    assert args.resume_head == _HEAD
    assert resumed["resumed_at"] == "proof_verify"
    assert resumed["resumed_at_source"] == "factory-run-record"
    assert resumed["head"] == _HEAD


def test_scenario142_a_resume_keeps_the_verdict_fallback_when_the_factory_lost_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An authoritative not-found answer sends the `captured` record to `review`, as before."""
    runner = _RecoveryRunner(factory_holds_run=False)
    args, resumed = _resumed(tmp_path=tmp_path, monkeypatch=monkeypatch, runner=runner)

    assert args.resume_entry_node == "review"
    assert resumed["resumed_at"] == "review"
    assert resumed["resumed_at_source"] == "pull-request-latest-record"


def test_scenario142_a_run_that_did_not_end_at_proof_verify_is_not_re_entered_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the unrecorded replay in the factory record the `captured` verdict still decides."""
    stages = {key: state for key, state in _STAGES.items() if key != "proof_verify@1"}
    args, resumed = _resumed(
        tmp_path=tmp_path, monkeypatch=monkeypatch, runner=_RecoveryRunner(stages=stages)
    )

    assert args.resume_entry_node == "review"
    assert resumed["resumed_at_source"] == "pull-request-latest-record"
