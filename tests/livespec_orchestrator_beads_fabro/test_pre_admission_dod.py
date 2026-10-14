"""Scenario 174: intake grades the same brief with the shipped gate prompt."""

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    apply_intake_dor,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig


@pytest.mark.parametrize("source", ["backlog", "pending-approval"])
def test_intake_runs_gate_before_ready(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    reset_fake_singleton()
    config = StoreConfig(
        tenant="judgement",
        prefix="judgement",
        server_user="judgement",
        database="judgement",
        bd_path="bd",
        fake=True,
        repo_root=tmp_path,
    )
    spec = tmp_path / "SPECIFICATION"
    spec.mkdir()
    governing = "## Scenario 174 — Admission judgement\n\nThe item is judged before ready.\n"
    (spec / "scenarios.md").write_text(governing, encoding="utf-8")
    (tmp_path / ".livespec.jsonc").write_text(
        '{"dispatcher":{"sandbox_capabilities":["terminal","headless_browser"],'
        '"acp_nodes":{"dod_gate":"ANTHROPIC_MODEL=claude-opus-4-8 npx -y '
        '@agentclientprotocol/claude-agent-acp"}}}',
        encoding="utf-8",
    )
    client = make_beads_client(config=config)
    description = (
        "## Definition of Done\n\n- The item is judged before ready.\n\n"
        "References: Scenario 174 — Admission judgement\n"
    )
    client.create_issue(
        draft=IssueDraft(
            issue_id="judgement-1",
            issue_type="task",
            title="Grade admission",
            description=description,
            priority=2,
            assignee=None,
            created_at="2026-10-14T00:00:00Z",
            labels=["admission:auto"],
            metadata={},
            spec_id=None,
            parent_id=None,
        )
    )
    client.update_issue(issue_id="judgement-1", status=source)
    prompts: list[str] = []

    def run(
        self: ShellCommandRunner,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
        start_new_session: bool = False,
    ) -> CommandResult:
        _ = self, timeout_seconds, env, stdin, start_new_session
        assert client.show_issue(issue_id="judgement-1")["status"] == source
        assert cwd == tmp_path
        prompts.append(argv[argv.index("-p") + 1])
        return CommandResult(exit_code=0, stdout='{"outcome":"passed"}', stderr="")

    monkeypatch.setattr(ShellCommandRunner, "run", run)
    apply_intake_dor(
        path=config,
        item_id="judgement-1",
        checklist=DefinitionOfReadyChecklist(
            single_coherent_done=True,
            autonomously_verifiable=True,
            autonomy_tiered=True,
            dependency_linked=True,
            repo_targeted=True,
            above_floor=True,
        ),
    )
    assert len(prompts) == 1, "intake must run the semantic judgement before writing ready"
    gate = (
        Path(__file__).resolve().parents[2]
        / ".claude-plugin"
        / ".fabro"
        / "workflows"
        / "implement-work-item"
        / "prompts"
        / "dod-gate.md"
    )
    assert gate.read_text(encoding="utf-8") in prompts[0]
    assert description in prompts[0]
    assert governing in prompts[0]
    assert "headless_browser" in prompts[0]
    reset_fake_singleton()
