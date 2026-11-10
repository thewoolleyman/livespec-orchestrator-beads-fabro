"""`filing_display` reports the dod-gate judgement it took, not only the findings.

`filing_display` is the display every filing front-end shows the filer line by
line. Its governing-heading judgement ran through the `dod_gate` candidate chain
and wrote each candidate's outcome ONLY to standard error, so a judgement whose
sole reply did not parse still rendered `definition-of-done findings: none` — a
clean answer from a judgement that never happened (`bd-ib-4foa5q`).

These cases bind the three halves of the repair: one line per candidate the
display started, the findings line saying the judgement is unavailable when no
candidate returned a parseable verdict, and the unparseable reply kept in a file
under the repository's `tmp/` that the display names.

WHY THE RUNNER IS REPLACED ON THE DISPLAY MODULE. The display builds its own host
reader around a `ShellCommandRunner`, because every front-end calls it as
`filing_display(item=..., cwd=Path.cwd())` and passes nothing else. Replacing that
one name keeps the production call shape under test.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_filing_display"
_GOVERNING = "## Scenario 206 — The spec-change tier is decided by the spec-stated judgement"
_VERDICT_REPLY = (
    '{"kind": "stated", "stated_by": ["' + _GOVERNING + '"],'
    ' "generalization_target": null, "rationale": "The scenario states it.",'
    ' "evidence": [{"heading": "'
    + _GOVERNING
    + '", "quote": "The checks report their candidates."}]}'
)
_UNPARSEABLE_REPLY = "I could not decide which clause governs this item."
_NONE_LINE = "definition-of-done findings: none"
_UNAVAILABLE_LINE = "definition-of-done findings: judgement unavailable"
_CODEX_UNPARSEABLE = (
    "dod-gate: candidate ran: agent=codex-acp model=gpt-5.6-terra"
    " exit-code=0 outcome=unparseable-verdict"
)
_CODEX_FAILED = (
    "dod-gate: candidate ran: agent=codex-acp model=gpt-5.6-terra"
    " exit-code=1 outcome=judge-command-failed"
)
_CODEX_VERDICT = (
    "dod-gate: candidate ran: agent=codex-acp model=gpt-5.6-terra exit-code=0 outcome=verdict"
)
_CLAUDE_VERDICT = (
    "dod-gate: candidate ran: agent=claude-acp model=claude-opus-5 exit-code=0 outcome=verdict"
)


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
        id="bd-ib-4foa5q",
        type="bug",
        status="ready",
        title="Report the judgement",
        description=(
            "## Definition of Done\n\n- The checks report their candidates.\n\n"
            f"References: {_GOVERNING}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-10T00:00:00Z",
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
        f"# Scenarios\n\n{_GOVERNING}\n\nThe checks report their candidates.\n",
        encoding="utf-8",
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


def _display(
    *, monkeypatch: pytest.MonkeyPatch, repo: Path, results: list[CommandResult]
) -> list[str]:
    module = importlib.import_module(_MODULE)
    runner = _Runner(results=results)
    monkeypatch.setattr(module, "ShellCommandRunner", lambda: runner)
    return module.filing_display(item=_item(), cwd=repo).splitlines()


def _saved(*, repo: Path) -> list[Path]:
    scratch = repo / "tmp"
    return sorted(scratch.iterdir()) if scratch.is_dir() else []


def test_an_unparseable_only_candidate_is_named_and_the_findings_line_says_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path, fallback=False)

    lines = _display(
        monkeypatch=monkeypatch,
        repo=repo,
        results=[CommandResult(exit_code=0, stdout=_UNPARSEABLE_REPLY, stderr="")],
    )

    assert _CODEX_UNPARSEABLE in lines
    assert _UNAVAILABLE_LINE in lines
    assert _NONE_LINE not in lines


def test_an_unparseable_reply_is_written_under_tmp_and_the_display_names_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path, fallback=False)

    lines = _display(
        monkeypatch=monkeypatch,
        repo=repo,
        results=[CommandResult(exit_code=0, stdout=_UNPARSEABLE_REPLY, stderr="")],
    )

    saved = _saved(repo=repo)
    assert len(saved) == 1
    assert saved[0].parent == repo / "tmp"
    assert saved[0].read_text(encoding="utf-8") == _UNPARSEABLE_REPLY
    naming = [line for line in lines if str(saved[0]) in line]
    assert len(naming) == 1
    assert "agent=codex-acp model=gpt-5.6-terra" in naming[0]


def test_a_parseable_verdict_keeps_the_findings_line_and_writes_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path, fallback=False)

    lines = _display(
        monkeypatch=monkeypatch,
        repo=repo,
        results=[CommandResult(exit_code=0, stdout=_VERDICT_REPLY, stderr="")],
    )

    assert _CODEX_VERDICT in lines
    assert _NONE_LINE in lines
    assert _UNAVAILABLE_LINE not in lines
    assert _saved(repo=repo) == []


def test_every_candidate_the_chain_started_is_named_and_a_later_verdict_is_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "token")
    repo = _repo(tmp_path=tmp_path, fallback=True)

    lines = _display(
        monkeypatch=monkeypatch,
        repo=repo,
        results=[
            CommandResult(exit_code=0, stdout=_UNPARSEABLE_REPLY, stderr=""),
            CommandResult(exit_code=0, stdout=_VERDICT_REPLY, stderr=""),
        ],
    )

    candidates = [line for line in lines if line.startswith("dod-gate: candidate ran: ")]
    assert candidates == [_CODEX_UNPARSEABLE, _CLAUDE_VERDICT]
    assert _NONE_LINE in lines
    assert _UNAVAILABLE_LINE not in lines
    assert len(_saved(repo=repo)) == 1


def test_a_failed_candidate_is_named_and_unavailable_but_has_no_reply_to_keep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path, fallback=False)

    lines = _display(
        monkeypatch=monkeypatch,
        repo=repo,
        results=[CommandResult(exit_code=1, stdout="", stderr="boom")],
    )

    assert _CODEX_FAILED in lines
    assert _UNAVAILABLE_LINE in lines
    assert _NONE_LINE not in lines
    assert _saved(repo=repo) == []


def test_a_reply_that_cannot_be_saved_is_reported_rather_than_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path, fallback=False)
    _ = (repo / "tmp").write_text("not a directory", encoding="utf-8")

    lines = _display(
        monkeypatch=monkeypatch,
        repo=repo,
        results=[CommandResult(exit_code=0, stdout=_UNPARSEABLE_REPLY, stderr="")],
    )

    assert _CODEX_UNPARSEABLE in lines
    assert _UNAVAILABLE_LINE in lines
    assert any("could not be saved" in line for line in lines)
