"""The apply phase's filing plan: one published line, parsed back into a cut.

WHY A PLAN CROSSES THE BOUNDARY RATHER THAN A LEDGER WRITE. The apply phase of
the ratified two-phase groom cut (`SPECIFICATION/contracts.md` section
"Grooming and slice-size calibration" -> "Consensus-gated automated groom cut")
runs in a factory sandbox, and a factory sandbox is deliberately given NO
ledger credential: `_dispatcher_overlay` builds the run-scoped environment from
the model and forge tokens and nothing else, and the credential wrapper a
`bd` call would fall back to is a HOST path that does not exist in the
container. So an apply node that FILES reaches for a secret the sandbox is
designed never to hold, and no retry can change that.

The clause does not require the filing to execute in the sandbox. Every MUST
in it constrains WHAT is filed and HOW -- via the capture path, with dependency
edges linked, spec-change slices routed to `propose-change`, the original
regroomed-out -- and the same clause already assigns a ledger write to the
Dispatcher on the propose side ("when the Dispatcher journals that termination
it MUST record the draft on the item as a ledger comment"). So the run PRODUCES
the cut and the Dispatcher PERFORMS it, on the side that legitimately holds the
tenant credential. Projecting `BEADS_DOLT_PASSWORD` into a groom sandbox was
the alternative and is rejected outright: it would hand a tenant-write
credential to an agent-driven container to save a seam the Dispatcher already
has.

WHY THE ENCODING IS ONE LINE, in the draft's own grammar. The plan reaches the
Dispatcher over the channel the propose phase's draft already reaches it on --
the terminated run's needs-human sentinel, which is a stderr LINE, and whose
reader returns the text following the sentinel ON THAT LINE. That channel is
the one MEASURED to survive to `fabro inspect`; a plan spanning several lines
would arrive truncated to its first, silently. Reusing the draft's ` ;; `
between records and ` | ` between fields means an operator who has read a
draft comment can read a plan, and means the run has one encoding to get right
rather than two.

WHY THE HEADER RECORD CARRIES THE APPROVAL. The filing seam refuses a call
carrying no approval record naming the approver identity and the route the
approval arrived on, so those two values have to cross the boundary WITH the
cut. They are read off the approving answer comment by the run and written into
the plan's first record, which is also what makes the plan self-identifying:
the leading marker is how the Dispatcher tells an apply phase's plan from a
propose phase's draft on the one shared channel.

A MALFORMED PLAN IS REFUSED, NEVER REPAIRED. Every parse failure raises
`GroomDraftError` rather than dropping the offending field, because a plan
missing a repo target or a tier is a cut the reviewer approved in a shape this
parser cannot reproduce, and filing a guessed-at version of it would file
something no human ever saw.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands.groom import CandidateSlice
from livespec_orchestrator_beads_fabro.errors import GroomDraftError

__all__: list[str] = [
    "GROOM_PLAN_MARKER",
    "GroomFilingPlan",
    "is_groom_filing_plan",
    "parse_groom_filing_plan",
]

# The plan's leading token, and the whole discriminator between the two phases'
# publications on the shared sentinel channel. It deliberately echoes
# `_dispatcher_groom_draft.GROOM_DRAFT_COMMENT_MARKER`'s shape without being it:
# the two must never be confused, because recording a PLAN as a draft comment
# would land a fresh draft after the approval and thereby invalidate the very
# consent the plan was filed under.
GROOM_PLAN_MARKER = "livespec-groom-plan"

_RECORD_SEPARATOR = ";;"
_FIELD_SEPARATOR = "|"
_ASSIGNMENT = "="
_APPROVER_FIELD = "approver"
_ROUTE_FIELD = "route"
_TITLE_FIELD = "slice"
_TIER_FIELD = "tier"
_REPO_FIELD = "repo"
_ACCEPTANCE_FIELD = "acceptance"
_SCOPE_FIELD = "scope"
_BLOCKERS_FIELD = "blockers"
_SPEC_FIELD = "spec"
# The two autonomy tiers the groom front-end drafts, spelled as the filing seam
# spells them so the plan needs no translation table on the way in.
_TIERS = ("factory", "human-gated")
# What a slice with no blockers writes. Spelled rather than left empty because
# an empty value and an omitted field are the same observation to a reader, and
# "this slice is a root of the layering" is worth saying out loud.
_NO_BLOCKERS = "none"
_BLOCKER_SEPARATOR = ","
_YES = "yes"


@dataclass(frozen=True, kw_only=True)
class GroomFilingPlan:
    """One approved cut, as the terminated apply run published it.

    `approver` and `route` are the approval record's two fields, read by the
    run off the approving answer comment rather than synthesized: an invented
    identity attributes a maintainer-tier mutation to someone who never
    approved it, which is worse than the refusal the filing seam would
    otherwise raise.
    """

    approver: str
    route: str
    slices: tuple[CandidateSlice, ...]


def is_groom_filing_plan(*, text: str) -> bool:
    """Whether this published line is an apply phase's plan rather than a draft.

    Kept separate from the parse so a caller can discriminate the two phases
    WITHOUT having to treat a malformed plan as "not a plan". The distinction
    matters: an unrecognised draft is recorded on the ledger, and recording a
    malformed plan that way would invalidate the approval it was filed under.
    """
    return _head(text=text) == GROOM_PLAN_MARKER


def parse_groom_filing_plan(*, text: str) -> GroomFilingPlan:
    """Parse a published plan line, refusing anything it cannot reproduce exactly.

    Raises `GroomDraftError` naming the first defect. The caller has already
    established the line IS a plan via `is_groom_filing_plan`; a line that is
    not one is itself a defect here rather than a `None`, because reaching this
    function with a draft means the discrimination above went wrong and that is
    worth saying rather than silently returning nothing.
    """
    records = tuple(part.strip() for part in text.split(_RECORD_SEPARATOR))
    header = _header_fields(record=records[0])
    approver = header.get(_APPROVER_FIELD, "")
    route = header.get(_ROUTE_FIELD, "")
    if approver == "" or route == "":
        raise GroomDraftError(
            detail=(
                "the filing plan's header names no approver or no route "
                f"(fields: {', '.join(sorted(header)) if header else 'none'})"
            )
        )
    slices = tuple(_slice_of(record=record) for record in records[1:] if record != "")
    if slices == ():
        raise GroomDraftError(detail="the filing plan names no slice")
    return GroomFilingPlan(approver=approver, route=route, slices=slices)


def _head(*, text: str) -> str:
    """The plan's leading token: the first field of the first record."""
    first = text.split(_RECORD_SEPARATOR, 1)[0]
    return first.split(_FIELD_SEPARATOR, 1)[0].strip()


