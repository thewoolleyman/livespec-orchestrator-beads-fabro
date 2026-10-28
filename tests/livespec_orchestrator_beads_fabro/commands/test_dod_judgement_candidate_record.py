"""A host Definition-of-Done verdict record names every candidate the taking ran.

`contracts.md` "One rubric, one subject" asks each judgement record to name "for a
chain, each candidate with its outcome". Whether a verdict that a Codex primary
returned also cost an Anthropic request can only be proven from the record, so
the record carries one `candidate:` line per candidate the chain ran, in the
order it ran them, with the candidate's agent, model, exit code and outcome.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_ADMITTED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    judge_definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_ADMISSION,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    dod_gate_prompt_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
    unjudged_governing_heading,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_HEADING = "## Scenario 239 — Every taking grades one subject by one rubric"
_PASS_REPLY = '{"outcome": "passed"}'
_CANDIDATE_PREFIX = "candidate: "


@dataclass
class _Runner:
    """A CommandRunner double replaying one result per candidate the chain runs."""

    results: list[CommandResult]
    calls: int = 0
    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
        start_new_session: bool = False,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, start_new_session)
        assert stdin is not None
        _ = os.read(stdin, 1_000_000)
        self.argvs.append(argv)
        self.calls += 1
        return self.results[min(self.calls - 1, len(self.results) - 1)]


def _item() -> WorkItem:
    return replace(
        WorkItem(
            id="bd-ib-tfu2gj",
            type="bug",
            status="ready",
            title="Name the candidates",
            description=(
                "## Definition of Done\n\n- A record names each candidate.\n\n"
                f"References: {_HEADING}\n"
            ),
            origin="freeform",
            gap_id=None,
            rank="a0",
            assignee=None,
            depends_on=(),
            captured_at="2026-10-28T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            admission_policy="auto",
            acceptance_policy="ai-only",
        )
    )


def _payload(*, tmp_path: Path) -> Path:
    root = tmp_path / "payload"
    prompts = root / ".fabro" / "workflows" / "implement-work-item" / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    _ = (prompts / "dod-gate.md").write_text(
        dod_gate_prompt_path().read_text(encoding="utf-8"), encoding="utf-8"
    )
    return root


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_HEADING}\n\nBody.\n", encoding="utf-8"
    )
    _ = (repo / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
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


def _candidate_lines(*, body: str) -> list[str]:
    return [line for line in body.splitlines() if line.startswith(_CANDIDATE_PREFIX)]


def _take(*, tmp_path: Path, runner: _Runner) -> list[str]:
    appended: list[str] = []

    def append(*, body: str) -> None:
        appended.append(body)

    decision = judge_definition_of_done(
        item=_item(),
        repo=_repo(tmp_path=tmp_path),
        stage=STAGE_PRE_ADMISSION,
        comments=(),
        append=append,
        runner=runner,
        payload_root=_payload(tmp_path=tmp_path),
        governing_heading=unjudged_governing_heading,
    )
    assert decision.outcome == JUDGEMENT_ADMITTED
    return appended


def test_a_verdict_record_names_both_candidates_when_the_fallback_decided(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "token")
    runner = _Runner(
        results=[
            CommandResult(exit_code=0, stdout="not a verdict", stderr=""),
            CommandResult(exit_code=0, stdout=_PASS_REPLY, stderr=""),
        ]
    )

    (body,) = _take(tmp_path=tmp_path, runner=runner)

    assert _candidate_lines(body=body) == [
        "candidate: agent=codex-acp model=gpt-5.6-terra exit-code=0 outcome=unparseable-verdict",
        "candidate: agent=claude-acp model=claude-opus-5 exit-code=0 outcome=verdict",
    ]


def test_a_verdict_record_names_only_the_primary_when_the_primary_decided(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "token")
    runner = _Runner(results=[CommandResult(exit_code=0, stdout=_PASS_REPLY, stderr="")])

    (body,) = _take(tmp_path=tmp_path, runner=runner)

    assert runner.calls == 1
    assert _candidate_lines(body=body) == [
        "candidate: agent=codex-acp model=gpt-5.6-terra exit-code=0 outcome=verdict",
    ]
