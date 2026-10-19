"""The factory-only anchor for a run that republished after its latest proof."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import (
    RESUMED_AT_PROOF_CAPTURE,
    SOURCE_FACTORY_RUN,
    ResumeAnchor,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_checkpoints import (
    fabro_inspect_checkpoints,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import fabro_inspect_record

__all__: list[str] = ["republication_anchor"]

_PUBLISH_DRAFT = "publish_draft"
_PROOF_CAPTURE = "proof_capture"
_SUCCEEDED = "succeeded"
_ANCESTRY_TIMEOUT_SECONDS = 60.0


def republication_anchor(
    *,
    provisional: ResumeAnchor | None,
    current_head: str | None,
    payload: object | None,
    repo: Path,
    runner: CommandRunner,
) -> ResumeAnchor | None:
    """Return the fresh-capture anchor only when this run itself republished it."""
    if provisional is None or current_head is None or provisional.head == current_head:
        return None
    if not _republished_to_capture(payload=payload, current_head=current_head):
        return None
    ancestry = runner.run(
        argv=["git", "merge-base", "--is-ancestor", provisional.head, current_head],
        cwd=repo,
        timeout_seconds=_ANCESTRY_TIMEOUT_SECONDS,
    )
    if ancestry.exit_code != 0:
        return None
    return ResumeAnchor(
        record=None,
        run_id=provisional.run_id,
        head=current_head,
        resumed_at=RESUMED_AT_PROOF_CAPTURE,
        source=SOURCE_FACTORY_RUN,
    )


def _republished_to_capture(*, payload: object | None, current_head: str) -> bool:
    """Whether the terminal factory record proves a post-proof republish."""
    record = fabro_inspect_record(payload=payload)
    if record is None:
        return False
    checkpoints = fabro_inspect_checkpoints(record=record)
    if not checkpoints or not _ends_at_capture(checkpoint=checkpoints[-1], head=current_head):
        return False
    visits = _successful_visits(record=record)
    captures = visits[_PROOF_CAPTURE]
    publications = visits[_PUBLISH_DRAFT]
    return bool(captures and publications and max(publications) > max(captures))


def _ends_at_capture(*, checkpoint: dict[str, Any], head: str) -> bool:
    """The terminal checkpoint names both the republished head and fresh capture."""
    node = checkpoint.get("current_node") or checkpoint.get("next_node_id")
    return checkpoint.get("git_commit_sha") == head and node == _PROOF_CAPTURE


def _successful_visits(*, record: dict[str, Any]) -> dict[str, set[int]]:
    """Completed publication/capture visit numbers from the engine's full history."""
    visits: dict[str, set[int]] = {_PUBLISH_DRAFT: set(), _PROOF_CAPTURE: set()}
    stages: object = record.get("stages")
    if not isinstance(stages, dict):
        return visits
    typed_stages = cast("Mapping[str, object]", stages)
    for name, detail in typed_stages.items():
        node, marker, ordinal = name.partition("@")
        if (
            node in visits
            and marker
            and ordinal.isdigit()
            and isinstance(detail, dict)
            and cast("Mapping[str, object]", detail).get("state") == _SUCCEEDED
        ):
            visits[node].add(int(ordinal))
    return visits
