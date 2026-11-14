"""Coverage for the drift judge's item-specific spend-journal seam."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._drift_run_judge import (
    _looks_like_item_class,
    drift_judge,
)


class _ClaudeRunner:
    """A Claude candidate that returns a parseable spec-stated verdict."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del argv, cwd, timeout_seconds, env, stdin
        return CommandResult(exit_code=0, stdout='{"kind":"stated"}', stderr="")


def test_the_drift_judge_forwards_an_explicit_journal_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A caller's item-specific name reaches the candidate-chain journal."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    project = tmp_path / "project"
    project.mkdir()
    _ = (project / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "acp_nodes": {
        "dod_gate": {"agent": "claude-acp", "model": "claude-opus-5", "effort": "high"}
      }
    }
  }
}
""",
        encoding="utf-8",
    )

    reply = drift_judge(
        project_root=project,
        runner=_ClaudeRunner(),
        caller="dod_governing_heading",
        journal_name="purpose:dod_governing_heading@bd-ib-m76p2n",
    )("judge this")

    assert reply == '{"kind":"stated"}'
    journal = next((home / ".claude" / "spend-journal").glob("*.jsonl"))
    header = json.loads(journal.read_text(encoding="utf-8").splitlines()[0])
    assert header["name"] == "purpose:dod_governing_heading@bd-ib-m76p2n"


def test_the_drift_judge_recognizes_the_item_class_reply_shape() -> None:
    assert _looks_like_item_class(text="feature") is True
