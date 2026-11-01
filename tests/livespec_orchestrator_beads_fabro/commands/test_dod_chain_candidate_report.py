"""The governing-heading verdict and the drift run report each candidate they ran.

Both put a spec-stated judgement through the same `dod_gate` chain a host
Definition-of-Done taking uses, and neither writes a ledger record of its own, so
standard error is the only place a reader can learn which legs ran. A drift pass
or a governing-heading read that silently fell through to an Anthropic candidate
is otherwise indistinguishable from one a Codex primary answered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
    host_governing_heading_reader,
)
from livespec_orchestrator_beads_fabro.commands._drift_run_judge import drift_judge
from livespec_orchestrator_beads_fabro.types import WorkItem

_GOVERNING = "## Scenario 206 — The spec-change tier is decided by the spec-stated judgement"
_VERDICT_REPLY = (
    '{"kind": "stated", "stated_by": ["' + _GOVERNING + '"],'
    ' "generalization_target": null, "rationale": "The scenario states it."}'
)
_REPORT_MARKER = "dod-gate: candidate ran: "
_CODEX_LINE = "agent=codex-acp model=gpt-5.6-terra exit-code=0 outcome=verdict"


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
        _ = (cwd, timeout_seconds, env, stdin, start_new_session)
        self.argvs.append(argv)
        self.calls += 1
        return self.results[min(self.calls - 1, len(self.results) - 1)]


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-tfu2gj",
        type="bug",
        status="ready",
        title="Report the candidates",
        description=(
            "## Definition of Done\n\n- The checks report their candidates.\n\n"
            f"References: {_GOVERNING}\n"
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


def _repo(*, tmp_path: Path, fallback: bool) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_GOVERNING}\n\nIt states the behaviour.\n", encoding="utf-8"
    )
    fallbacks = (
        ',\n          "fallbacks": [{\n'
        '            "agent": "claude-acp",\n'
        '            "model": "claude-opus-5",\n'
        '            "effort": "high"\n'
        "          }]"
        if fallback
        else ""
    )
    _ = (repo / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "acp_nodes": {
        "dod_gate": {
          "agent": "codex-acp",
          "model": "gpt-5.6-terra",
          "effort": "high"__FALLBACKS__
        }
      }
    }
  }
}
""".replace("__FALLBACKS__", fallbacks),
        encoding="utf-8",
    )
    return repo


def _reports(*, captured: str) -> list[str]:
    return [
        line.removeprefix(_REPORT_MARKER)
        for line in captured.splitlines()
        if line.startswith(_REPORT_MARKER)
    ]


def test_a_governing_heading_verdict_reports_the_candidate_that_answered(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _Runner(results=[CommandResult(exit_code=0, stdout=_VERDICT_REPLY, stderr="")])
    reader = host_governing_heading_reader(runner=runner)

    verdict = reader(item=_item(), repo=_repo(tmp_path=tmp_path, fallback=False))

    assert verdict is not None
    assert runner.calls == 1
    assert _reports(captured=capsys.readouterr().err) == [_CODEX_LINE]


def test_a_drift_run_judgement_reports_every_candidate_it_ran_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "token")
    runner = _Runner(
        results=[
            CommandResult(exit_code=1, stdout="", stderr=""),
            CommandResult(exit_code=0, stdout=_VERDICT_REPLY, stderr=""),
        ]
    )
    judge = drift_judge(
        project_root=_repo(tmp_path=tmp_path, fallback=True), runner=runner, caller="drift_run"
    )

    reply = judge("one prompt")

    assert reply == _VERDICT_REPLY
    assert _reports(captured=capsys.readouterr().err) == [
        "agent=codex-acp model=gpt-5.6-terra exit-code=1 outcome=judge-command-failed",
        "agent=claude-acp model=claude-opus-5 exit-code=0 outcome=verdict",
    ]
