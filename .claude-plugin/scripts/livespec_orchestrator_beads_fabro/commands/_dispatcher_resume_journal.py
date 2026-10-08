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
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

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
    """One NAME per resume of one pull request, oldest first.

    Returned as names rather than as a count because the third-resume refusal
    has to name both earlier resumes, and a count cannot be named. Each resume
    is named by the earlier run it set out to finish, which is the identifier an
    operator can look up on the factory; a record naming no identifier falls
    back to the stage it entered at, so a malformed row still CONTRIBUTES to the
    bound rather than silently raising the cap by one.
    """
    anchored: list[str] = []
    for record in _resume_records(records=records, work_item_id=work_item_id):
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
    """
    return bool(
        resumes_anchored_on(records=records, work_item_id=work_item_id, pull_request=pull_request)
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
