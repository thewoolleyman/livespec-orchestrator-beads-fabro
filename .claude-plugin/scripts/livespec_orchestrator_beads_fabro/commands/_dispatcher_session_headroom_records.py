"""What admission RECORDS and REFUSES about one item's headroom assessment.

`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance" puts three different records on this one filter, and they
are three because they answer three questions:

- The READING record. "For each affected work-item and assessed credential, the
  Dispatcher MUST journal ... the opaque non-secret credential identity, the
  utilization and remaining-headroom percentages or an explicit unobservable
  result, and the local observation time." It is written whether or not anything
  was skipped, which is what makes a floor of `0` observable at all.
- The SELECTION record. Section "Factory-configurable ACP fallback priority" ->
  "Per-node selection": "When headroom skips an earlier candidate, the selection
  record MUST identify that candidate and reference its headroom assessment and
  governing floor; it MUST NOT represent that skip as an observed hold." So the
  skipped candidate is named with the headroom REASON token, never with a hold
  key or a cause.
- The CONTAINMENT REFUSAL. "No silent containment": a headroom-governed refusal
  "MUST additionally name the assessed credential identity, reading or explicit
  unobservable result, observation time, governing floor, and skipped candidates
  for the admission-required node lacking an eligible candidate" -- and it "MUST
  NOT invent a hold identity or expiry", which is why no hold field appears
  anywhere below.

THE REFUSAL IS A SEPARATE STAGE FROM THE CHAIN-EXHAUSTION REFUSAL, and that is
the point rather than an accident of layering. A chain emptied by observed holds
and a chain emptied by a headroom reading carry DIFFERENT fields, because they
are not governed by the same observation: the first names holds and their
expiries, the second names a reading that minted no hold. One stage carrying
both would have to leave half its fields null on every record, and a reader
could no longer tell "no hold governs this" from "the hold fields were not
written".

WHY THE SCHEDULED REEVALUATION INSTANT IS THE RE-PROBE CADENCE AND NOT A HOLD
EXPIRY. The clause routes reevaluation through the existing Per-node selection
scheduling rule: "the earliest expiry among holds emptying a chain when
applicable, otherwise after `dispatcher.credential_reprobe_interval_seconds`".
A headroom skip mints no hold, so there is no expiry to be earliest among and
the cadence is the whole answer. Reading a hold expiry here would be inventing
the identity the same clause forbids.

NOTHING HERE DECIDES ELIGIBILITY. The verdict already decided it; this module
reports what the verdict holds. That is why every function takes the verdict
rather than re-deriving a skip, and why the refusal fires only on a verdict that
is already non-viable.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol, cast

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._acp_candidate_preflight import (
    HEADROOM_SKIP,
    NodePreflight,
    SkippedCandidate,
)
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    SessionHeadroomGate,
    session_headroom_assessment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_CREDENTIAL_REPROBE_INTERVAL_SECONDS,
    resolve_credential_reprobe_interval_seconds,
)
from livespec_orchestrator_beads_fabro.effects import parse_iso_datetime

__all__: list[str] = [
    "SESSION_HEADROOM_READING_STAGE",
    "SESSION_HEADROOM_REFUSAL_STAGE",
    "SESSION_HEADROOM_SELECTION_STAGE",
    "append_session_headroom_records",
    "session_headroom_refusal",
]

SESSION_HEADROOM_READING_STAGE = "session-headroom-reading"
SESSION_HEADROOM_SELECTION_STAGE = "session-headroom-selection"
SESSION_HEADROOM_REFUSAL_STAGE = "session-headroom-refusal"

# The governing condition this containment refusal names. It is the FILTER, not
# a provider or a vendor: no allowance was observed to be gone, only measured
# too thin to start a run against.
_GOVERNING_CONDITION = "admission_session_headroom"


class _Journal(Protocol):
    def append(self, *, record: dict[str, object]) -> None:
        """Persist one journal record."""
        ...


def append_session_headroom_records(
    *, work_item_id: str, verdict: AcpPreflightVerdict, journal: _Journal
) -> None:
    """Journal this item's reading, and any per-node selection it governed.

    A verdict carrying no gate journals NOTHING, which is the whole additive
    guarantee: a repository whose nodes render no covered candidate, or a
    surface that composes a snapshot without a live usage request, reaches this
    with `session_headroom` absent and writes no line.
    """
    gate = verdict.session_headroom
    if gate is None:
        return
    journal.append(
        record={
            "stage": SESSION_HEADROOM_READING_STAGE,
            "work_item_id": work_item_id,
            **session_headroom_assessment(gate=gate),
        }
    )
    for preflight in verdict.nodes:
        record = _selection_record(work_item_id=work_item_id, preflight=preflight, gate=gate)
        if record is not None:
            journal.append(record=record)


def session_headroom_refusal(
    *,
    repo: Path,
    work_item_id: str,
    verdict: AcpPreflightVerdict,
    journal: _Journal,
    now_iso: str,
) -> DispatchOutcome | None:
    """Refuse before claim when a headroom skip emptied an admission-required node.

    Returns `None` unless the verdict is already non-viable AND a headroom skip
    is what emptied one of the nodes it reports as exhausted. Both conditions are
    load-bearing: a viable verdict refuses nothing, and a chain emptied purely by
    observed holds belongs to the chain-exhaustion refusal, which names holds and
    their expiries. Attributing that refusal here would report a vendor outage as
    a usage reading.
    """
    gate = verdict.session_headroom
    if gate is None or verdict.viable:
        return None
    emptied = _headroom_emptied_node(verdict=verdict)
    if emptied is None:
        return None
    journal.append(
        record={
            "stage": SESSION_HEADROOM_REFUSAL_STAGE,
            "work_item_id": work_item_id,
            "governing_condition": _GOVERNING_CONDITION,
            "admission_required_node": emptied.node,
            "scheduled_reevaluation_at": _reevaluation_instant(repo=repo, now_iso=now_iso),
            "skipped_candidates": _skipped_candidates(preflight=emptied),
            **session_headroom_assessment(gate=gate),
        }
    )
    return DispatchOutcome(
        work_item_id=work_item_id,
        status="failed",
        stage=SESSION_HEADROOM_REFUSAL_STAGE,
        pr_number=None,
        merge_sha=None,
        detail=(
            "session headroom refusal: no eligible candidate remains for "
            f"admission-required ACP node {emptied.node} at floor "
            f"{gate.floor}% ({_reading_label(gate=gate)})"
        ),
    )


def _selection_record(
    *, work_item_id: str, preflight: NodePreflight, gate: SessionHeadroomGate
) -> dict[str, object] | None:
    """The per-node selection record a headroom skip earlier in the chain owes.

    `None` for a node headroom skipped nothing on, and `None` for a node left
    with no candidate at all: an empty chain SELECTED nothing, so a selection
    record for it would name a candidate that will not run. That node is the
    containment refusal's subject instead.
    """
    skipped = _headroom_skips(preflight=preflight)
    if not skipped or not preflight.candidates:
        return None
    selected = preflight.candidates[0]
    identity = selected.identity
    return {
        "stage": SESSION_HEADROOM_SELECTION_STAGE,
        "work_item_id": work_item_id,
        "node": preflight.node,
        "selected_availability_key": None if identity is None else identity.availability_key,
        "selected_candidate_key": None if identity is None else identity.candidate_key,
        "skipped_candidates": _skipped_candidates(preflight=preflight),
        **session_headroom_assessment(gate=gate),
    }


def _headroom_emptied_node(*, verdict: AcpPreflightVerdict) -> NodePreflight | None:
    """The first exhausted node a headroom skip contributed to emptying.

    Exhausted nodes are walked in the verdict's own order, which is graph order,
    so the node this refusal names is deterministic across dispatches rather
    than whichever one a set happened to yield first.
    """
    for node in verdict.exhausted:
        preflight = verdict.node_preflight(node=node)
        if preflight is not None and _headroom_skips(preflight=preflight):
            return preflight
    return None


def _headroom_skips(*, preflight: NodePreflight) -> tuple[SkippedCandidate, ...]:
    """This node's candidates the headroom filter skipped, in configured order."""
    return tuple(skip for skip in preflight.skipped if skip.reason == HEADROOM_SKIP)


