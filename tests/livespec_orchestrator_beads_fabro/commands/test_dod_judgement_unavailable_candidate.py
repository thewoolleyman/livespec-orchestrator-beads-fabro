"""A host judgement that ends did-not-run names the candidate that ended the chain.

The measured gap (2026-10-27): a pre-dispatch judgement comment read
`outcome: did-not-run` with `judgement-unavailable-cause: judge-command-failed`
and named no candidate and no exit code, while the drive's standard error was
empty — so the failure could not be attributed to the Codex leg, the Claude leg,
a credential or a timeout. The record now carries every candidate the chain ran
and the one whose failure ended it, and the same ender is written to standard
error.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_dod_judgement_run as judgement_module,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_UNAVAILABLE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    judge_definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_DISPATCH,
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
_ENDER_PREFIX = "judgement-unavailable-candidate: "
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


def _lines_with(*, body: str, prefix: str) -> list[str]:
    return [line for line in body.splitlines() if line.startswith(prefix)]


def _take_unavailable(*, tmp_path: Path, runner: _Runner) -> str:
    appended: list[str] = []

    def append(*, body: str) -> None:
        appended.append(body)

    decision = judge_definition_of_done(
        item=_item(),
        repo=_repo(tmp_path=tmp_path),
        stage=STAGE_PRE_DISPATCH,
        comments=(),
        append=append,
        runner=runner,
        payload_root=_payload(tmp_path=tmp_path),
        governing_heading=unjudged_governing_heading,
    )
    assert decision.outcome == JUDGEMENT_UNAVAILABLE
    (body,) = appended
    return body


_FAILED = CommandResult(exit_code=1, stdout="", stderr="")


def test_the_record_names_each_candidate_and_the_one_that_ended_the_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "token")
    runner = _Runner(
        results=[CommandResult(exit_code=2, stdout="", stderr=""), _FAILED],
    )

    body = _take_unavailable(tmp_path=tmp_path, runner=runner)

    assert "judgement-unavailable-cause: judge-command-failed" in body.splitlines()
    assert _lines_with(body=body, prefix=_CANDIDATE_PREFIX) == [
        "candidate: agent=codex-acp model=gpt-5.6-terra exit-code=2 outcome=judge-command-failed",
        "candidate: agent=claude-acp model=claude-opus-5 exit-code=1 outcome=judge-command-failed",
    ]
    assert _lines_with(body=body, prefix=_ENDER_PREFIX) == [
        "judgement-unavailable-candidate: agent=claude-acp model=claude-opus-5"
        " exit-code=1 outcome=judge-command-failed",
    ]


def test_standard_error_names_the_candidate_that_ended_the_chain_and_its_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "token")
    runner = _Runner(
        results=[CommandResult(exit_code=2, stdout="", stderr=""), _FAILED],
    )

    _ = _take_unavailable(tmp_path=tmp_path, runner=runner)

    reports = [line for line in capsys.readouterr().err.splitlines() if "did not run" in line]
    assert len(reports) == 1
    assert "cause judge-command-failed" in reports[0]
    assert (
        "agent=claude-acp model=claude-opus-5 exit-code=1 outcome=judge-command-failed"
        in reports[0]
    )


def test_a_chain_that_ran_no_candidate_says_so_on_standard_error_and_in_the_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_candidates(*, cwd: Path) -> None:
        _ = cwd

    monkeypatch.setattr(judgement_module, "dod_gate_candidates", no_candidates)
    runner = _Runner(results=[_FAILED])

    body = _take_unavailable(tmp_path=tmp_path, runner=runner)

    assert runner.calls == 0
    assert "judgement-unavailable-cause: no-eligible-model" in body.splitlines()
    assert _lines_with(body=body, prefix=_CANDIDATE_PREFIX) == []
    assert _lines_with(body=body, prefix=_ENDER_PREFIX) == []
    reports = [line for line in capsys.readouterr().err.splitlines() if "did not run" in line]
    assert len(reports) == 1
    assert "cause no-eligible-model" in reports[0]
    assert "no candidate ran" in reports[0]
