"""The typed causal recovery attempt and its consumption, as ledger comments.

A recovery attempt is evidence, never prose: it names the prior run history,
the measured diagnosis, the executable operation and the execution evidence.
Both records are ledger comments because the ledger is the one store every
dispatching host shares; a journal on one host could not stop a second host
replaying a spent attempt.  Comments are append-only, so a consumption can never
be edited away and a spent attempt id stays spent.

Neither record carries a deadline field.  The original obligation deadline is
read from the plan authority chain alone, which is how a recovery cannot
postpone it.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_progress import (
    RedispatchRecovery,
)

__all__: list[str] = [
    "CONSUMED_MARKER",
    "RECOVERY_MARKER",
    "consumed_attempt_ids",
    "parse_recovery_comments",
    "render_consumed_comment",
    "render_recovery_comment",
]

RECOVERY_MARKER = "livespec-redispatch-recovery-attempt"
CONSUMED_MARKER = "livespec-redispatch-recovery-consumed"

_ATTEMPT_ID = "attempt_id"
_PRIOR_RUN_IDS = "prior_run_ids"
_TEXT_FIELDS = ("diagnosis", "operation", "execution_evidence")


def render_recovery_comment(*, recovery: RedispatchRecovery) -> str:
    """The comment a recorded recovery attempt is written as."""
    payload = {
        _ATTEMPT_ID: recovery.attempt_id,
        _PRIOR_RUN_IDS: list(recovery.prior_run_ids),
        "diagnosis": recovery.diagnosis,
        "operation": recovery.operation,
        "execution_evidence": recovery.execution_evidence,
    }
    return f"{RECOVERY_MARKER}\n{json.dumps(payload, sort_keys=True)}"


def render_consumed_comment(*, attempt_id: str) -> str:
    """The comment that spends one recovery attempt id for good."""
    return f"{CONSUMED_MARKER}\n{json.dumps({_ATTEMPT_ID: attempt_id})}"


def parse_recovery_comments(*, bodies: Sequence[str]) -> tuple[RedispatchRecovery, ...]:
    """Every well-formed recovery attempt, in the order it was recorded.

    A malformed body is dropped rather than half-read: a partial record would be
    prose posing as a typed attempt.
    """
    recoveries: list[RedispatchRecovery] = []
    for body in bodies:
        payload = _payload(body=body, marker=RECOVERY_MARKER)
        recovery = None if payload is None else _recovery(payload=payload)
        if recovery is not None:
            recoveries.append(recovery)
    return tuple(recoveries)


def consumed_attempt_ids(*, bodies: Sequence[str]) -> frozenset[str]:
    """Every recovery attempt id some earlier dispatch already spent."""
    spent: set[str] = set()
    for body in bodies:
        payload = _payload(body=body, marker=CONSUMED_MARKER)
        attempt_id = None if payload is None else payload.get(_ATTEMPT_ID)
        if isinstance(attempt_id, str):
            spent.add(attempt_id)
    return frozenset(spent)


def _payload(*, body: str, marker: str) -> dict[str, object] | None:
    head, _, rest = body.partition("\n")
    if head.strip() != marker:
        return None
    try:
        parsed: object = json.loads(rest)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return cast("dict[str, object]", parsed)


def _recovery(*, payload: dict[str, object]) -> RedispatchRecovery | None:
    attempt_id = payload.get(_ATTEMPT_ID)
    prior = payload.get(_PRIOR_RUN_IDS)
    texts = [payload.get(name) for name in _TEXT_FIELDS]
    if not isinstance(attempt_id, str) or not isinstance(prior, list):
        return None
    run_ids = cast("list[object]", prior)
    if not all(isinstance(run_id, str) for run_id in run_ids):
        return None
    if not all(isinstance(text, str) for text in texts):
        return None
    diagnosis, operation, evidence = cast("list[str]", texts)
    return RedispatchRecovery(
        attempt_id=attempt_id,
        prior_run_ids=tuple(cast("list[str]", run_ids)),
        diagnosis=diagnosis,
        operation=operation,
        execution_evidence=evidence,
    )
