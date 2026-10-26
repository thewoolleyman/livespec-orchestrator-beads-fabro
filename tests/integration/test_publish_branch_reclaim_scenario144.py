"""The real-origin stale-publish-branch recovery journey for Scenario 144."""

from __future__ import annotations

import argparse
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_precondition import (
    publish_branch_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publish_branch_preserve import (
    preserved_publish_ref,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publish_branch_reclaim import (
    PUBLISH_BRANCH_RECLAIM_STAGE,
    reclaim_stale_publish_branch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)

_ITEM_ID = "bd-ib-hfi52b"
_RUN_ID = "01M5RECLAIM000000000000000"
_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "Integration Test",
    "GIT_AUTHOR_EMAIL": "integration@example.invalid",
    "GIT_COMMITTER_NAME": "Integration Test",
    "GIT_COMMITTER_EMAIL": "integration@example.invalid",
}


def _git(*argv: str, cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *argv], cwd=cwd, check=True, capture_output=True, env=_GIT_ENV, text=True
    )
    return completed.stdout.strip()


@dataclass(kw_only=True)
class _OriginRunner:
    """Runs origin reads for real and translates the forge ref API onto that origin."""

    origin: Path
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self, *, argv: list[str], cwd: Path, timeout_seconds: float, **_kwargs: object
    ) -> CommandResult:
        del timeout_seconds
        self.calls.append(argv)
        if argv[:2] == ["git", "ls-remote"]:
            completed = subprocess.run(
                argv, check=False, cwd=cwd, capture_output=True, env=_GIT_ENV, text=True
            )
            return CommandResult(
                exit_code=completed.returncode, stdout=completed.stdout, stderr=completed.stderr
            )
        if argv[:4] == ["fabro", "ps", "-a", "--json"]:
            return CommandResult(exit_code=0, stdout="[]", stderr="")
        if argv[:4] == ["gh", "api", "--method", "POST"]:
            fields = [value for value in argv if value.startswith(("ref=", "sha="))]
            ref = next(value.removeprefix("ref=") for value in fields if value.startswith("ref="))
            sha = next(value.removeprefix("sha=") for value in fields if value.startswith("sha="))
            _ = _git("--git-dir", str(self.origin), "update-ref", ref, sha, cwd=cwd)
            return CommandResult(exit_code=0, stdout="", stderr="")
        if argv[:4] == ["gh", "api", "--method", "DELETE"]:
            endpoint = argv[-1]
            ref = "refs/" + endpoint.partition("/git/refs/")[2]
            _ = _git("--git-dir", str(self.origin), "update-ref", "-d", ref, cwd=cwd)
            return CommandResult(exit_code=0, stdout="", stderr="")
        raise AssertionError(f"unexpected reclaim command: {argv}")


def _world(*, tmp_path: Path) -> tuple[Path, Path, str]:
    origin = tmp_path / "origin.git"
    repo = tmp_path / "repo"
    branch = publish_branch_for(work_item_id=_ITEM_ID)
    _ = _git("init", "--bare", str(origin), cwd=tmp_path)
    _ = _git("init", str(repo), cwd=tmp_path)
    _ = _git("config", "user.name", "Integration Test", cwd=repo)
    _ = _git("config", "user.email", "integration@example.invalid", cwd=repo)
    (repo / "dead-run.txt").write_text("published by dead run\n", encoding="utf-8")
    _ = _git("add", "dead-run.txt", cwd=repo)
    _ = _git("commit", "-m", "dead publish", cwd=repo)
    head = _git("rev-parse", "HEAD", cwd=repo)
    _ = _git("remote", "add", "origin", str(origin), cwd=repo)
    _ = _git("push", "origin", f"HEAD:refs/heads/{branch}", cwd=repo)
    return origin, repo, head


def test_scenario144_reclaims_a_dead_publish_branch_on_a_real_origin_and_records_its_preservation(
    tmp_path: Path,
) -> None:
    """Scenario 144: preserve first, delete second, then permit a plain re-dispatch."""
    origin, repo, dead_head = _world(tmp_path=tmp_path)
    branch = publish_branch_for(work_item_id=_ITEM_ID)
    journal = JournalFile(path=repo / "tmp" / "journal.jsonl")
    journal.append(record={"stage": "dispatch-id", "work_item_id": _ITEM_ID, "run_id": _RUN_ID})
    runner = _OriginRunner(origin=origin)
    args = argparse.Namespace(fabro_bin="fabro")

    reclaim_stale_publish_branch(
        args=args,
        repo=repo,
        work_item_id=_ITEM_ID,
        journal=journal,
        journal_path=journal.path,
        runner=runner,
    )

    preserved = preserved_publish_ref(work_item_id=_ITEM_ID, head=dead_head)
    assert _git("--git-dir", str(origin), "rev-parse", preserved, cwd=repo) == dead_head
    absent = subprocess.run(
        [
            "git",
            "--git-dir",
            str(origin),
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{branch}",
        ],
        check=False,
        env=_GIT_ENV,
    )
    assert absent.returncode == 1
    record = next(
        row
        for row in read_journal_records(journal_path=journal.path)
        if row["stage"] == PUBLISH_BRANCH_RECLAIM_STAGE
    )
    assert record["preserved_ref"] == preserved
    assert record["head"] == dead_head

    (repo / "redispatch.txt").write_text("new dispatch may publish\n", encoding="utf-8")
    _ = _git("add", "redispatch.txt", cwd=repo)
    _ = _git("commit", "-m", "plain redispatch", cwd=repo)
    new_head = _git("rev-parse", "HEAD", cwd=repo)
    _ = _git("push", "origin", f"HEAD:refs/heads/{branch}", cwd=repo)
    assert _git("--git-dir", str(origin), "rev-parse", f"refs/heads/{branch}", cwd=repo) == new_head


def test_reclaim_runner_rejects_an_unrecognized_command(tmp_path: Path) -> None:
    """The reclaim fake fails loudly if the production command grows a new boundary."""
    with pytest.raises(AssertionError, match="unexpected reclaim command"):
        _OriginRunner(origin=tmp_path).run(argv=["unexpected"], cwd=tmp_path, timeout_seconds=1)
