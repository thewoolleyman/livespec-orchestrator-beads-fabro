"""Run-to-work-item attribution, preferring recorded facts over the goal regex.

A `fabro ps -a --json` row carries no work-item field, so every consumer used to
re-derive the owning item from the run's GOAL TEXT with the
`^Work-item:\\s*(\\S+)` regex in `_fabro_port_records`. That derivation is the
weakest evidence available. It reads a rendered prose brief rather than a field,
so a goal-template edit silently breaks it; and because it keys on the ITEM it
cannot tell two runs for the SAME item apart, so a superseded run and the
re-dispatch that replaced it attribute identically. Both failures return a
plausible answer with no error.

Two stronger sources are recorded at dispatch time. The work-item's
`dispatch_fabro_run_id` metadata key names the newest run the Dispatcher
launched for it, and the dispatch journal keeps every run id it has ever
recorded against that item. This module is the ONE place the three are ordered,
so no consumer can drift back onto the regex leg by forgetting the other two
exist:

1. item metadata — the run id the LEDGER itself names for this run.
2. the dispatch journal's newest record naming this run id.
3. the goal-text regex — the bootstrap, and the only leg available in the
   window between `fabro run` creating a run and the Dispatcher stamping it.

`RunAttribution()` with no sources is REGEX-ONLY, and that is a legitimate
value rather than a degraded one: a call site with no ledger or journal to hand
still routes its decision through this precedence, so the day it gains a source
the stronger leg wins with no edit at the call site.

A journal record counts as a run record when it carries BOTH a `work_item_id`
and a `run_id`, and is not a NOTIFICATION row. Naming the stages that DO carry a
run (`fabro-run`, `dispatch-id`, `watchdog-discovery-poll`, ...) would be
narrower but would fail in the expensive direction: a stage added later would
carry the run id and be silently ignored, and the miss would look exactly like an
item that had never been dispatched.

WHY THE NOTIFICATION ROWS ARE THE ONE EXCLUSION, AND WHY IT IS A PREFIX. The
terminal-failure alarm journals the DISPATCHER's own per-invocation correlation
id — a uuid4 hex from `_dispatcher_self_update.run_id`, carrying no factory
identity at all — under the key `run_id`, because that is the field the alarm
body correlates on. It is the only writer in the fleet that puts a non-Fabro
value there, so the two-field test above read every notified dispatch as a
dispatch that had created a run. The exclusion is keyed on the notifier's own
`notify-` stage PREFIX rather than on the two stage names it writes today, which
is the direction that fails cheaply: a notification stage added later is covered
with no edit, while a non-notification stage would have to be named `notify-*` to
be wrongly excluded. `_dispatcher_notify` composes its stage names from the
constant below rather than respelling them, so the writer cannot drift out of the
set the reader excludes.

Measured 2026-10-18 on `bd-ib-nsrgxl`: two resume attempts of pull request 3209
were refused before any Fabro run existed, each refusal journaled `notify-sent`
carrying a 32-hex dispatcher id, and the third attempt was refused for having
"already anchored 2 resumes" — so `bd-ib-7uslox`'s narrowing of that bound to
resumes that created a run had no effect on the case it was filed for.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroRunSummary

__all__: list[str] = [
    "GOAL_TEXT_ONLY",
    "NOTIFICATION_STAGE_PREFIX",
    "RunAttribution",
    "journal_run_ids",
    "journaled_run_ids",
    "newest_journaled_run_id",
    "run_attribution",
]

JournalRecords = Iterable[Mapping[str, object]]

# The stage prefix the terminal-failure alarm journals under, whose `run_id` is
# the Dispatcher's own correlation id rather than a factory run. Exported so
# `_dispatcher_notify` composes its stage names from it instead of respelling
# them — see the module docstring for why the exclusion is a prefix.
NOTIFICATION_STAGE_PREFIX = "notify-"

_STAGE_KEY = "stage"
_RUN_ID_KEY = "run_id"
_WORK_ITEM_KEY = "work_item_id"


@dataclass(frozen=True, kw_only=True)
class RunAttribution:
    """The ordered evidence one consumer has for mapping runs onto items.

    Both maps are keyed by RUN id, which is the direction that stays
    single-valued: an item accumulates many runs over its life, a run belongs to
    exactly one item.
    """

    metadata_run_ids: Mapping[str, str] = field(default_factory=dict)
    journal_run_ids: Mapping[str, str] = field(default_factory=dict)

    def work_item_id_for(self, *, run: FabroRunSummary) -> str | None:
        """Return the work-item this run belongs to, by strongest evidence first."""
        recorded = self.metadata_run_ids.get(run.run_id)
        if recorded is not None:
            return recorded
        journaled = self.journal_run_ids.get(run.run_id)
        if journaled is not None:
            return journaled
        return run.work_item_id

    def owns(self, *, run: FabroRunSummary, work_item_id: str) -> bool:
        """Whether this run belongs to the named work-item."""
        return self.work_item_id_for(run=run) == work_item_id


# The attribution a call site with no ledger and no journal to hand still routes
# through. Shared rather than constructed per call because a `RunAttribution()`
# default argument would be a call in a default (ruff B008); it is safe to share
# because the dataclass is frozen and neither map is ever mutated in place.
GOAL_TEXT_ONLY = RunAttribution()


def run_attribution(
    *,
    metadata_run_ids: Mapping[str, str] | None = None,
    journal_records: JournalRecords = (),
) -> RunAttribution:
    """Build an attribution from a ledger run-id index and journal records."""
    return RunAttribution(
        metadata_run_ids=dict(metadata_run_ids or {}),
        journal_run_ids=journal_run_ids(records=journal_records),
    )


def journal_run_ids(*, records: JournalRecords) -> dict[str, str]:
    """Map every journaled Fabro run id to the work-item the journal names for it."""
    mapped: dict[str, str] = {}
    for record in records:
        named = _named_fabro_run(record=record)
        if named is not None:
            run_id, work_item_id = named
            mapped[run_id] = work_item_id
    return mapped


def journaled_run_ids(*, records: JournalRecords, work_item_id: str) -> tuple[str, ...]:
    """Every Fabro run id the dispatch journal names for one item, in journal order.

    A DIFFERENT question from `newest_journaled_run_id` below, and the difference
    matters where an item has been dispatched more than once: the newest run is
    the one now terminating, while this is every run the item has ever had. The
    proof-attribution pass needs the plural, because a run that dies after
    publishing its branch is recovered by a LATER dispatch and the dispatch that
    published the merged head is then no longer the newest row.

    One entry per journaled record rather than a deduplicated set, so the LAST
    element is the newest run exactly as the singular reader resolves it. A
    repeated id is therefore possible and harmless: every consumer either takes
    the last element or tests membership.
    """
    return tuple(
        named[0]
        for record in records
        if (named := _named_fabro_run(record=record)) is not None and named[1] == work_item_id
    )


def newest_journaled_run_id(*, records: JournalRecords, work_item_id: str) -> str | None:
    """Return the newest Fabro run id the dispatch journal names for one item.

    "Newest" is LAST-WINS over the record order, which is sound because the
    journal is append-only: a later record for the same item cannot describe an
    earlier run. This is the seam the reconciler needs to call a run SUPERSEDED
    — an item whose newest journaled run is not the run under judgment has
    moved on, whatever that run's own status still claims.

    Derived from the plural reader above rather than scanning again, which is what
    makes the two mechanically incapable of disagreeing: the singular is always a
    member of the plural, so a widening that accepts the plural set can never
    exclude what the reconciler calls the newest run.
    """
    found = journaled_run_ids(records=records, work_item_id=work_item_id)
    return found[-1] if found else None


def _named_fabro_run(*, record: Mapping[str, object]) -> tuple[str, str] | None:
    """The `(run id, work item)` pair one record names a Fabro run with, else None.

    The ONE place the reading lives, so the three readers above are mechanically
    incapable of disagreeing about what names a run: `journal_run_ids` and
    `journaled_run_ids` both resolve each record through here, and
    `newest_journaled_run_id` is derived from the plural rather than scanning
    again.

    A NOTIFICATION row is rejected before its fields are read at all — not merely
    left out of one caller's answer — because its `run_id` is the Dispatcher's own
    correlation id and is therefore wrong for every question these readers are
    asked, not just for the resume bound. A reader that filtered at one call site
    would leave the publish-branch reclaim and the resume observation asking the
    factory about a uuid4 that no factory has ever minted.
    """
    stage = record.get(_STAGE_KEY)
    if isinstance(stage, str) and stage.startswith(NOTIFICATION_STAGE_PREFIX):
        return None
    run_id = _text(value=record.get(_RUN_ID_KEY))
    work_item_id = _text(value=record.get(_WORK_ITEM_KEY))
    if run_id is None or work_item_id is None:
        return None
    return run_id, work_item_id


def _text(*, value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
