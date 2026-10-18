"""The `resume` journal record, and the attribution chain it carries.

`SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" requires one `resume` record journaled BEFORE the run exists,
"naming the earlier run's identifiers, the pull request number, the published
head, the resumed-at stage and the source that decided it". The attribution
paragraph then makes that record load-bearing rather than merely informative:
"the `resume` record links the earlier run's identifiers to the resumed dispatch,
and the acceptance pass MUST attribute a record carrying any identifier so linked
to the resumed dispatch, so a `verified` record the earlier run published grades
the resumed run's merge."

WHY THE LINK LIVES IN THE JOURNAL AND NOWHERE ELSE. The two runs share only one
thing: the work item. Everything else about them differs — different run ids,
different sandboxes, and for a resumed run a different entry node — and the
RECORD the earlier run published names its own run, not the resumed one. The
journal is the single artifact that spans both dispatches of one item, which is
the same reason `_dispatcher_proof_attribution` resolves its accepted identifier
set from the file rather than from the record under judgment.

WHY THE CHAIN IS TRANSITIVE, AND WHY THAT IS CHEAP HERE. The clause admits a
SECOND resume of one item, so an identifier may be linked through two records
rather than one. Because every resume of an item is journaled under that item,
reading every `resume` record for the item and unioning the identifiers they name
IS the transitive closure — no walk is needed, and a walk would introduce an
ordering question (which record links which) that the data does not answer.

WHY THE PULL-REQUEST FIELD IS NOT DECORATION. The third-resume refusal counts the
resumes "anchored on the same pull request", and an item can legitimately have
more than one pull request over its life — a plain re-dispatch after a reclaim
opens a new one. Counting resumes per ITEM rather than per PULL REQUEST would
refuse a first resume of a freshly published pull request because two resumes of
a previous one had already been spent.

WHY ONLY A RESUME THAT CREATED A FACTORY RUN ANCHORS ONE. The record is journaled
BEFORE the run exists — it has to be, for the attribution reason above — so a
`resume` row is evidence of an ATTEMPT and not of a run. The bound exists because
"the proof-loop caps are per run", which the refusal says itself, so an attempt
refused before any run was created spent none of those caps and there is nothing
for it to have anchored. Counting it turns a transient provider-headroom refusal
into the PERMANENT loss of the resume route: two such attempts exhaust the bound,
and the only remedy the refusal can then name is a plain dispatch, which reclaims
the publish branch and discards the pull request's approved work. Measured
2026-10-18 on `bd-ib-nsrgxl`: two resume attempts of pull request 3209 were each
refused by the ACP preflight's session-headroom filter with no Fabro run, and the
third was refused for having "already anchored 2 resumes".

HOW A CREATED RUN IS RECOGNISED, AND WHY NOT BY STAGE NAME. A run exists once the
factory has minted an id for it, and `_run_attribution` already owns that
reading: a journal record counts as a run record "when it carries BOTH a
`work_item_id` and a `run_id`", precisely because naming the stages instead
"would fail in the expensive direction" — a stage added later would carry the run
id and be silently ignored. So this module asks that module, rather than keeping
a second list of stage names free to drift from it. Keying on the `dispatch-id`
row in particular would be wrong in the very direction this fix corrects: that
row is written before the launch, so a dispatch refused at the goal preflight or
at materialization would anchor a resume that created no run.

AND WHY ASKING THAT MODULE WAS NOT ENOUGH ON ITS OWN. The narrowing above landed
with no effect on the case it was filed for, because the refusal path ALARMS and
the alarm journaled the DISPATCHER's own uuid4 correlation id under the key
`run_id`. Every refused resume was therefore followed by a row naming a `run_id`
for the item, so the pending record resolved as launched exactly as a real run
would have made it. `_run_attribution` now excludes the notifier's `notify-`
stages from that reading (`bd-ib-upqaqw`), which is where the exclusion belongs:
this reader asks what names a Fabro run and must not hold a private answer to it.

AND WHY THE WINDOW CLOSES AT THE ITEM'S NEXT ATTEMPT. A reader that simply asked
whether the item has ever had a run would let ONE launched resume vouch for every
refused attempt around it — including the attempt that came before it, whose own
window it was never in. So a resume anchors on a run-naming row that follows it
and precedes the item's next `resume` row, and a row that precedes every attempt
(the dispatch that published the pull request in the first place) anchors none.

WHY `was_resumed` DELIBERATELY DOES NOT NARROW WITH IT. That reader answers a
different question — whether the MERGE this item reached was reached through a
resume — for a pointer whose resumed-run identifier comes from the merging
outcome rather than from the journal. It is asked only of an item that merged, so
an attempt that never ran cannot be the dispatch it credits, and narrowing it
would make a pointer's provenance depend on a row the merging dispatch does not
own.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from livespec_orchestrator_beads_fabro.commands._run_attribution import journaled_run_ids

__all__: list[str] = [
    "RESUME_STAGE",
    "resume_journal_record",
    "resume_linked_run_ids",
    "resumes_anchored_on",
    "was_resumed",
]

RESUME_STAGE = "resume"

_WORK_ITEM_KEY = "work_item_id"
_STAGE_KEY = "stage"
_EARLIER_RUN_IDS_KEY = "earlier_run_ids"
_PULL_REQUEST_KEY = "pull_request"


def resume_journal_record(
    *,
    work_item_id: str,
    earlier_run_ids: Sequence[str],
    pull_request: int,
    head: str,
    resumed_at: str,
    source: str,
) -> dict[str, object]:
    """The one record a resume journals before the run exists.

    `earlier_run_ids` is PLURAL because the earlier run answers to more than one
    identifier — its Fabro run id and the dispatch id its sandbox declared — and
    the attribution clause accepts "either identifier the Dispatcher can
    attribute". Recording only the one the anchoring record happened to carry
    would link half the pair, and the half left out is the one a record published
    by a different stage of the same run may carry.
    """
    return {
        _STAGE_KEY: RESUME_STAGE,
        _WORK_ITEM_KEY: work_item_id,
        _EARLIER_RUN_IDS_KEY: list(earlier_run_ids),
        _PULL_REQUEST_KEY: pull_request,
        "head": head,
        "resumed_at": resumed_at,
        "resumed_at_source": source,
    }


def resume_linked_run_ids(
    *, records: Sequence[Mapping[str, object]], work_item_id: str
) -> tuple[str, ...]:
    """Every earlier-run identifier the item's `resume` records link, duplicates dropped.

    The union across all of the item's resume records IS the transitive closure,
    for the reason the module docstring gives. Order is the journal's own, oldest
    first, so the tuple reads as the chain was built.
    """
    linked: list[str] = []
    for record in _resume_records(records=records, work_item_id=work_item_id):
        linked.extend(_identifier_list(value=record.get(_EARLIER_RUN_IDS_KEY)))
    return tuple(dict.fromkeys(linked))


def resumes_anchored_on(
    *, records: Sequence[Mapping[str, object]], work_item_id: str, pull_request: int
) -> tuple[str, ...]:
    """One NAME per resume of one pull request that CREATED A RUN, oldest first.

    Returned as names rather than as a count because the third-resume refusal
    has to name both earlier resumes, and a count cannot be named. Each resume
    is named by the earlier run it set out to finish, which is the identifier an
    operator can look up on the factory; a record naming no identifier falls
    back to the stage it entered at, so a malformed row that DID create a run
    still CONTRIBUTES to the bound rather than silently raising the cap by one.

    An attempt that created no run is absent entirely, for the reason the module
    docstring gives: it spent none of the per-run caps the bound replaces.
    """
    anchored: list[str] = []
    for record in _launched_resume_records(records=records, work_item_id=work_item_id):
        if record.get(_PULL_REQUEST_KEY) != pull_request:
            continue
        named = _identifier_list(value=record.get(_EARLIER_RUN_IDS_KEY))
        anchored.append(named[0] if named else f"a resume at {record.get('resumed_at')}")
    return tuple(anchored)


def was_resumed(
    *, records: Sequence[Mapping[str, object]], work_item_id: str, pull_request: int
) -> bool:
    """Whether the merging pull request of this item was reached through a resume.

    Keyed on the PULL REQUEST as well as the item, because that is what makes the
    pointer's resumed-run bullet honest: an item whose earlier pull request was
    resumed and whose CURRENT one was dispatched plainly was not resumed into
    this merge, and naming a resumed run on its pointer would credit a dispatch
    that had nothing to do with the record being cited.

    Read off EVERY resume record of that pull request, and deliberately not off
    the bound's launched subset, for the reason the module docstring gives: this
    answers a question about a merge that happened, and the identifier the
    pointer names comes from the merging outcome rather than from these rows.
    """
    return any(
        record.get(_PULL_REQUEST_KEY) == pull_request
        for record in _resume_records(records=records, work_item_id=work_item_id)
    )


def _resume_records(
    *, records: Sequence[Mapping[str, object]], work_item_id: str
) -> tuple[Mapping[str, object], ...]:
    """Every `resume` record for one item, in journal order."""
    return tuple(
        record
        for record in records
        if record.get(_STAGE_KEY) == RESUME_STAGE and record.get(_WORK_ITEM_KEY) == work_item_id
    )


def _launched_resume_records(
    *, records: Sequence[Mapping[str, object]], work_item_id: str
) -> tuple[Mapping[str, object], ...]:
    """Every `resume` record of one item that went on to create a factory run.

    One pass over the item's own rows, carrying at most one resume record as
    PENDING. A `resume` row replaces whatever was pending — which is what closes
    the window at the item's next attempt — and the first later row naming a run
    resolves the pending record as launched. A pending record the pass ends on
    created no run and is simply never yielded.

    The run-naming test is `journaled_run_ids` rather than a stage comparison, so
    this reader and `_run_attribution` cannot disagree about what names a run.
    """
    launched: list[Mapping[str, object]] = []
    pending: Mapping[str, object] | None = None
    for record in records:
        if record.get(_WORK_ITEM_KEY) != work_item_id:
            continue
        if record.get(_STAGE_KEY) == RESUME_STAGE:
            pending = record
        elif pending is not None and journaled_run_ids(
            records=(record,), work_item_id=work_item_id
        ):
            launched.append(pending)
            pending = None
    return tuple(launched)


def _identifier_list(*, value: object) -> list[str]:
    """The string identifiers one journaled field carries, ignoring anything else.

    A journal row is JSON a previous build wrote, so the field may be absent, a
    scalar, or a list carrying a non-string. Every such reading yields NO
    identifier rather than a coerced one: an identifier that is not a string
    cannot match a record's run id, and `str()`-ing it would produce a value that
    looks like an id and matches nothing — which reads as a record belonging to
    another item rather than as a malformed journal row.
    """
    if not isinstance(value, list):
        return []
    entries = cast("list[object]", value)
    return [one for one in entries if isinstance(one, str)]
