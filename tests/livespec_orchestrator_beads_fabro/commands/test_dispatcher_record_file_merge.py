"""The materialized record-file merger resolves only declared additive records."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_merge import (
    RECORD_FILE_MERGE_PROGRAM_FILENAME,
    record_file_merge_program_source,
)


def _git(*argv: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *argv],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
        },
    )


def _commit(*, repo: Path, message: str) -> None:
    _git("add", ".", cwd=repo)
    _git("commit", "--quiet", "-m", message, cwd=repo)


def test_the_materialized_program_merges_declared_json_entries_in_branch_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "--quiet", "-b", "master", cwd=repo)
    (repo / ".livespec.jsonc").write_text(
        """{
  // the program reads the committed declaration, not a test-only argument
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "record_files": [{
        "path": "record.json",
        "format": "json-array",
        "key": ["id"]
      }]
    }
  }
}
""",
        encoding="utf-8",
    )
    (repo / "record.json").write_text('[{"id": "base"}]\n', encoding="utf-8")
    _commit(repo=repo, message="seed")
    _git("switch", "--quiet", "-c", "run", cwd=repo)
    (repo / "record.json").write_text('[{"id": "base"}, {"id": "run"}]\n', encoding="utf-8")
    _commit(repo=repo, message="run record")
    _git("switch", "--quiet", "master", cwd=repo)
    (repo / "record.json").write_text('[{"id": "base"}, {"id": "default"}]\n', encoding="utf-8")
    _commit(repo=repo, message="default record")
    _git("switch", "--quiet", "run", cwd=repo)

    conflicted = _git("rebase", "master", cwd=repo, check=False)
    assert conflicted.returncode != 0
    program = tmp_path / RECORD_FILE_MERGE_PROGRAM_FILENAME
    program.write_text(record_file_merge_program_source(), encoding="utf-8")
    namespace: dict[str, object] = {"__name__": "record_file_merge_under_test"}
    exec(program.read_text(encoding="utf-8"), namespace)  # noqa: S102
    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "argv", [str(program), "--mode", "rebase", "record.json"])
    merged = namespace["main"]()

    assert merged == 0
    assert (
        "LIVESPEC_RECORD_FILE_MERGED: path=record.json format=json-array" in capsys.readouterr().err
    )
    _git("add", "record.json", cwd=repo)
    _git("-c", "core.editor=true", "rebase", "--continue", cwd=repo)
    assert json.loads((repo / "record.json").read_text(encoding="utf-8")) == [
        {"id": "base"},
        {"id": "default"},
        {"id": "run"},
    ]
