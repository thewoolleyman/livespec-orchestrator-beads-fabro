"""A Petri-era routing stage's innermost cause reaches both needs-human surfaces.

Work-item `bd-ib-3nu5vv`. `ab9a961f` ("attribute needs-human causes to the
routing stage", `bd-ib-jtl5ir`) moved the cause the needs-human record reports
off the run CONCLUSION — where a Petri terminal's own deliberate `exit 1`
lives — and onto the stage that ROUTED the run there, read from that stage's
own failure events. On the pinned engine that read lands; on the Petri-era
engine it found nothing for EVERY node of EVERY run, so the one line a triager
needs vanished from both surfaces at once and nothing said it had.

MEASURED ON hp-candidate (`:32278`, fabro `0.382.0-nightly.0` `adeefec`):
records written on Dispatcher payloads up to 0.203.2 carry an
`innermost cause:` line — `bd-ib-o6aeji` run `01M5330YQQFQ` reads
`innermost cause: script exited with status 1` — while runs
`01M542TM46NS`, `01M55WZ7DS6A` and `01M563W6CWYQ`, written on v0.207.2 and
later, carry none. Legacy hp (`:32276`) records still carry the line, which is
what localizes the gap to the Petri-era event shape rather than to the change
itself.

WHY THE READ COULD NOT RETURN A HIT. The pinned engine PRINTS the event; the
Petri-era engine prints an ENVELOPE — `{run_id, stream_seq, kind, id,
recorded_at, item: {seq, recorded_at, record: {kind, body}}}`, transcribed from
`plan/fabro-currency/research/006-hp-candidate-first-measurements-2026-10-08.md`
and already relied on by `test_dispatcher_watchdog_petri_events.py` — and puts
the event's own `event`, node and `failure` fields two levels in, under
`item.record.body`. It also names every ending `step.finished` and carries the
verdict in `outcome`, never as a `stage.failed` event name, and names the node
`firing` rather than `node_id`. So a reader of the envelope's own keys reports
a clean, plausible "this node recorded nothing" with no error at all.

THE FIXTURE'S STAGE KEYS ARE THE MEASURED ONES. `test_fabro_terminal_evidence_
petri_stages.py` transcribes this carrier's `inspect` stage map as `<node>@<visit>`
with no ordinal prefix (`proof_capture@2`, `needs_human@1`, measured 2026-10-15),
so the routing stage here is `pr@1`. What was NOT measured is how a `firing`
field spells the same node, so BOTH spellings are exercised — the stage key and
the bare graph node id — because `graph_node_id` normalizes either and a fixture
carrying only one would pass against a reader that handled only that one.

A CAUSE CHAIN is likewise not something this engine has been measured emitting
(research note 006 records "No `causes`, no `signature`" on its conclusion), and
that is exactly why the chain case belongs here: the assertion is conditional —
given events that DO carry one, the innermost element is what both surfaces must
name — so the chain case grades the selection and the `detail.message` case
grades the shape the engine is measured writing today.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_cause import (
    needs_human_cause_body,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NEEDS_HUMAN_MARKER,
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_failure_detail_from_payload,
    fabro_status_kind_from_payload,
)

_RUN = "01M563W6CWYQ"
_ITEM = "bd-ib-3nu5vv"
_ROUTING_STAGE = "pr@1"
_TERMINAL_STAGE = "needs_human@1"
_RECORDED_AT_MS = 1792000000000

# The chain, outermost-first: `causes[0]` is the fixed transport wrapper that
# names no fault, so the record must report `causes[-1]`.
_WRAPPER_CAUSE = "ACP protocol error"
_INNERMOST_CAUSE = "script exited with status 1"

# The shape the Petri-era engine IS measured writing for a failure:
# `{reason, detail: {message, category}}`, with no chain beside it.
_DETAIL_MESSAGE = "goal gate unsatisfied for node pr and no retry target"

# The terminal's own failed step, which can never be the cause: it is a
# dead-end script that exits 1 by design on every run that reaches it.
_TERMINAL_MESSAGE = "stage needs_human failed with no outgoing fail edge"

_STDERR = (
    f"{NEEDS_HUMAN_MARKER}_PRESERVED: refs/heads/needs-human/{_RUN}\n"
    f"{NEEDS_HUMAN_MARKER}: loop cannot auto-resolve this work-item; run "
    "terminated, work preserved by reference, decision routed to the ledger "
    "(blocked / needs-human)\n"
)


def _stage(*, handler: str, state: str) -> dict[str, Any]:
    """One entry of the Petri `stages` map, with the four keys it carries."""
    return {"handler": handler, "state": state, "output": None, "response": None}


def _petri_inspect() -> list[object]:
    """`fabro inspect --json` for a Petri-era run that ended at the terminal.

    The checkpoint carries the three keys that engine writes and NO
    `node_outcomes`, so the routing stage's failure cannot be read from the
    checkpoint at all and the event stream is the only source left. The
    conclusion carries the TERMINAL's own exit, which is the sentence the
    routing-stage attribution exists to stop reporting.
    """
    return [
        {
            "run_id": _RUN,
            "parent_id": None,
            "status": {"kind": "failed", "reason": "workflow_error"},
            "stages": {
                "implement@1": _stage(handler="agent", state="succeeded"),
                "janitor@1": _stage(handler="script", state="succeeded"),
                _ROUTING_STAGE: _stage(handler="agent", state="failed"),
                _TERMINAL_STAGE: _stage(handler="script", state="failed"),
            },
            "checkpoint": {
                "current_node": "needs_human",
                "git_commit_sha": "9bcd4faa2e3c4d5f6071829304a5b6c7d8e9f012",
                "timestamp": "2026-10-18T01:00:00.000000000Z",
            },
            "conclusion": {
                "status": "failed",
                "failure": {
                    "reason": "workflow_error",
                    "detail": {
                        "message": _TERMINAL_MESSAGE,
                        "category": "deterministic",
                    },
                },
            },
        }
    ]


def _envelope(*, stream_seq: int, kind: str, body: dict[str, Any]) -> dict[str, Any]:
    """One Petri-era event envelope, with the six keys research note 006 records."""
    return {
        "run_id": _RUN,
        "stream_seq": stream_seq,
        "kind": kind,
        "id": f"{_RUN}-{stream_seq}",
        "recorded_at": _RECORDED_AT_MS,
        "item": {
            "seq": stream_seq,
            "recorded_at": _RECORDED_AT_MS,
            "record": {"kind": kind, "body": body},
        },
    }


def _petri_events(*, firing: str, failure: dict[str, Any]) -> list[object]:
    """The routing stage's own failed ending, with the terminal's beside it."""
    return [
        _envelope(
            stream_seq=11,
            kind="step.started",
            body={"event": "step.started", "firing": firing, "attempt": 1},
        ),
        _envelope(
            stream_seq=12,
            kind="step.finished",
            body={
                "event": "step.finished",
                "firing": firing,
                "outcome": "failed",
                "failure": failure,
            },
        ),
        _envelope(
            stream_seq=13,
            kind="step.finished",
            body={
                "event": "step.finished",
                "firing": _TERMINAL_STAGE,
                "outcome": "failed",
                "failure": {
                    "reason": "node_error",
                    "detail": {"message": _TERMINAL_MESSAGE, "category": "deterministic"},
                },
            },
        ),
    ]


def _plan(*, tmp_path: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=tmp_path,
        work_item_id=_ITEM,
        branch=f"feat/{_ITEM}",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="hp-candidate",
        fabro_factory_server="https://hp-xubuntu.example:32278",
        fabro_factory_dev_token=None,
        janitor=None,
        janitor_checkout=tmp_path / ".janitor",
        janitor_core_checkout=tmp_path / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
    )


def _outcome(
    *, tmp_path: Path, inspect_payload: list[object], events_payload: list[object] | None
) -> DispatchOutcome:
    """The terminal outcome, with both payloads read by the production parsers."""
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(tmp_path=tmp_path),
        run_id=_RUN,
        inspect=FabroInspectResult(
            command=CommandResult(exit_code=0, stdout="", stderr=""),
            payload=inspect_payload,
            status_kind=fabro_status_kind_from_payload(payload=inspect_payload),
            failure=fabro_failure_detail_from_payload(payload=inspect_payload),
            events_payload=events_payload,
        ),
        exit_code=1,
        stderr=_STDERR,
    )
    assert outcome is not None
    return outcome


@pytest.mark.parametrize("firing", [_ROUTING_STAGE, "pr"])
def test_a_petri_routing_stage_cause_chain_reaches_both_needs_human_surfaces(
    tmp_path: Path, firing: str
) -> None:
    """The chain's INNERMOST element, on the dispatch result and in the ledger.

    Both surfaces are asserted in one case deliberately: they render from the
    same `fabro_failure_cause` field, so a build that fed one and not the other
    is the regression being closed and a test reading only the detail would
    pass through it. The wrapper element is asserted ABSENT as well, because a
    reader taking `causes[0]` names the transport and no fault while still
    producing an `innermost cause:` line.
    """
    outcome = _outcome(
        tmp_path=tmp_path,
        inspect_payload=_petri_inspect(),
        events_payload=_petri_events(
            firing=firing,
            failure={
                "reason": "node_error",
                "causes": [_WRAPPER_CAUSE, _INNERMOST_CAUSE],
                "category": "deterministic",
                "signature": "pr|deterministic|acp turn failed",
            },
        ),
    )

    assert outcome.fabro_failure_cause == _INNERMOST_CAUSE
    assert f"innermost cause: {_INNERMOST_CAUSE}" in outcome.detail
    assert f"innermost cause: {_INNERMOST_CAUSE}" in needs_human_cause_body(outcome=outcome)
    assert _WRAPPER_CAUSE not in outcome.detail


def test_the_measured_petri_failure_detail_message_is_named_as_the_cause(
    tmp_path: Path,
) -> None:
    """The shape the engine writes today: one `detail.message`, no chain.

    This is the case a real Petri ending takes, and it is NOT redundant with
    the chain case above: the two travel through different arms of the shared
    cause-chain classifier, so a reader that only understood a `causes` list
    would satisfy the chain case and still report nothing here.
    """
    outcome = _outcome(
        tmp_path=tmp_path,
        inspect_payload=_petri_inspect(),
        events_payload=_petri_events(
            firing=_ROUTING_STAGE,
            failure={
                "reason": "node_error",
                "detail": {"message": _DETAIL_MESSAGE, "category": "deterministic"},
            },
        ),
    )

    assert outcome.fabro_failure_cause == _DETAIL_MESSAGE
    assert f"innermost cause: {_DETAIL_MESSAGE}" in outcome.detail
    assert f"innermost cause: {_DETAIL_MESSAGE}" in needs_human_cause_body(outcome=outcome)


def test_the_terminal_steps_own_failure_is_never_the_reported_cause(
    tmp_path: Path,
) -> None:
    """The control, and the one that makes reading the envelope at all SAFE.

    `needs_human` exits 1 by design, so its own step records a failure on every
    run that reaches it — and it is the one node that cannot be the cause. A
    reader that newly SEES the Petri stream and does not also recognize a Petri
    terminal key would report that designed exit as the innermost cause, which
    is strictly worse than the silence this item is closing: it is true of every
    needs-human ending there has ever been, so it reads as a finding while
    carrying no information.
    """
    outcome = _outcome(
        tmp_path=tmp_path,
        inspect_payload=_petri_inspect(),
        events_payload=_petri_events(
            firing=_ROUTING_STAGE,
            failure={
                "reason": "node_error",
                "detail": {"message": _DETAIL_MESSAGE, "category": "deterministic"},
            },
        ),
    )

    assert _TERMINAL_MESSAGE not in outcome.detail
    assert _TERMINAL_MESSAGE not in needs_human_cause_body(outcome=outcome)
    assert outcome.needs_human_stages == (_ROUTING_STAGE,)


def test_the_pinned_engines_own_event_shape_still_reads(tmp_path: Path) -> None:
    """Preservation: a bare `stage.failed` keyed `node_id` is unchanged.

    The two engines overlap for the whole cutover, so widening the reader to the
    Petri envelope must not cost the pinned shape. This case carries the pinned
    `node_outcomes` checkpoint AND the pinned event spelling, so a reader that
    replaced one shape with the other fails here rather than passing on the
    strength of the new one.
    """
    pinned: list[object] = [
        {
            "run_id": _RUN,
            "status": {"kind": "failed"},
            "checkpoints": [
                {
                    "checkpoint": {
                        "next_node_id": "needs_human",
                        "node_outcomes": {
                            "pr": {"status": "failed"},
                            "needs_human": {"status": "failed"},
                        },
                    }
                }
            ],
        }
    ]
    events: list[object] = [
        {
            "event": "fabro.stage.failed",
            "node_id": "pr",
            "properties": {
                "failure": {
                    "causes": [_WRAPPER_CAUSE, _INNERMOST_CAUSE],
                    "category": "deterministic",
                }
            },
        }
    ]

    outcome = _outcome(tmp_path=tmp_path, inspect_payload=pinned, events_payload=events)

    assert outcome.fabro_failure_cause == _INNERMOST_CAUSE
    assert f"innermost cause: {_INNERMOST_CAUSE}" in outcome.detail
