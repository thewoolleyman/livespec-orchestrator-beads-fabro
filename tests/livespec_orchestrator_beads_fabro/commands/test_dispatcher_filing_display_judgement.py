"""The filing display distinguishes an unavailable judgement from a clean one."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_filing_display"
_GOVERNING = "## Scenario 239 — Every taking of the Definition-of-Done judgement grades one subject by one rubric"
_UNPARSEABLE_REPLY = "I could not decide which clause governs this item."


@dataclass
class _Runner:
    """A command runner returning the one configured candidate reply."""

    result: CommandResult

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
        del argv, cwd, timeout_seconds, env, stdin, start_new_session
        return self.result


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-e3vbbo",
        type="bug",
        status="pending-approval",
        title="The filing display reports its governing judgement",
        description=(
            "## Definition of Done\n\n"
            "- The display reports its governing-heading judgement.\n\n"
            f"References: {_GOVERNING}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True)
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_GOVERNING}\n\nThe display reports its governing-heading judgement.\n",
        encoding="utf-8",
    )
    _ = (repo / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "acp_nodes": {
        "dod_gate": {
          "agent": "codex-acp",
          "model": "gpt-5.6-terra",
          "effort": "high"
        }
      }
    }
  }
}
""",
        encoding="utf-8",
    )
    return repo


def test_an_unavailable_governing_heading_judgement_is_not_reported_as_no_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A filer must see that the reading did not happen instead of a clean verdict."""
    module = importlib.import_module(_MODULE)
    monkeypatch.setattr(
        module,
        "ShellCommandRunner",
        lambda: _Runner(result=CommandResult(exit_code=0, stdout=_UNPARSEABLE_REPLY, stderr="")),
    )

    lines = module.filing_display(item=_item(), cwd=_repo(tmp_path=tmp_path)).splitlines()

    assert "definition-of-done findings: judgement unavailable" in lines
    assert "definition-of-done findings: none" not in lines


def test_a_filing_reader_that_takes_no_governing_heading_judgement_is_not_clean(
    tmp_path: Path,
) -> None:
    """An explicitly unjudged display must not render a clean finding verdict."""
    module = importlib.import_module(_MODULE)

    lines = module.filing_display(
        item=_item(), cwd=_repo(tmp_path=tmp_path), governing=_unjudged_reader
    ).splitlines()

    assert "definition-of-done findings: judgement unavailable" in lines
    assert "definition-of-done findings: none" not in lines


def _unjudged_reader(*, item: WorkItem, repo: Path) -> None:
    """A filing surface that deliberately takes no governing-heading judgement."""
    del item, repo
