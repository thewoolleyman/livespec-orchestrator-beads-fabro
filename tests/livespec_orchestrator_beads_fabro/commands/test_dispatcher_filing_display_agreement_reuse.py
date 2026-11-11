"""A second display of an unchanged filed item reads the record and spends no model call.

The sibling module `test_dispatcher_filing_display_agreement.py` shows the FIRST
display recording what the later screens reuse. This one is the other direction:
an item that already carries the record (a re-display, or a display after intake's
own judgement) must render the identical lines from it, because a display that
retook the governing-heading judgement on every call is exactly where two readings
of one unchanged item come apart.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_filing_display as display_module
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_GOVERNING = "## Scenario 206 — The spec-change tier is decided by the spec-stated judgement"
_CITED = "## Scenario 141 — The referenced scenario governs the proof"
_GOVERNING_REPLY = (
    '{"kind": "stated", "stated_by": ["' + _GOVERNING + '"], "generalization_target": null,'
    ' "rationale": "It states it.", "evidence": [{"heading": "' + _GOVERNING + '",'
    ' "quote": "The checks consult the judgement."}]}'
)
_PASS_REPLY = '{"outcome": "passed"}'


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass
class _Runner:
    """A command runner answering the governing judgement, then the rubric, and counting."""

    calls: int = 0

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
        _ = os.read(stdin, 1_000_000)
        self.calls += 1
        reply = _GOVERNING_REPLY if self.calls == 1 else _PASS_REPLY
        return CommandResult(exit_code=0, stdout=reply, stderr="")


def test_a_second_display_renders_the_recorded_verdict_and_takes_no_judgement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same item, same ledger: the same lines, and the model is not asked again."""
    config = StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )
    item = WorkItem(
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
    append_work_item(path=config, item=item)
    repo = tmp_path / "repo"
    (repo / "SPECIFICATION").mkdir(parents=True)
    _ = (repo / "SPECIFICATION" / "scenarios.md").write_text(
        f"# Scenarios\n\n{_GOVERNING}\n\nThe checks consult the judgement.\n\n{_CITED}\n\nOther.\n",
        encoding="utf-8",
    )
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"acp_nodes":'
        ' {"dod_gate": {"agent": "claude-acp", "model": "claude-opus-5"}}}}}',
        encoding="utf-8",
    )
    runner = _Runner()
    monkeypatch.setattr(display_module, "ShellCommandRunner", lambda: runner)

    first = display_module.filing_display(item=item, cwd=repo, path=config).splitlines()
    second = display_module.filing_display(item=item, cwd=repo, path=config).splitlines()

    # The first display alone ran a candidate, so only it reports one.
    assert [line for line in first if not line.startswith("dod-gate: candidate ran")] == second
    assert any(_GOVERNING in line for line in second)
    assert runner.calls == 2
