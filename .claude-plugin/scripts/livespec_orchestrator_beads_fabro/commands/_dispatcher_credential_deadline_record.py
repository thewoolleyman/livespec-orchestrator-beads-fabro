"""The one durable record written when credential-use reaches its deadline.

The guard can stop a coding agent only inside the sandbox.  This record is the
host-side account that turns that stop (or a refused launch) into a recoverable
dispatch ending: it preserves the exact deadline and the queue time that was
actually consumed, rather than recasting the ending as an ordinary failure.
"""

from __future__ import annotations

__all__: list[str] = [
    "CREDENTIAL_DEADLINE_REACHED_STAGE",
    "KILLED_MID_NODE_CAUSE",
    "LAUNCH_REFUSED_CAUSE",
    "QUEUE_EXCEEDED_CAUSE",
    "credential_deadline_record",
]

CREDENTIAL_DEADLINE_REACHED_STAGE = "credential-use-deadline-reached"
QUEUE_EXCEEDED_CAUSE = "queue-exceeded"
LAUNCH_REFUSED_CAUSE = "launch-refused"
KILLED_MID_NODE_CAUSE = "killed-mid-node"


def credential_deadline_record(  # noqa: PLR0913 - each terminal fact is independently observed.
    *,
    work_item_id: str,
    dispatch_id: str | None,
    run_id: str,
    factory: str,
    executing_stage: str | None,
    projection_epoch: int,
    deadline_epoch: int,
    observed_epoch: int,
    governing_figure: str,
    preserved_pointer: str,
    cause: str,
    published_head: str | None,
) -> dict[str, object]:
    """Render the deadline terminal exactly once, after preservation succeeds.

    Queue time is clamped at zero because a host clock reading that predates the
    projection is not negative queueing; it is an unavailable measurement in
    the conservative direction.  The record still carries both instants so an
    operator can diagnose the skew without inventing elapsed time.
    """
    return {
        "stage": CREDENTIAL_DEADLINE_REACHED_STAGE,
        "work_item_id": work_item_id,
        "dispatch_id": dispatch_id,
        "run_id": run_id,
        "factory": factory,
        "executing_stage": executing_stage,
        "projection_epoch": projection_epoch,
        "credential_use_deadline_epoch": deadline_epoch,
        "queue_time_consumed_seconds": max(0, observed_epoch - projection_epoch),
        "governing_figure": governing_figure,
        "preserved_pointer": preserved_pointer,
        "cause": cause,
        "published_head": published_head,
    }