def _skipped_candidates(*, preflight: NodePreflight) -> list[dict[str, object]]:
    """Every candidate this node lost, each with the REASON token that lost it.

    The whole skipped set is reported rather than the headroom subset alone,
    because a node can be emptied by a hold AND a headroom reading together and
    an operator reading one of the two would mis-diagnose which to act on. The
    `reason` token is what keeps a headroom skip from reading as an observed
    hold: no hold key, no cause and no expiry is attached to one.
    """
    return [
        {
            "availability_key": skip.availability_key,
            "candidate_key": skip.candidate_key,
            "reason": skip.reason,
        }
        for skip in preflight.skipped
    ]


def _reading_label(*, gate: SessionHeadroomGate) -> str:
    """The reading, or the explicit unobservable result, as operator text."""
    remaining = gate.reading.remaining_headroom_percent
    if remaining is None:
        return f"reading unobservable: {gate.reading.unobservable_reason}"
    return f"{remaining:g}% remaining"


def _reevaluation_instant(*, repo: Path, now_iso: str) -> str:
    """When the admission loop reevaluates this wait, by the re-probe cadence.

    The instant is derived from the journal's own `Z`-suffixed form the same way
    the provider-exhaustion records derive theirs, so two refusals written in one
    pass cannot disagree about what "now" was.
    """
    interval = unsafe_perform_io(
        resolve_credential_reprobe_interval_seconds(cwd=repo).value_or(
            DEFAULT_CREDENTIAL_REPROBE_INTERVAL_SECONDS
        )
    )
    now = parse_iso_datetime(text=now_iso.removesuffix("Z") + "+00:00")
    scheduled = cast("datetime", now) + timedelta(seconds=interval)
    return scheduled.strftime("%Y-%m-%dT%H:%M:%SZ")
