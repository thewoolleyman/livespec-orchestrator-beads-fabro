"""Value and refusal for the cohesive `disposed` supersession cause."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from livespec_orchestrator_beads_fabro.commands._plan_carrier_gate import CLOSED_STATUS

__all__: list[str] = [
    "DisposedEvidence",
    "SupersessionRefusal",
    "disposed_refusal",
    "plan_membership",
]


@dataclass(frozen=True, kw_only=True)
class DisposedEvidence:
    target_id: str
    status: str
    resolution: str | None
    is_plan_child: bool


@dataclass(frozen=True, kw_only=True)
class SupersessionRefusal:
    """Why one claimed supersession is not an EVIDENCED causal supersession."""

    detail: str


def disposed_refusal(
    *, target_id: str | None, disposed: DisposedEvidence | None
) -> SupersessionRefusal | None:
    if target_id is None:
        return SupersessionRefusal(detail="a disposed supersession must name its target record")
    if disposed is None or disposed.target_id != target_id:
        return SupersessionRefusal(
            detail=f"the disposed target {target_id!r} could not be read from the obligation"
        )
    if (disposed.status == CLOSED_STATUS and disposed.resolution == "superseded") or (
        disposed.status != CLOSED_STATUS and not disposed.is_plan_child
    ):
        return None
    return SupersessionRefusal(
        detail=(
            f"the disposed target {target_id!r} is neither closed as superseded nor detached"
            " from this plan, so its cause does not verify"
        )
    )


def plan_membership(*, record: dict[str, object], epic_id: str) -> bool | None:
    """Whether the target still carries a parent-child edge to this plan.

    `None` is an edge list nobody can read, which the caller must refuse: reading
    it as "no edge" would accept unreadable evidence as proof of detachment. An
    OMITTED list is `False`, because bd omits an empty `dependencies` array. The
    two surfaces name an edge differently (`depends_on_id`/`type` on a listing,
    `id`/`dependency_type` on `bd show`), so both spellings are read.
    """
    if "dependencies" not in record:
        return False
    raw = record["dependencies"]
    if not isinstance(raw, list):
        return None
    is_child = False
    for raw_edge in cast("list[object]", raw):
        if not isinstance(raw_edge, dict):
            return None
        edge = cast("dict[str, object]", raw_edge)
        target = edge.get("depends_on_id", edge.get("id"))
        kind = edge.get("type", edge.get("dependency_type"))
        if not isinstance(target, str) or not isinstance(kind, str):
            return None
        is_child = is_child or (kind == "parent-child" and target == epic_id)
    return is_child