def _header_fields(*, record: str) -> dict[str, str]:
    entries = tuple(entry.strip() for entry in record.split(_FIELD_SEPARATOR))
    if entries[0].strip() != GROOM_PLAN_MARKER:
        raise GroomDraftError(detail=f"the published line does not open with {GROOM_PLAN_MARKER!r}")
    return _fields(entries=entries[1:], record=record)


def _fields(*, entries: tuple[str, ...], record: str) -> dict[str, str]:
    """One record's `key=value` fields, refusing an entry carrying no assignment."""
    parsed: dict[str, str] = {}
    for entry in entries:
        if entry == "":
            continue
        if _ASSIGNMENT not in entry:
            raise GroomDraftError(
                detail=f"filing-plan field {entry!r} carries no '=' in record {record!r}"
            )
        key, _, value = entry.partition(_ASSIGNMENT)
        parsed[key.strip()] = value.strip()
    return parsed


def _slice_of(*, record: str) -> CandidateSlice:
    """One slice record, with every field the filing seam gates on required.

    `scope` becomes the slice's description and `acceptance` its acceptance;
    both are demanded rather than defaulted, because a slice filed with an
    empty acceptance parses to zero gradeable assertions and is later refused
    at dispatch — a failure that would surface long after the cut was approved.
    """
    fields = _fields(
        entries=tuple(entry.strip() for entry in record.split(_FIELD_SEPARATOR)), record=record
    )
    title = fields.get(_TITLE_FIELD, "")
    tier = fields.get(_TIER_FIELD, "")
    repo_target = fields.get(_REPO_FIELD, "")
    acceptance = fields.get(_ACCEPTANCE_FIELD, "")
    scope = fields.get(_SCOPE_FIELD, "")
    if title == "":
        raise GroomDraftError(detail=f"filing-plan record {record!r} names no slice title")
    if tier not in _TIERS:
        raise GroomDraftError(
            detail=f"slice {title!r} names tier {tier!r}; expected one of {', '.join(_TIERS)}"
        )
    for name, value in (
        (_REPO_FIELD, repo_target),
        (_ACCEPTANCE_FIELD, acceptance),
        (_SCOPE_FIELD, scope),
    ):
        if value == "":
            raise GroomDraftError(detail=f"slice {title!r} has an empty {name}")
    return CandidateSlice(
        title=title,
        description=scope,
        acceptance=acceptance,
        autonomy_tier=tier,
        repo_target=repo_target,
        depends_on=_blockers(raw=fields.get(_BLOCKERS_FIELD, _NO_BLOCKERS)),
        is_spec_change=fields.get(_SPEC_FIELD, "") == _YES,
    )


def _blockers(*, raw: str) -> tuple[str, ...]:
    """The earlier-slice title handles this slice is blocked by, if any."""
    if raw in ("", _NO_BLOCKERS):
        return ()
    return tuple(handle.strip() for handle in raw.split(_BLOCKER_SEPARATOR) if handle.strip() != "")
