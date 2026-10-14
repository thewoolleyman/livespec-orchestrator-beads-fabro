"""Run the shipped Definition-of-Done judgement before spending a factory slot.

The gate prompt remains the authority. This host invocation supplies the same
effective criteria and referenced clauses, and uses the committed capability
mirror: the host's own installed tools say nothing about the target image.
Expected execution faults are data; the admission caller owns their routing.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, cast

from returns.io import IOFailure, IOResult, IOSuccess

from livespec_orchestrator_beads_fabro.commands._acp_catalogs import resolve_acp_catalogs
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import resolve_acp_nodes
from livespec_orchestrator_beads_fabro.commands._acp_node_repository import repository_acp_overlays
from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_nodes import workflow_layer
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_publication_policy import (
    scoped_repository_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_criteria_wall_variant import (
    criteria_wall_variant,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    effective_criteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import render_goal
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import executing_payload_root
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_capabilities import (
    mirrored_sandbox_capabilities,
)
from livespec_orchestrator_beads_fabro.commands._workflow_variants import workflow_registry
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt, parse_json
from livespec_orchestrator_beads_fabro.errors import LivespecConfigUnreadableError
from livespec_orchestrator_beads_fabro.store import read_work_item_comments

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "judge_before_admission",
]

_WORKFLOW = Path(".fabro/workflows/implement-work-item")


def judge_before_admission(*, path: StoreConfig, item: WorkItem) -> IOResult[CommandResult, str]:
    """Run one read-only judgement, or explain why it could not run.

    No factory is contacted. The host CLI inherits the resolved gate adapter's
    model and environment; unsupported adapters are unavailable, never silently
    substituted with a different provider.
    """
    repo = path.repo_root
    if repo is None:
        return IOFailure("repository root is unavailable")
    variant = criteria_wall_variant(repo=repo, work_item_id=item.id)
    if variant.exempt:
        return IOFailure("groom-kind item does not require an implementation judgement")
    result = attempt(
        action=lambda: _judge(path=path, item=item, repo=repo, workflow_name=variant.name),
        exceptions=(OSError, LivespecConfigUnreadableError),
    )
    if isinstance(result, AttemptFailure):
        return IOFailure(str(result.error))
    return IOFailure(result) if isinstance(result, str) else IOSuccess(result)


def _judge(
    *, path: StoreConfig, item: WorkItem, repo: Path, workflow_name: str
) -> CommandResult | str:
    adapter = _gate_adapter(repo=repo, workflow_name=workflow_name)
    if isinstance(adapter, str):
        return adapter
    prompt = _prompt(path=path, item=item, repo=repo)
    argv = _headless_argv(adapter=adapter, prompt=prompt)
    if isinstance(argv, str):
        return argv
    return ShellCommandRunner().run(
        argv=argv,
        cwd=repo,
        timeout_seconds=600.0,
        env=dict(adapter.env),
        stdin=subprocess.DEVNULL,
    )


def _headless_argv(*, adapter: AcpAdapter, prompt: str) -> list[str] | str:
    """Translate shipped adapters without guessing custom transports.

    Model and effort stay pinned to the gate's configuration. Tool permissions
    are narrowed for this host read, and every raw Codex call receives EOF.
    """
    command = (*shlex.split(adapter.command), *adapter.args)
    if command == ("npx", "-y", "@agentclientprotocol/claude-agent-acp"):
        return [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "json",
            "--tools",
            "Read,Grep,Glob",
            "--strict-mcp-config",
            "--mcp-config",
            '{"mcpServers":{}}',
        ]
    if len(command) != 1 or Path(command[0]).name != "codex-acp":
        return "no eligible host judgement runner for the configured dod_gate adapter"
    parsed = parse_json(text=adapter.env.get("CODEX_CONFIG", ""))
    if not isinstance(parsed, dict):
        return "dod_gate CODEX_CONFIG is not a readable model configuration"
    config = cast("dict[str, object]", parsed)
    supported = {"model", "model_reasoning_effort", "approval_policy", "sandbox_mode"}
    if config.keys() - supported or not isinstance(config.get("model"), str):
        return "no eligible host judgement runner for the configured Codex model settings"
    argv = ["codex", "exec", "--json", "--sandbox", "read-only", "-c", 'approval_policy="never"']
    for key in ("model", "model_reasoning_effort"):
        value = config.get(key)
        if value is not None:
            argv.extend(["-c", f"{key}={json.dumps(value)}"])
    return [*argv, prompt]


def _gate_adapter(*, repo: Path, workflow_name: str) -> AcpAdapter | str:
    block, _ = scoped_repository_block(block=dispatcher_block(cwd=repo), workflow_kind="implement")
    catalogs = resolve_acp_catalogs(block=block)
    if isinstance(catalogs, str):
        return catalogs
    directory = workflow_registry(block=block).get(workflow_name)
    local = repo / (directory or _WORKFLOW) / "workflow.toml"
    manifest = (
        local
        if directory is not None or local.is_file()
        else executing_payload_root() / _WORKFLOW / "workflow.toml"
    )
    defaults = workflow_layer(committed=manifest, catalogs=catalogs)
    if isinstance(defaults, str):
        return defaults
    overlays = repository_acp_overlays(block=block, catalogs=catalogs)
    if isinstance(overlays, str):
        return overlays
    resolution = resolve_acp_nodes(workflow_inputs=defaults, repository=overlays, dispatch={})
    if isinstance(resolution, str):
        return resolution
    node = resolution.nodes.get("dod_gate")
    return "workflow declares no dod_gate model" if node is None else node.adapter


def _prompt(*, path: StoreConfig, item: WorkItem, repo: Path) -> str:
    gate = (executing_payload_root() / _WORKFLOW / "prompts/dod-gate.md").read_text(
        encoding="utf-8"
    )
    criteria = effective_criteria(item=item)
    capabilities = mirrored_sandbox_capabilities(block=dispatcher_block(cwd=repo))
    comments = read_work_item_comments(path=path, work_item_id=item.id)
    goal = render_goal(item=item, repo=repo, branch=f"feat/{item.id}", comments=comments)
    return (
        f"Goal:\n{goal}\n\n{gate}\n\n"
        "Host pre-admission invocation: apply the judgement above without changing files. "
        "The target image is not this host: use only the committed capability mirror "
        "below, or report unpublished when it is empty. Search SPECIFICATION/scenarios.md "
        "with the read-only tools when checking for a missing governing scenario.\n"
        f"Effective criteria ({criteria.source}):\n{criteria.text}\n"
        f"Sandbox capability mirror: {json.dumps(capabilities)}\n"
        f"Referenced specification clauses:\n{_clauses(item=item, repo=repo)}\n"
        "For machine-readable transport, retain every finding and remedy in the gate's "
        'failed outcome, and add a "remedies" array of remedy strings in finding order. '
        'On a clean pass end with {"outcome":"passed"}. '
        "If you cannot complete the judgement end with "
        '{"outcome":"unavailable","reason":"<why>"}.\n'
    )


def _clauses(*, item: WorkItem, repo: Path) -> str:
    references = definition_of_done(description=item.description).references
    clauses: list[str] = []
    for file in sorted((repo / "SPECIFICATION").glob("*.md")):
        text = file.read_text(encoding="utf-8")
        for clause in re.split(r"(?m)(?=^## )", text):
            heading = clause.partition("\n")[0]
            if heading in references or heading.removeprefix("## ") in references:
                clauses.append(f"{file.name}:\n{clause}")
    return "\n".join(clauses)
