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
    A declared node whose copied prompt is absent is instead a materialization
    failure because the graph would ask Fabro to read a missing file.
    """
    try:
        graph_text = graph.read_text(encoding="utf-8")
        for stage, section in stage_riders.items():
            if section == "":
                continue
            prompt = _stage_prompt_path(graph_text=graph_text, stage=stage)
            if prompt is None:
                continue
            destination = payload_dir / prompt
            if not destination.is_file():
                return f"workflow prompt {prompt} for stage {stage} is missing"
            _ = destination.write_text(
                section + "\n" + destination.read_text(encoding="utf-8"), encoding="utf-8"
            )
    except OSError as error:
        return str(error)
    return None


def _stage_prompt_path(*, graph_text: str, stage: str) -> Path | None:
    """Read one stage's relative prompt path from a copied workflow graph."""
    pattern = rf"(?ms)^\s*{re.escape(stage)}\s*\[(?P<body>[^\]]*)\]"
    match = re.search(pattern, graph_text)
    if match is None:
        return None
    prompt = re.search(r'prompt\s*=\s*"@(?P<path>[^"]+)"', match.group("body"))
    return None if prompt is None else Path(prompt.group("path"))
