"""Gathering one dispatch's TDD order signals at calibration time.

The IO half of plan `factory-test-first-enforcement` slice S3 (work-item
`bd-ib-3h5vfq`): the `gh pr view --json commits` probe, the per-dispatch
commit-series selection, the order-sink read and the adapter lookup, assembled
into the `TddSignals` the terminal `dispatcher.calibration` span carries. The
derivations themselves are pure and live in `_dispatcher_tdd_commits`,
`_dispatcher_tdd_order_sink`, `_dispatcher_implement_adapter` and
`_dispatcher_tdd_signals`; this module only reaches for their inputs.

HOW THE CORRELATION IS PER DISPATCH RATHER THAN PER ITEM — the work-item names
this as a requirement, and the mechanism is ONE id appearing on both ends. The
Dispatcher mints a `dispatch_id` per dispatch and writes it into the sandbox
clone's local `livespec.factoryRunId` git config
(`_dispatcher_factory_provenance.factory_run_id_prepare_steps_block`), which is
what stamps the `Factory-Run-Id` trailer onto every commit that run authors.
The same id is journaled as the `dispatch-id` stage record. So reading the id
off the journal and filtering the pull request's commits by that trailer is an
EXACT per-run selection: a re-dispatch of the same item, or a human commit
pushed onto the same branch, cannot contribute to it.

WHY A TRAILER-EMPTY SERIES IS UNOBSERVABLE AND NOT ZERO. If the pull request
has commits but none carries THIS dispatch's trailer, the honest answer is
that this run's series could not be identified — not that the run authored
zero Reds. A zero-Red, zero-gap reading is precisely the sharpest post-hoc
signature available, so manufacturing one from a missing trailer would invent
the finding this instrument exists to measure.

Posture: every probe is fail-soft to `None`, and the whole calibration stage
is already fail-open around this module (`_dispatcher_calibration_emit`
journals a `calibration-error` and swallows). The commit probe runs for a
published run whatever its terminal status — a reviewed-but-unmerged run has a
commit series worth measuring, and the diff-size proxy's merged-only
restriction is a separate limitation that slice S4 owns.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_size_gate import (
    size_justified_at_admission,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_implement_adapter import (
    implement_adapter_label,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_commits import (
    TddCommitSignals,
    commit_trailers,
    parse_commit_messages,
    tdd_commit_signals,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_order_sink import TddOrderSink
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_signals import (
    TddSignals,
    tdd_signals,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "FACTORY_RUN_ID_TRAILER_KEY",
    "commit_signals_for_dispatch",
    "dispatch_id_for",
    "dispatch_ids_for",
    "gather_tdd_signals",
]

# The trailer the sandbox's `livespec.factoryRunId` git config stamps on every
# commit the run authors. Its VALUE is the Dispatcher's `dispatch_id`, which is
# what makes this a per-run selector rather than a per-item one.
FACTORY_RUN_ID_TRAILER_KEY = "Factory-Run-Id"

_DISPATCH_ID_STAGE = "dispatch-id"
_DISPATCH_ID_FIELD = "dispatch_id"

# The commit-series probe budget, matching the sibling merged-PR diff-size
# probe: fail-soft to None rather than hold up an already-final verdict.
_COMMITS_PROBE_TIMEOUT_SECONDS = 60.0


def gather_tdd_signals(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    records: tuple[dict[str, object], ...],
    sink: TddOrderSink,
    runner: CommandRunner,
) -> TddSignals:
    """Assemble this dispatch's TDD signals from every available source.

    `records` are the per-dispatch journal records calibration already read
    back; they supply both the dispatch id and the implement node's resolved
    adapter. The order aggregate is looked up MOST-SPECIFIC-FIRST — the
    dispatch id before the work-item id — so a re-dispatched item reads its
    own run's refusals; the work-item key is the fallback for a dispatch whose
    id never reached the journal.
    """
    dispatch_id = dispatch_id_for(records=records, work_item_id=item.id)
    return tdd_signals(
        item=item,
        commits=commit_signals_for_dispatch(
            repo=repo, outcome=outcome, dispatch_id=dispatch_id, runner=runner
        ),
        order=sink.signals_for(
            keys=(dispatch_id, item.id) if dispatch_id is not None else (item.id,)
        ),
        adapter=implement_adapter_label(records=records, work_item_id=item.id),
        size_justified=_size_justified_signal(
            records=records,
            item=item,
            outcome=outcome,
            dispatch_id=dispatch_id,
        ),
    )


def _size_justified_signal(
    *,
    records: tuple[dict[str, object], ...],
    item: WorkItem,
    outcome: DispatchOutcome,
    dispatch_id: str | None,
) -> bool | None:
    """Whether this green dispatch was admitted by an attributed exception."""
    if outcome.status != "green" or dispatch_id is None:
        return None
    return size_justified_at_admission(
        records=records,
        work_item_id=item.id,
        dispatch_id=dispatch_id,
    )


def dispatch_ids_for(
    *, records: tuple[dict[str, object], ...], work_item_id: str
) -> tuple[str, ...]:
    """Every dispatch id this item's `dispatch-id` journal records name, in order.

    The plural of the reader below, and the shape the proof-attribution pass
    needs: an item dispatched more than once has one id per dispatch, and the
    dispatch that published a MERGED head may be any of them rather than the
    newest. One entry per record, so the LAST element is the dispatch now
    terminating. A non-string or empty value reads as absent rather than being
    coerced, since a coerced id would select a commit series belonging to nobody.
    """
    found: list[str] = []
    for record in records:
        if record.get("stage") != _DISPATCH_ID_STAGE or record.get("work_item_id") != work_item_id:
            continue
        candidate = record.get(_DISPATCH_ID_FIELD)
        if isinstance(candidate, str) and candidate != "":
            found.append(candidate)
    return tuple(found)


def dispatch_id_for(*, records: tuple[dict[str, object], ...], work_item_id: str) -> str | None:
    """This item's dispatch id from its `dispatch-id` journal record, or None.

    The LAST matching record wins, mirroring how the adapter lookup resolves:
    if a journal carries more than one, the most recent is the dispatch now
    terminating. Derived from the plural reader above rather than scanning the
    records again, which makes the two mechanically incapable of disagreeing: the
    singular is always a member of the plural.
    """
    found = dispatch_ids_for(records=records, work_item_id=work_item_id)
    return found[-1] if found else None


def commit_signals_for_dispatch(
    *,
    repo: Path,
    outcome: DispatchOutcome,
    dispatch_id: str | None,
    runner: CommandRunner,
) -> TddCommitSignals | None:
    """This dispatch's commit-derived TDD signals, or None when unobservable.

    `None` for every arm that cannot identify THIS run's series: no pull
    request to read, no dispatch id to select by, a failing `gh` probe, an
    unparseable payload, or a payload whose commits carry none of this run's
    `Factory-Run-Id` trailer.
    """
    if outcome.pr_number is None or dispatch_id is None:
        return None
    result = runner.run(
        argv=["gh", "pr", "view", str(outcome.pr_number), "--json", "commits"],
        cwd=repo,
        timeout_seconds=_COMMITS_PROBE_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return None
    messages = parse_commit_messages(stdout=result.stdout)
    if messages is None:
        return None
    mine = tuple(
        message
        for message in messages
        if commit_trailers(message=message).get(FACTORY_RUN_ID_TRAILER_KEY) == dispatch_id
    )
    if not mine:
        return None
    return tdd_commit_signals(messages=mine)
