"""Apply the semantic pre-admission verdict at the ledger's readiness boundary."""

from __future__ import annotations

from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro._pre_admission_dod import judge_before_admission
from livespec_orchestrator_beads_fabro._pre_admission_verdict import parse_judgement
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "pre_admission_hold",
]


def pre_admission_hold(*, path: StoreConfig, item: WorkItem) -> str | None:
    """Return the needs-human finding, or allow the existing admission route.

    Unavailable judgements cannot create a hold: the in-run gate remains the
    backstop. Every readiness writer calls this same decision boundary.
    """
    result = judge_before_admission(path=path, item=item).bind_result(
        lambda response: parse_judgement(response=response)
    )
    if not is_successful(result):
        return None
    return unsafe_perform_io(result.unwrap()).failure_reason
