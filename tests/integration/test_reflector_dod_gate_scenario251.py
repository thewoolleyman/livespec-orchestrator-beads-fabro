"""Integration-tier acceptance for Scenario 251's reflector candidate chain.

Exercises the out-of-band reflector through its public entry point over a real
governed-repository configuration.  The candidate executable remains a seam:
the test records the configured commands rather than calling a provider, while
the production resolver, structured-findings parser, filing route and lesson
route all run unchanged.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflector_oob import (
    RecordingLessonsProposer,
    run_reflector_oob,
)

_REFLECTOR_LEVER = "LIVESPEC_REFLECTOR_OOB"
_RETIRED_MODEL_LEVER = "LIVESPEC_REFLECTOR_MODEL"


@dataclass(kw_only=True)
class _Runner:
    """The candidate-execution seam, recording which configured command ran."""

    replies: list[CommandResult]
    calls: list[list[str]] = field(default_factory=list)
    environs: list[dict[str, str | None]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
    ) -> CommandResult:
        assert cwd.is_dir()
        assert timeout_seconds > 0
        self.calls.append(argv)
        self.environs.append(dict(env or {}))
        return self.replies.pop(0)


@dataclass(kw_only=True)
class _Journal:
    """The reflector journal seam, retaining each production record."""

    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _repo(*, tmp_path: Path) -> Path:
    """A governed repository whose resolved chain is Codex then Claude."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "connection": {"prefix": "bd-ib"},
    "dispatcher": {
      "acp_nodes": {
        "dod_gate": {
          "agent": "codex-acp",
          "model": "gpt-5.6-terra",
          "effort": "high",
          "fallbacks": [{
            "agent": "claude-acp",
            "model": "claude-opus-5",
            "effort": "high"
          }]
        }
      }
    }
  }
}
""",
        encoding="utf-8",
    )
    return repo


def _run(
    *,
    repo: Path,
    runner: _Runner,
    journal: _Journal,
    lessons: RecordingLessonsProposer,
) -> None:
    run_reflector_oob(
        repo=repo,
        journal=journal,
        spans_path=repo / "reflector-spans.jsonl",
        runner=runner,
        lessons_proposer=lessons,
    )


def test_scenario251_the_reflector_uses_the_resolved_dod_gate_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The primary decides, malformed output falls back, and no verdict files nothing."""
    repo = _repo(tmp_path=tmp_path)
    monkeypatch.setenv(_REFLECTOR_LEVER, "observe")
    monkeypatch.setenv(_RETIRED_MODEL_LEVER, "claude-opus-4-8")

    primary = _Runner(replies=[CommandResult(exit_code=0, stdout='{"findings": []}', stderr="")])
    primary_journal = _Journal()
    _run(
        repo=repo,
        runner=primary,
        journal=primary_journal,
        lessons=RecordingLessonsProposer(),
    )

    assert [Path(call[0]).name for call in primary.calls] == ["codex-acp"]
    assert all(_RETIRED_MODEL_LEVER not in environ for environ in primary.environs)
    assert primary_journal.records == [
        {"stage": "reflector-oob", "mode": "observe", "finding_count": 0}
    ]

    fallback = _Runner(
        replies=[
            CommandResult(exit_code=0, stdout="not structured findings", stderr=""),
            CommandResult(exit_code=0, stdout=json.dumps({"findings": []}), stderr=""),
        ]
    )
    fallback_journal = _Journal()
    _run(
        repo=repo,
        runner=fallback,
        journal=fallback_journal,
        lessons=RecordingLessonsProposer(),
    )

    assert [Path(call[0]).name for call in fallback.calls] == ["codex-acp", "npx"]
    assert "@agentclientprotocol/claude-agent-acp" in fallback.calls[1]
    assert fallback_journal.records == [
        {"stage": "reflector-oob", "mode": "observe", "finding_count": 0}
    ]

    monkeypatch.setenv(_REFLECTOR_LEVER, "file")
    unavailable = _Runner(
        replies=[
            CommandResult(exit_code=124, stdout="", stderr="timed out"),
            CommandResult(exit_code=0, stdout="not structured findings", stderr=""),
        ]
    )
    unavailable_journal = _Journal()
    lessons = RecordingLessonsProposer()
    _run(repo=repo, runner=unavailable, journal=unavailable_journal, lessons=lessons)

    assert [Path(call[0]).name for call in unavailable.calls] == ["codex-acp", "npx"]
    assert lessons.proposals == []
    assert unavailable_journal.records == [
        {
            "stage": "reflector-oob-judgement-did-not-run",
            "reason": "no dod_gate candidate returned a structured findings verdict",
            "candidate_count": 2,
        }
    ]
