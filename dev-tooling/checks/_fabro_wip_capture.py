"""The WIP-capture declaration required of every committing settle node."""

from __future__ import annotations

from _checked_workflow_payloads import BUNDLE_RELPATH, CheckedPayload
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

__all__: list[str] = ["wip_capture_findings"]

_SETTLE_NODES = (
    "implement_commit_settle",
    "fix_commit_settle",
    "review_fix_commit_settle",
)
_WIP_CAPTURE_PROGRAM = "livespec-capture-wip"


def wip_capture_findings(*, payloads: list[CheckedPayload]) -> list[str]:
    """Name every commit-settling node that omits the required WIP capture."""
    findings: list[str] = []
    for payload in payloads:
        if payload.where != "/".join(BUNDLE_RELPATH):
            continue
        graph = payload.directory / "workflow.fabro"
        if not graph.is_file():
            continue
        parsed = parse_dot_graph(text=graph.read_text(encoding="utf-8"))
        if isinstance(parsed, str):
            continue
        for node in _SETTLE_NODES:
            if node not in parsed.nodes:
                continue
            script = parsed.nodes.get(node, {}).get("script", "")
            if _WIP_CAPTURE_PROGRAM not in script:
                detail = f"{payload.where}: {node} settles agent commits without"
                findings.append(f"{detail} {_WIP_CAPTURE_PROGRAM} preservation")
    return findings
