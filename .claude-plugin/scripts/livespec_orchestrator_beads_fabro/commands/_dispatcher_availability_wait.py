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

THE RECORDED SCHEDULE IS READ FROM THE JOURNAL, WHICH IS WHAT SURVIVES A
RESTART. Nothing is kept between passes: the instant a prior pass scheduled is
recovered from the append-only journal on disk, so a Dispatcher started afresh
reads the same instant its predecessor recorded. An unreadable or absent
journal reconstructs NOTHING rather than a plausible schedule, and this pass
then simply supersedes nothing -- the item is refused and rescheduled either
way, because admission is decided from live evidence, never from the recorded
instant. That is why the reconstruction cannot gate a pass: an operator
clearance "MUST make the affected wait eligible for immediate reevaluation",
and a gate keyed on a recorded instant would hold the item past it.

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
    recorded_availability_wait,
    schedule_availability_wait,
)
from livespec_orchestrator_beads_fabro.commands._acp_journal_records import journal_records
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_CREDENTIAL_REPROBE_INTERVAL_SECONDS,
    resolve_credential_reprobe_interval_seconds,
)

__all__: list[str] = [
    "reconstructed_availability_wait",
    "resolve_availability_wait",
]


def resolve_availability_wait(
    *,
    repo: Path,
    verdict: AcpPreflightVerdict,
    now_iso: str,
    journal_path: Path | None,
) -> AvailabilityWait | None:
    """This pass's scheduled reevaluation, or `None` when nothing is waiting.

    The returned wait carries the schedule a prior pass recorded, so the
    refusal can say which instant this evaluation superseded and whether it
    had already lapsed.
    """
    if not verdict.exhausted:
        return None
    interval = unsafe_perform_io(
        resolve_credential_reprobe_interval_seconds(cwd=repo).value_or(
            DEFAULT_CREDENTIAL_REPROBE_INTERVAL_SECONDS
        )
    )
    return schedule_availability_wait(
        verdict=verdict,
        now_iso=now_iso,
        reprobe_interval_seconds=interval,
        recorded=reconstructed_availability_wait(journal_path=journal_path),
    )


def reconstructed_availability_wait(*, journal_path: Path | None) -> AvailabilityWait | None:
    """The schedule the journal on disk records, or `None` when it records none.

    The read goes through the ACP feature's SHARED journal reader rather than
    a fourth private copy of it, for the reason that module's own docstring
    gives: the three existing ledgers in this one file are each a forward fold
    over it, and separate copies drift -- the first divergence anyone notices
    being one ledger tolerating a truncated line another had started raising
    on. It also supplies the two postures this read needs unchanged: an absent
    or unreadable journal yields no records rather than an error, and a line
    that does not parse is skipped, because the journal is shared with every
    other dispatcher stage and one crash mid-append must not make a recorded
    schedule unreadable.
    """
    return recorded_availability_wait(records=journal_records(journal_path=journal_path))
