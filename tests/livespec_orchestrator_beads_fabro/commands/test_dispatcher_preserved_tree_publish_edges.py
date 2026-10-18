"""Every step of the preserved-tree publication that can fail, and the removals."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_publish import (
    STEP_BLOB,
    STEP_COMMIT,
    STEP_REF,
    STEP_TREE,
    PreservedTree,
    PublishFailure,
    publish_preserved_tree,
)
from livespec_orchestrator_beads_fabro.commands._fabro_run_files import RunFile, RunFiles

_BASE_COMMIT = "5d511335aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_FILES = (RunFile(path="a.py", content=b"changed\n", mode="100644"),)


@dataclass(kw_only=True)
class _StagedRunner:
    """Answer each call from `answers`, recording every argv and posted body."""

    answers: list[CommandResult]
    argvs: list[list[str]] = field(default_factory=list)
    bodies: list[object] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd
        _ = timeout_seconds
        _ = env
        self.argvs.append(list(argv))
        if stdin is not None:
            self.bodies.append(json.loads(os.pread(stdin, 1_000_000, 0).decode("utf-8")))
        index = len(self.argvs) - 1
        if index < len(self.answers):
            return self.answers[index]
        return CommandResult(exit_code=0, stdout="deadbeef\n", stderr="")


def _ok(*, stdout: str) -> CommandResult:
    return CommandResult(exit_code=0, stdout=f"{stdout}\n", stderr="")


def _published(*, runner: _StagedRunner, files: tuple[RunFile, ...]) -> object:
    return publish_preserved_tree(
        runner=runner,
        repo=Path("/nonexistent"),
        work_item_id="bd-ib-na2xvm",
        base_commit=_BASE_COMMIT,
        read=RunFiles(files=files, scope="committed", source="sandbox"),
        message="preserved tree",
    )


def test_an_unreadable_base_commit_fails_at_the_tree_step() -> None:
    runner = _StagedRunner(answers=[CommandResult(exit_code=1, stdout="", stderr="not found")])
    failed = _published(runner=runner, files=_FILES)
    assert isinstance(failed, PublishFailure)
    assert failed.step == STEP_TREE
    assert _BASE_COMMIT in failed.detail


def test_a_base_commit_read_that_named_nothing_fails_at_the_tree_step() -> None:
    runner = _StagedRunner(answers=[_ok(stdout="")])
    failed = _published(runner=runner, files=_FILES)
    assert isinstance(failed, PublishFailure)
    assert failed.step == STEP_TREE


def test_a_refused_blob_fails_at_the_blob_step_and_names_the_path() -> None:
    runner = _StagedRunner(
        answers=[_ok(stdout="basetree"), CommandResult(exit_code=1, stdout="", stderr="413")]
    )
    failed = _published(runner=runner, files=_FILES)
    assert isinstance(failed, PublishFailure)
    assert failed.step == STEP_BLOB
    assert "a.py" in failed.detail


def test_a_refused_tree_fails_at_the_tree_step_and_counts_the_files_read() -> None:
    runner = _StagedRunner(
        answers=[
            _ok(stdout="basetree"),
            _ok(stdout="blobsha"),
            CommandResult(exit_code=1, stdout="", stderr="422"),
        ]
    )
    failed = _published(runner=runner, files=_FILES)
    assert isinstance(failed, PublishFailure)
    assert failed.step == STEP_TREE
    assert "1 changed file(s)" in failed.detail


def test_a_refused_commit_fails_at_the_commit_step() -> None:
    runner = _StagedRunner(
        answers=[
            _ok(stdout="basetree"),
            _ok(stdout="blobsha"),
            _ok(stdout="treesha"),
            CommandResult(exit_code=1, stdout="", stderr="422"),
        ]
    )
    failed = _published(runner=runner, files=_FILES)
    assert isinstance(failed, PublishFailure)
    assert failed.step == STEP_COMMIT
    assert "treesha" in failed.detail


def test_a_refused_ref_fails_at_the_ref_step() -> None:
    runner = _StagedRunner(
        answers=[
            _ok(stdout="basetree"),
            _ok(stdout="blobsha"),
            _ok(stdout="treesha"),
            _ok(stdout="commitsha"),
            CommandResult(exit_code=1, stdout="", stderr="422"),
        ]
    )
    failed = _published(runner=runner, files=_FILES)
    assert isinstance(failed, PublishFailure)
    assert failed.step == STEP_REF
    assert "commitsha" in failed.detail


def test_a_removal_rides_as_a_null_sha_entry_and_posts_no_blob() -> None:
    runner = _StagedRunner(
        answers=[_ok(stdout="basetree"), _ok(stdout="treesha"), _ok(stdout="commitsha")]
    )
    published = _published(
        runner=runner,
        files=(RunFile(path="gone.py", content=None, mode="100644"),),
    )
    assert isinstance(published, PreservedTree)
    assert published.file_count == 1
    tree_body = runner.bodies[0]
    assert tree_body == {
        "base_tree": "basetree",
        "tree": [{"path": "gone.py", "mode": "100644", "type": "blob", "sha": None}],
    }
