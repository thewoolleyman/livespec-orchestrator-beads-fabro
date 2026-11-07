"""Durable per-merge drift verdict receipts on the detection-coverage anchor.

The drift frontier may stop at one held finding while a later merge was already
judged.  The next job still has to revisit that later merge for filing, but it
must not spend another model call while the ratified specification is the same.
These append-only receipts make that distinction durable across job processes.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

from livespec_runtime.spec_stated import SpecStatedVerdict

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError, BeadsMappingError

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "DRIFT_VERDICT_MARKER_PREFIX",
    "record_drift_verdict",
    "recorded_drift_verdict",
]

DRIFT_VERDICT_MARKER_PREFIX = "livespec-drift-verdict: "


def record_drift_verdict(
    *,
    path: StoreConfig | None,
    anchor: str | None,
    merge: str,
    spec_revision: str,
    verdict: SpecStatedVerdict,
) -> None:
    """Append the one receipt that lets a later job reuse `verdict`."""
    if path is None or anchor is None or anchor.strip() == "":
        return
    body = {
        "merge": merge,
        "spec_revision": spec_revision,
        "kind": verdict.kind,
        "stated_by": list(verdict.stated_by),
        "generalization_target": verdict.generalization_target,
        "rationale": verdict.rationale,
    }
    make_beads_client(config=path).add_comment(
        issue_id=anchor,
        body=DRIFT_VERDICT_MARKER_PREFIX + json.dumps(body, sort_keys=True),
    )


def recorded_drift_verdict(
    *,
    path: StoreConfig | None,
    anchor: str | None,
    merge: str,
    spec_revision: str,
) -> SpecStatedVerdict | None:
    """Return the newest usable receipt for this merge and spec revision."""
    if path is None or anchor is None or anchor.strip() == "":
        return None
    comments = attempt(
        action=lambda: read_work_item_comments(path=path, work_item_id=anchor),
        exceptions=(BeadsCommandError, BeadsMappingError),
    )
    if isinstance(comments, AttemptFailure):
        return None
    for comment in reversed(comments):
        if not comment.text.startswith(DRIFT_VERDICT_MARKER_PREFIX):
            continue
        verdict = _decode(payload=comment.text.removeprefix(DRIFT_VERDICT_MARKER_PREFIX))
        if verdict is not None and verdict[0] == (merge, spec_revision):
            return verdict[1]
    return None


def _decode(*, payload: str) -> tuple[tuple[str, str], SpecStatedVerdict] | None:
    """Read one receipt, skipping malformed historical records fail-soft."""
    parsed = parse_json(text=payload)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return None
    fields = cast("dict[str, Any]", parsed)
    merge = fields.get("merge")
    revision = fields.get("spec_revision")
    kind = fields.get("kind")
    stated_by = fields.get("stated_by")
    target = fields.get("generalization_target")
    rationale = fields.get("rationale")
    headings = cast("list[object]", stated_by) if isinstance(stated_by, list) else []
    if (
        not isinstance(merge, str)
        or not isinstance(revision, str)
        or kind not in {"stated", "partial", "unstated"}
        or not isinstance(stated_by, list)
        or not all(isinstance(heading, str) for heading in headings)
        or (target is not None and not isinstance(target, str))
        or not isinstance(rationale, str)
    ):
        return None
    return (
        (merge, revision),
        SpecStatedVerdict(
            kind=cast("Any", kind),
            stated_by=tuple(cast("list[str]", headings)),
            generalization_target=target,
            rationale=rationale,
        ),
    )
