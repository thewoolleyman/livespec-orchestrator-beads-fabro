"""Pure spec-next candidate adaptation for needs-attention."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any, cast

from livespec_runtime.attention_item import AttentionUrgency
from livespec_runtime.needs_attention import SpecNextOutput

from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "adapt_top_candidate",
    "candidate_urgency",
    "spec_output_from_candidate",
]

_NON_ACTIONABLE_ACTIONS = frozenset(("", "none"))


def candidate_urgency(*, value: object) -> AttentionUrgency:
    """Coerce a candidate's `urgency` to the attention scale, defaulting medium."""
    if value == "high":
        return "high"
    if value == "low":
        return "low"
    return "medium"


def spec_output_from_candidate(*, candidate: object, project_root: Path) -> SpecNextOutput | None:
    """Adapt one spec-`next` candidate into a SpecNextOutput, or None if inert.

    A candidate is inert when it is not an object or its `action` is missing /
    empty / `"none"` — the caller skips it and tries the next-ranked candidate.
    """
    if not isinstance(candidate, dict):
        return None
    mapping = cast("dict[str, Any]", candidate)
    action = mapping.get("action")
    if not isinstance(action, str) or action in _NON_ACTIONABLE_ACTIONS:
        return None
    reason = mapping.get("reason")
    summary = f"Spec-side {action} is ready."
    if isinstance(reason, str) and reason != "":
        summary = reason
    target = mapping.get("target")
    spec_target = "SPECIFICATION"
    if isinstance(target, str) and target != "":
        spec_target = target
    return SpecNextOutput(
        op=action,
        spec_target=spec_target,
        summary=summary,
        urgency=candidate_urgency(value=mapping.get("urgency")),
        # The handoff mirrors the repo's `codex exec livespec:<op>` convention
        # (see `_plan_threads`) but names the ACTUAL ranked op — revise /
        # propose-change / critique / prune-history — never `next`, so a human
        # runs the recommended spec action directly instead of re-ranking.
        command=f"codex exec livespec:{action} --project-root {_quote(path=project_root)}",
    )


def adapt_top_candidate(*, stdout: str, project_root: Path) -> SpecNextOutput | None:
    """Adapt the top NON-`none` candidate from spec-`next` stdout, or None.

    Returns None for unparseable stdout, a non-object payload, a missing /
    non-list `candidates`, an empty ranking, or a ranking with only inert
    (`none`) candidates.
    """
    payload = parse_json(text=stdout)
    if isinstance(payload, JsonParseFailure):
        return None
    if not isinstance(payload, dict):
        return None
    candidates = cast("dict[str, Any]", payload).get("candidates")
    if not isinstance(candidates, list):
        return None
    for candidate in cast("list[Any]", candidates):
        output = spec_output_from_candidate(candidate=candidate, project_root=project_root)
        if output is not None:
            return output
    return None


def _quote(*, path: Path) -> str:
    return shlex.quote(str(path))
