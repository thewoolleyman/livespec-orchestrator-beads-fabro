"""Host judgement context, adapter selection, and external failure boundaries."""

from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro import _pre_admission_dod as judgement
from livespec_orchestrator_beads_fabro._beads_client import (
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import _drive_valves as valves
from livespec_orchestrator_beads_fabro.commands._dispatcher_criteria_wall_variant import (
    CriteriaWallVariant,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.store import read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io


@pytest.fixture
def filed(*, tmp_path: Path) -> tuple[StoreConfig, WorkItem]:
    reset_fake_singleton()
    config = StoreConfig(
        tenant="judge",
        prefix="judge",
        server_user="judge",
        database="judge",
        bd_path="bd",
        fake=True,
        repo_root=tmp_path,
    )
    client = make_beads_client(config=config)
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id="judge-1",
            issue_type="task",
            title="Route a slice",
            description="## Definition of Done\n- Route the slice.\nReferences: ## Routing\n",
            priority=2,
            assignee=None,
            created_at="2026-10-14T00:00:00Z",
            labels=["admission:auto"],
            metadata={},
            spec_id=None,
            parent_id=None,
        )
    )
    client.add_comment(issue_id="judge-1", body="The operator's rider governs this slice.")
    spec = tmp_path / "SPECIFICATION"
    spec.mkdir()
    _ = (spec / "contracts.md").write_text(
        "# Contracts\n\n## Routing\nRoute the slice.\n", encoding="utf-8"
    )
    _configure(
        repo=tmp_path,
        adapter="ANTHROPIC_MODEL=chosen-model npx -y @agentclientprotocol/claude-agent-acp",
    )
    return config, next(iter(read_work_items(path=config)))


