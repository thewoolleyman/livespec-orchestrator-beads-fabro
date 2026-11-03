"""Value and refusal for the cohesive `disposed` supersession cause."""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._plan_carrier_gate import CLOSED_STATUS

__all__: list[str] = [
    "DisposedEvidence",
    "SupersessionRefusal",
    "disposed_refusal",
]


@dataclass(frozen=True, kw_only=True)
class DisposedEvidence:
    target_id: str
    status: str
    resolution: str | None
    is_plan_child: bool


@dataclass(frozen=True, kw_only=True)
class SupersessionRefusal:
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
