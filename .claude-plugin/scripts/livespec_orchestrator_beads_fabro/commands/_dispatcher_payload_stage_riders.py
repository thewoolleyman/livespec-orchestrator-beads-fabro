"""Prefix each materialized agent prompt with its stage-specific riders."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

__all__: list[str] = ["prefix_stage_riders"]


def prefix_stage_riders(
    *, payload_dir: Path, graph: Path, stage_riders: Mapping[str, str]
) -> str | None:
    """Prefix copied prompts, skipping stages the selected workflow does not declare.

    A workflow variant need not offer every agent stage. There is no brief for a
    missing node, so its targeted rider has nowhere to travel and is harmless.
    A declared node whose copied prompt is absent, or that names no prompt at all,
    is instead a materialization failure: the graph would ask Fabro to read a
    missing file, or the stage's targeted rider would be silently dropped.
    """
    try:
        graph_text = graph.read_text(encoding="utf-8")
        for stage, section in stage_riders.items():
            if section == "":
                continue
            body = _stage_node_body(graph_text=graph_text, stage=stage)
            if body is None:
                continue
            prompt = _prompt_path(body=body)
            if prompt is None:
                return f'workflow stage {stage} declares no prompt="@..." attribute for its rider'
            destination = payload_dir / prompt
            if not destination.is_file():
                return f"workflow prompt {prompt} for stage {stage} is missing"
            _ = destination.write_text(
                section + "\n" + destination.read_text(encoding="utf-8"), encoding="utf-8"
            )
    except OSError as error:
        return str(error)
    return None


def _stage_node_body(*, graph_text: str, stage: str) -> str | None:
    """Read one stage's attribute body from a copied workflow graph, if declared."""
    pattern = rf"(?ms)^\s*{re.escape(stage)}\s*\[(?P<body>[^\]]*)\]"
    match = re.search(pattern, graph_text)
    return None if match is None else match.group("body")


def _prompt_path(*, body: str) -> Path | None:
    """Read the relative prompt path from one node's attribute body."""
    prompt = re.search(r'prompt\s*=\s*"@(?P<path>[^"]+)"', body)
    return None if prompt is None else Path(prompt.group("path"))
