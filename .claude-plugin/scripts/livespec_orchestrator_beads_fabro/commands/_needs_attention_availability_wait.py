"""The attention row an admission-required ACP chain's own wait produces.

`SPECIFICATION/contracts.md`, among the orchestrator-owned attention facts,
closes its enumerated wait list with "an item waiting because an
admission-required ACP chain has no eligible candidate ... including because of
live holds, outstanding post-expiry confirmation, unavailable evidence,
admission-time credential-probe skips, or admission session-headroom skips,
which likewise stays `ready`", and then states what that row owes: "The wait
item MUST name the governing condition and scheduled reevaluation instant."

NOTHING COMPOSED THAT ROW, AND ITS ABSENCE WAS THE QUIET KIND. The wait is
already derived — `resolve_availability_wait` has computed the condition and
the instant on every containment refusal since v127 — but the only consumer was
the dispatch journal, which an operator reads after being told to look. On the
awareness surface the item simply rests in `ready`: nothing is stranded, no
claim is held, no capacity is pressured, and the idle-factory row deliberately
CLEARS, because a factory held back by an exhausted chain is waiting rather
than idle. So the one surface built to report every wait reported this one as
nothing at all.

THE ROW IS SCOPED PER WAITING ITEM, exactly as the legacy
provider-exhaustion lane beside it is. The clause's subject is "an item
waiting", and the ready items a chain exhaustion holds are the population it
holds: a single repository-wide row would have no `work_item` to point at and
would make the one wait that holds twenty items look like the one that holds
one.

THE HANDOFF IS CHOSEN BY THE GOVERNING CONDITION AND NEVER BY WHAT THE WAIT
HAPPENS TO CARRY. "It MUST offer an applicable attributed clearance valve when
a live hold is the target: exact scope/key clearance for current records, or
the legacy provider valve for legacy records. Otherwise its handoff MUST
inspect the recorded wait and unavailable or failed observation; it MUST NOT
advertise clearance of a nonexistent live hold." The condition is the one fact
that says which record is the TARGET, and `AvailabilityWait.holds` is not: it
collects every live hold that emptied ANY admission-required chain, so a node
emptied by an outstanding confirmation can arrive beside a SIBLING node's typed
hold — and clearing that hold releases a chain this row is not about, leaving
the named node exactly as empty as before. Keying on the condition is also what
makes the three no-live-hold conditions structurally unable to reach a
clearance arm rather than merely unlikely to.

NO AVAILABILITY WAIT USES `resolve-blocked`, which the same clause states
outright, and nothing here advertises one: the two clearance commands retire
records and the third reads the journal. The item stays `ready` throughout, so
there is no blocked reason for a valve to resolve.

NOTHING HERE PROBES A CREDENTIAL, TAKES A CONFIRMATION TURN, OR MUTATES. The
verdict comes from the shared `acp_chain_preflight_verdict`, which supplies no
probe at all, and the only other read is the repository's own committed
re-probe cadence. That is what lets two compositions over one unchanged store
render identical bytes — and the instant they render is a function of the
availability evidence rather than of the clock, because `_reevaluate_at`
answers the earliest governing expiry whenever one parses.
"""

from __future__ import annotations

from pathlib import Path

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef

