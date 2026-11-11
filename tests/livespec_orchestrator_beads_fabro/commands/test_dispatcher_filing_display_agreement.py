"""A filed item's display and the later Definition-of-Done screens take ONE judgement.

Work-item `bd-ib-e3vbbo`: `filing_display` reported `definition-of-done findings:
none` for items the pre-dispatch screen then refused, because the display took
its own model judgement and left no record the later screens could read. Every
front-end displays AFTER filing, so the display can be handed the item's ledger
and go through the very decision the approve valve and the pre-dispatch wall take:
reuse the recorded verdict, else take it and record it.

EVERY CASE READS THE LATER SCREEN OFF THE SAME LEDGER AND COUNTS THE MODEL CALLS.
"The two surfaces agree" is a claim about a spend that did NOT happen as much as
about an answer: a display that took a judgement and left no record would show the
same finding text and still let the later screen retake it, and a retaking is
exactly where two readings of one unchanged item come apart.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_filing_display as display_module
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    judge_item_definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_ADMISSION,
    STAGE_PRE_DISPATCH,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
    unjudged_governing_heading,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_GOVERNING = "## Scenario 206 — The spec-change tier is decided by the spec-stated judgement"
_CITED = "## Scenario 141 — The referenced scenario governs the proof"
_PASS_REPLY = '{"outcome": "passed"}'
_PROOF_MODE_REPLY = (
    '{"outcome": "failed", "failure_reason":'
    ' "bd-ib-e3vbbo: assertion 1 claims factory_captured for a surface no factory sandbox'
    ' offers; declare it host-captured."}'
)
_GOVERNING_REPLY = (
    '{"kind": "stated", "stated_by": ["' + _GOVERNING + '"], "generalization_target": null,'
    ' "rationale": "It states it.", "evidence": [{"heading": "' + _GOVERNING + '",'
    ' "quote": "The checks consult the judgement."}]}'
)


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass
class _Runner:
    """A command runner answering each model call in turn and counting them."""

    replies: list[str]
    calls: int = 0
    prompts: list[str] = field(default_factory=list)

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
        _ = (argv, cwd, timeout_seconds, env, start_new_session)
        assert stdin is not None
        self.prompts.append(os.read(stdin, 1_000_000).decode("utf-8"))
        self.calls += 1
        reply = self.replies[min(self.calls - 1, len(self.replies) - 1)]
        return CommandResult(exit_code=0, stdout=reply, stderr="")


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-e3vbbo",
        type="bug",
        status="pending-approval",
        title="The display agrees with the screens that follow it",
        description=(
            "## Definition of Done\n\n- The checks consult the judgement.\n\n"
            f"References: {_CITED}\n"
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
        admission_policy="manual",
        acceptance_policy="ai-only",
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_GOVERNING}\n\nThe checks consult the judgement.\n\n{_CITED}\n\nOther.\n",
        encoding="utf-8",
    )
    _ = (repo / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "acp_nodes": {
        "dod_gate": {"agent": "claude-acp", "model": "claude-opus-5"}
      }
    }
  }
}
""",
        encoding="utf-8",
    )
    return repo


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def test_the_pre_admission_proof_mode_verdict_is_displayed_and_then_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal approve would issue is on the display, and approve spends nothing."""
    config = _config()
    item = _item()
    append_work_item(path=config, item=item)
    repo = _repo(tmp_path=tmp_path)
    runner = _Runner(replies=[_PROOF_MODE_REPLY])
    monkeypatch.setattr(display_module, "ShellCommandRunner", lambda: runner)

    lines = display_module.filing_display(
        item=item, cwd=repo, governing=unjudged_governing_heading, path=config
    ).splitlines()

    assert any(
        line.startswith(display_module.ADVISORY_FINDING_PREFIX) and "factory_captured" in line
        for line in lines
    )
    assert display_module.FINDINGS_NONE_REPORT not in lines
    assert runner.calls == 1

    approve = judge_item_definition_of_done(
        item=item,
        repo=repo,
        path=config,
        stage=STAGE_PRE_ADMISSION,
        runner=runner,
        governing_heading=unjudged_governing_heading,
    )

    assert approve.reused is True
    assert approve.holds is True
    assert runner.calls == 1


def test_the_governing_heading_the_display_named_is_the_one_pre_dispatch_reuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One unchanged item, one governing verdict: the screen after the display retakes none."""
    config = _config()
    item = _item()
    append_work_item(path=config, item=item)
    repo = _repo(tmp_path=tmp_path)
    runner = _Runner(replies=[_GOVERNING_REPLY, _PASS_REPLY])
    monkeypatch.setattr(display_module, "ShellCommandRunner", lambda: runner)

    lines = display_module.filing_display(item=item, cwd=repo, path=config).splitlines()

    assert any(
        line.startswith(display_module.ADVISORY_FINDING_PREFIX) and _GOVERNING in line
        for line in lines
    )
    assert display_module.FINDINGS_NONE_REPORT not in lines
    assert runner.calls == 2

    screen = judge_item_definition_of_done(
        item=item,
        repo=repo,
        path=config,
        stage=STAGE_PRE_DISPATCH,
        runner=runner,
        governing_heading=unjudged_governing_heading,
    )

    assert screen.reused is True
    assert screen.holds is True
    assert any(_GOVERNING in finding for finding in screen.findings)
    assert runner.calls == 2


def test_an_unreadable_ledger_is_reported_unavailable_and_records_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no sidecar to read or write the display cannot claim agreement, so it says so."""
    config = _config()
    item = _item()
    append_work_item(path=config, item=item)
    repo = _repo(tmp_path=tmp_path)
    runner = _Runner(replies=[_PASS_REPLY])
    monkeypatch.setattr(display_module, "ShellCommandRunner", lambda: runner)
    for module in (
        display_module,
        __import__(
            "livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate",
            fromlist=["judgement_comment_bodies"],
        ),
    ):
        monkeypatch.setattr(module, "judgement_comment_bodies", lambda **_: None)

    lines = display_module.filing_display(
        item=item, cwd=repo, governing=unjudged_governing_heading, path=config
    ).splitlines()

    assert "definition-of-done findings: judgement unavailable" in lines
    assert display_module.FINDINGS_NONE_REPORT not in lines
    assert runner.calls == 0