def _configure(*, repo: Path, adapter: str) -> None:
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {
                        "acp_nodes": {"dod_gate": adapter},
                        "sandbox_capabilities": ["terminal", "tmux"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def test_runtime_uses_resolved_model_and_context(
    *,
    filed: tuple[StoreConfig, WorkItem],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, item = filed
    calls: list[list[str]] = []

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
        _ = self, start_new_session
        assert cwd == config.repo_root
        assert timeout_seconds > 0
        assert env is not None
        assert env["ANTHROPIC_MODEL"] == "chosen-model"
        assert stdin == subprocess.DEVNULL
        assert argv[argv.index("--tools") + 1] == "Read,Grep,Glob"
        calls.append(argv)
        return CommandResult(exit_code=0, stdout='{"outcome":"passed"}', stderr="")

    monkeypatch.setattr(ShellCommandRunner, "run", run)
    result = _judged(path=config, item=item)
    assert isinstance(result, CommandResult)
    assert len(calls) == 1
    prompt = calls[0][2]
    assert 'Sandbox capability mirror: ["terminal", "tmux"]' in prompt
    assert "The operator's rider governs this slice." in prompt
    assert "contracts.md:\n## Routing\nRoute the slice." in prompt
    assert "Effective criteria (description-definition-of-done):" in prompt


@pytest.mark.parametrize(
    "resolver",
    [
        "resolve_acp_catalogs",
        "workflow_layer",
        "repository_acp_overlays",
        "resolve_acp_nodes",
    ],
)
def test_resolution_fault_is_reported(
    *,
    filed: tuple[StoreConfig, WorkItem],
    monkeypatch: pytest.MonkeyPatch,
    resolver: str,
) -> None:
    config, item = filed

    def refusal(**_: object) -> str:
        return "configuration cannot resolve"

    monkeypatch.setattr(judgement, resolver, refusal)
    assert _judged(path=config, item=item) == "configuration cannot resolve"


def test_absent_repo_is_unavailable(*, filed: tuple[StoreConfig, WorkItem]) -> None:
    config, item = filed
    assert (
        _judged(path=replace(config, repo_root=None), item=item) == "repository root is unavailable"
    )


def test_groom_does_not_invoke_implementation_judge(
    *,
    filed: tuple[StoreConfig, WorkItem],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, item = filed

    def variant(**_: object) -> CriteriaWallVariant:
        return CriteriaWallVariant(name="groom", kind="groom")

    monkeypatch.setattr(judgement, "criteria_wall_variant", variant)
    assert "groom-kind" in str(_judged(path=config, item=item))


@pytest.mark.parametrize("adapter", ["custom-acp", "codex-acp --custom-option"])
def test_custom_adapter_is_not_replaced(
    *, filed: tuple[StoreConfig, WorkItem], tmp_path: Path, adapter: str
) -> None:
    config, item = filed
    _configure(repo=tmp_path, adapter=adapter)
    assert "no eligible" in str(_judged(path=config, item=item))


def test_workflow_without_gate_is_unavailable(
    *, filed: tuple[StoreConfig, WorkItem], tmp_path: Path
) -> None:
    config, item = filed
    _ = (tmp_path / ".livespec.jsonc").write_text("{}", encoding="utf-8")
    manifest = tmp_path / ".fabro/workflows/implement-work-item/workflow.toml"
    manifest.parent.mkdir(parents=True)
    _ = manifest.write_text("[run.inputs]\n", encoding="utf-8")
    assert _judged(path=config, item=item) == "workflow declares no dod_gate model"


def test_unreadable_gate_is_unavailable(
    *,
    filed: tuple[StoreConfig, WorkItem],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config, item = filed
    manifest = tmp_path / ".fabro/workflows/implement-work-item/workflow.toml"
    manifest.parent.mkdir(parents=True)
    _ = manifest.write_text(
        '[run.inputs]\ndod_gate_adapter = "npx -y @agentclientprotocol/claude-agent-acp"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(judgement, "executing_payload_root", lambda: tmp_path)
    assert "dod-gate.md" in str(_judged(path=config, item=item))


def _judged(*, path: StoreConfig, item: WorkItem) -> CommandResult | str:
    result = judgement.judge_before_admission(path=path, item=item)
    return unsafe_perform_io(result.unwrap() if is_successful(result) else result.failure())


@pytest.mark.parametrize(
    ("action", "source"), [("approve", "pending-approval"), ("move", "backlog")]
)
def test_human_entry_routes_judge_before_writing_ready(
    *,
    filed: tuple[StoreConfig, WorkItem],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    source: str,
) -> None:
    config, item = filed
    client = make_beads_client(config=config)
    client.update_issue(
        issue_id=item.id,
        status=source,
        add_labels=["admission:manual"],
        remove_labels=["admission:auto"],
    )
    calls: list[str] = []

    def connection(**_: object) -> StoreConfig:
        return config

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
        _ = self, cwd, timeout_seconds, env, stdin, start_new_session
        assert argv[0] == "claude"
        assert client.show_issue(issue_id=item.id)["status"] == source
        calls.append(argv[2])
        return CommandResult(exit_code=0, stdout='{"outcome":"passed"}', stderr="")

    monkeypatch.setattr(valves, "resolve_store_config", connection)
    monkeypatch.setattr(ShellCommandRunner, "run", run)
    aid = f"{action}:{item.id}" + (":ready" if action == "move" else "")
    _ = valves.run_human_valve_action(repo=tmp_path, action_id=aid)
    assert len(calls) == 1
    assert client.show_issue(issue_id=item.id)["status"] == "ready"


@pytest.mark.parametrize("effort", [None, "high"])
def test_codex_uses_the_gate_pin_with_eof_and_read_only_tools(
    *,
    filed: tuple[StoreConfig, WorkItem],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    effort: str | None,
) -> None:
    config, item = filed
    settings = {"model": "gpt-5.5"}
    if effort is not None:
        settings["model_reasoning_effort"] = effort
    _configure(
        repo=tmp_path,
        adapter=f"CODEX_CONFIG={shlex.quote(json.dumps(settings))} /opt/livespec/codex-acp/bin/codex-acp",
    )
    calls: list[list[str]] = []

    def run(self: ShellCommandRunner, **kwargs: object) -> CommandResult:
        _ = self
        assert kwargs["stdin"] == subprocess.DEVNULL
        argv = cast("list[str]", kwargs["argv"])
        calls.append(argv)
        return CommandResult(exit_code=0, stdout="model output", stderr="")

    monkeypatch.setattr(ShellCommandRunner, "run", run)
    assert isinstance(_judged(path=config, item=item), CommandResult)
    argv = calls[0]
    assert argv[:5] == ["codex", "exec", "--json", "--sandbox", "read-only"]
    assert 'model="gpt-5.5"' in argv
    assert ('model_reasoning_effort="high"' in argv) == (effort is not None)


@pytest.mark.parametrize("settings", ["broken", "[]", "{}", '{"model":"pinned","unknown":true}'])
def test_codex_settings_that_cannot_be_preserved_are_unavailable(
    *,
    filed: tuple[StoreConfig, WorkItem],
    tmp_path: Path,
    settings: str,
) -> None:
    config, item = filed
    _configure(repo=tmp_path, adapter=f"CODEX_CONFIG={shlex.quote(settings)} codex-acp")
    assert isinstance(_judged(path=config, item=item), str)


@pytest.mark.parametrize("custom", [False, True])
def test_workflow_scoping_preserves_the_implementation_gate_model(
    *,
    filed: tuple[StoreConfig, WorkItem],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    custom: bool,
) -> None:
    config, item = filed
    directory = "custom-workflow" if custom else ".fabro/workflows/implement-work-item"
    manifest = tmp_path / directory / "workflow.toml"
    manifest.parent.mkdir(parents=True)
    _ = manifest.write_text(
        '[run.inputs]\ndod_gate_adapter = "ANTHROPIC_MODEL=workflow-model npx -y @agentclientprotocol/claude-agent-acp"\n',
        encoding="utf-8",
    )
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "judge",
                        "prefix": "judge",
                        "server_user": "judge",
                        "database": "judge",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {
                        "acp_nodes": {"pr": "groom-only-acp"},
                        "workflows": {"custom": "custom-workflow"},
                        "default_workflow": "custom" if custom else "implement-work-item",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    models: list[str] = []

    def run(self: ShellCommandRunner, **kwargs: object) -> CommandResult:
        _ = self
        env = cast("dict[str, str]", kwargs["env"])
        models.append(env["ANTHROPIC_MODEL"])
        return CommandResult(exit_code=0, stdout='{"outcome":"passed"}', stderr="")

    monkeypatch.setattr(ShellCommandRunner, "run", run)
    assert isinstance(_judged(path=config, item=item), CommandResult)
    assert models == ["workflow-model"]