from livespec_orchestrator_beads_fabro.commands._acp_availability_wait import (
    AvailabilityWait,
    GoverningHold,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_preflight import (
    LEGACY_HOLD_SKIP,
    TYPED_HOLD_SKIP,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    resolve_availability_wait,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import utc_now_iso
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_handoffs import (
    availability_wait_journal_command,
    clear_acp_availability_hold_command,
    clear_provider_exhaustion_command,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_waits import (
    acp_chain_preflight_verdict,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "availability_wait_handoff",
    "availability_wait_items",
]

# The orchestrator-owned `hygiene:<type>:<resource>` form, whose resource is the
# waiting work-item. `acp-availability-wait` names the mechanism rather than the
# condition, because the condition varies per evaluation while the stable id
# must not -- a row whose id moved when a typed hold expired into an outstanding
# confirmation would read downstream as one fact clearing and another appearing.
_WAIT_TYPE = "acp-availability-wait"

# What the summary renders where the wait names NO admission-required node: the
# unavailable-evidence arm, which is a real bounded wait with no node to
# attribute it to. Spelled rather than left empty, because an empty field reads
# as a node id that did not survive.
_NO_NODE = "none"


def availability_wait_items(
    *,
    project_root: Path,
    repo: str,
    items: list[WorkItem],
    now_iso: str | None = None,
) -> list[AttentionItem]:
    """One row per ready item an admission-required chain's wait holds.

    Empty when nothing is waiting, which is every repository whose chains still
    hold a candidate and whose evidence sources all read — and every repository
    declaring no fallback configuration at all, which short-circuits inside the
    shared verdict before any graph or journal is touched.

    `now_iso` is this composition's EVALUATION TIME, and it is a parameter
    because the byte-identity requirement states it as a premise: "Identical
    ledger, capacity, configuration, availability evidence, and evaluation time
    MUST produce a byte-identical row." Where no governing hold carries an
    expiry the scheduled instant IS the cadence measured from this evaluation,
    so a lane that read only its own clock left no caller able to hold that
    premise — and two passes a second apart rendered two different rows for a
    reason the requirement explicitly excludes.

    It defaults to this pass's own clock, which is what every snapshot caller
    takes: a composition has exactly one evaluation, so reading it here is
    reading it once. The parameter exists for a caller that has ALREADY fixed
    the instant, never as a second clock.

    THE SAME INSTANT REACHES BOTH READS, which is the other half of the
    determinism. The verdict's hold liveness and the wait's cadence are two
    readings of ONE evaluation, so a clock read twice could retire a hold
    between them and report a wait derived from evidence the verdict never saw.
    """
    evaluated_at = utc_now_iso() if now_iso is None else now_iso
    wait = resolve_availability_wait(
        repo=project_root,
        verdict=acp_chain_preflight_verdict(project_root=project_root, now_iso=evaluated_at),
        now_iso=evaluated_at,
    )
    if wait is None:
        return []
    return [
        _wait_item(project_root=project_root, repo=repo, item=item, wait=wait)
        for item in items
        if item.status == "ready" and item.factory_safety is None
    ]


def availability_wait_handoff(*, project_root: Path, wait: AvailabilityWait) -> Handoff:
    """The one handoff this wait's own governing condition sanctions.

    The inspection route is the DEFAULT rather than a last resort, and the two
    clearance routes are narrow exceptions to it: an outstanding confirmation,
    an unavailable evidence source, a credential-probe skip and a headroom
    shortfall each name nothing an operator can retire, so advertising a
    clearance beside any of them would be advertising "clearance of a
    nonexistent live hold".
    """
    hold = _clearable_hold(wait=wait)
    if hold is not None:
        return Handoff(
            kind="shell",
            command=clear_acp_availability_hold_command(
                project_root=project_root,
                scope=hold.scope,
                hold_key=hold.hold_key,
                candidate_key=hold.candidate_key,
            ),
        )
    if wait.governing_condition == LEGACY_HOLD_SKIP and wait.legacy_provider is not None:
        return Handoff(
            kind="shell",
            command=clear_provider_exhaustion_command(
                project_root=project_root, provider=wait.legacy_provider
            ),
        )
    return Handoff(
        kind="shell",
        command=availability_wait_journal_command(project_root=project_root),
    )


def _clearable_hold(*, wait: AvailabilityWait) -> GoverningHold | None:
    """The live record this row's own condition makes the clearance target.

    The EARLIEST expiry wins, which is not an arbitrary tiebreak: that is the
    record `_reevaluate_at` derived the scheduled instant from, so it is the
    one whose clearance actually moves the instant the row reports. A valve
    naming a later record would advertise a clearance that changes nothing an
    operator can observe on this row.

    The remaining key components order the rest, so two compositions over one
    unchanged evidence set pick the same record whatever order the holds were
    collected in; a `candidate_key` of `None` sorts as the empty string, which
    is below every real key and keeps a domain record ahead of the candidate
    records that share its expiry.
    """
    if wait.governing_condition != TYPED_HOLD_SKIP:
        return None
    ordered = sorted(
        wait.holds,
        key=lambda hold: (hold.expires_at, hold.scope, hold.hold_key, hold.candidate_key or ""),
    )
    return ordered[0] if ordered else None


def _wait_item(
    *,
    project_root: Path,
    repo: str,
    item: WorkItem,
    wait: AvailabilityWait,
) -> AttentionItem:
    return ConformanceContext(project_root=project_root, repo=repo).candidate(
        id=f"hygiene:{_WAIT_TYPE}:{item.id}",
        kind="hygiene",
        urgency="high",
        summary=_summary(work_item=item.id, wait=wait),
        source_ref=SourceRef(repo=repo, work_item=item.id),
        handoff=availability_wait_handoff(project_root=project_root, wait=wait),
    )


def _summary(*, work_item: str, wait: AvailabilityWait) -> str:
    """Name the condition, the node and the instant, and nothing that varies.

    Deterministic by construction: every field is read off the wait, which is a
    function of the availability evidence and the committed cadence. No clock
    reading, dwell or run id appears here.
    """
    return (
        f"Work-item {work_item} stays ready while an admission-required ACP node "
        f"has no eligible candidate: governing_condition={wait.governing_condition} "
        f"admission_required_node={wait.node or _NO_NODE} "
        f"scheduled_reevaluation_at={wait.reevaluate_at}. "
        "Reevaluation is automatic and needs no human action."
    )
