"""Resolving ONE pass's availability wait: the committed dial, then the value.

The impure half of `_acp_availability_wait`, split pure-from-impure the usual
way in this tree. That module decides WHEN an item whose admission-required
chain is empty is looked at again, as a pure function of the verdict plus an
interval; this one reads the interval off the target repository and hands it
over.

THE READ IS SKIPPED WHOLE WHEN NOTHING IS WAITING, and that early return is the
module's only branch for a reason. A viable verdict is the common case -- every
pass of every healthy repository -- and its wait cannot exist, so a
configuration read there would spend a file read per pass on a question whose
answer cannot change anything, and would additionally let an unreadable
`.livespec.jsonc` surface as a wait fault on a pass that was never going to
refuse.

THE INTERVAL IS COMMITTED CONFIGURATION, SO IT IS RESOLVED ONCE PER PASS, by
the caller, exactly as `_dispatcher_admission_eligibility` resolves the adopted
assertion-count ceiling and the dispatch's rendered candidates once per pass:
the answer belongs to the repository rather than to any candidate, and every
refused row of one wave reports the same instant. A per-row resolution would
re-read one file per candidate to reach the identical answer, and two rows of
one wave could then report two different instants if the file changed between
them.

AN UNREADABLE DIAL FALLS BACK TO THE RATIFIED DEFAULT rather than refusing.
This is NOT the fail-open direction: the wait is a schedule, not a gate -- the
dispatch is already refused by the empty chain, and the only thing at stake is
which instant the record names. Refusing here would replace an honest refusal
carrying a slightly-wrong instant with no refusal record at all, which is
strictly less information about an item that is waiting either way. The
unreadable configuration is the business of
`_dispatcher_admission_eligibility`'s own configuration refusal, which runs on
the same pass and reports it as the repository fault it is.
"""

from __future__ import annotations

from pathlib import Path

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._acp_availability_wait import (
    AvailabilityWait,
    schedule_availability_wait,
)
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_CREDENTIAL_REPROBE_INTERVAL_SECONDS,
    resolve_credential_reprobe_interval_seconds,
)

__all__: list[str] = [
    "resolve_availability_wait",
]


def resolve_availability_wait(
    *,
    repo: Path,
    verdict: AcpPreflightVerdict,
    now_iso: str,
) -> AvailabilityWait | None:
    """This pass's scheduled reevaluation, or `None` when nothing is waiting."""
    if not verdict.exhausted:
        return None
    interval = unsafe_perform_io(
        resolve_credential_reprobe_interval_seconds(cwd=repo).value_or(
            DEFAULT_CREDENTIAL_REPROBE_INTERVAL_SECONDS
        )
    )
    return schedule_availability_wait(
        verdict=verdict, now_iso=now_iso, reprobe_interval_seconds=interval
    )
