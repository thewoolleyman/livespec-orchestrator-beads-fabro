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

WHERE EVERY PETRI-ERA SPELLING IN THIS MODULE WAS MEASURED, and what was NOT.
This is stated field by field rather than as one citation, because the first
delivery of this fix read three keys no engine has been observed writing and a
test carrying them passed anyway — the fixture and the reader agreed with each
other and with nothing else:

* The ENVELOPE `{run_id, stream_seq, kind, id, recorded_at, item: {seq,
  recorded_at, record: {kind, body}}}` is transcribed from
  `plan/fabro-currency/research/006-hp-candidate-first-measurements-2026-10-08.md`
  (candidate v0.378.0-nightly.0) and is already relied on by
  `test_dispatcher_watchdog_petri_events.py`.
* The event BODY at `item.record.body`, its `event` field, the ending name
  `step.finished`, and the failure block at `outcome.status.failure` carrying
  `message` are transcribed from this repository's own committed reproducer,
  `plan/fabro-currency/research/004-acp-spend-limit-repro.py` — whose
  `selected_evidence` reads `item.record.body` and whose `verify_case` reads
  `body["outcome"]["status"]["failure"]["class"]` — with the recorded blocks in
  `004-acp-spend-limit-evidence.json` (candidate v0.371.0-nightly.0). A
  SUCCEEDED step carries `outcome.status == "success"` on that same field, so a
  success and a failure are told apart by the block and not by a verdict word.
* The NODE at `item.subject.node.name`, on the envelope's item rather than on
  the event body, is from the same reproducer's `selected_evidence`
  (`item.get("subject", {}).get("node", {}).get("name") == "probe"`). Note 006
  does not mention `subject`: its envelope line describes the `run.created`
  record, so it is silent about this key rather than contradicting it.

WHAT IS COMPOSED HERE AND SAID TO BE: the `causes` LIST of the first case, and
the stage-key `pr@1` / bare `pr` node spellings of the parametrization. No
Petri-era conclusion or event has been measured carrying a cause chain —
research note 006 records "No `causes`, no `signature`" — which is exactly why
the chain case is CONDITIONAL, matching the Definition of Done's own wording:
given events that DO carry one, the innermost element is what both surfaces
must name. The chain is carried INSIDE the measured container
(`outcome.status.failure`) so only the one key is composed. And the node
spelling is parametrized because note 004 measured a bare graph node name while
`test_fabro_terminal_evidence_petri_stages.py` transcribes this carrier's
`inspect` stage map as `<node>@<visit>` (`proof_capture@2`, `needs_human@1`,
measured 2026-10-15): `graph_node_id` normalizes either, and a fixture carrying
only one would pass against a reader that handled only that one.

NONE OF THE PETRI KEYS HAS BEEN RE-MEASURED ON 0.382 ITSELF. If that engine
moved any of them the reader reports an absent cause again — honestly, as an
absence — and the remedy is a fresh measurement, not a guessed key.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

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
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_outcome import (
    PROVIDER_LIMIT_RELEASE_STATUS,
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

# The shape the Petri-era engine IS measured writing for a failed step:
# one `message` inside `outcome.status.failure`, with no chain beside it.
_FAILURE_MESSAGE = "the agent process exited before the protocol completed"
_WEEKLY_LIMIT_MESSAGE = "You've hit your weekly limit · resets Oct 23, 3pm (UTC)"

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


def _envelope(*, stream_seq: int, node: str | None, body: dict[str, Any]) -> dict[str, Any]:
    """One Petri-era event envelope, with the keys note 006 and note 004 record.

    `node` is `None` for the one case that needs an event naming no node at all;
    the `subject` block is then omitted entirely rather than carried empty,
    because that is what a record the engine could not attribute looks like.
    """
    item: dict[str, Any] = {
        "seq": stream_seq,
        "recorded_at": _RECORDED_AT_MS + stream_seq,
        "record": {"kind": body["event"], "body": body},
    }
    if node is not None:
        item["subject"] = {"node": {"name": node}}
    return {
        "run_id": _RUN,
        "stream_seq": stream_seq,
        "kind": body["event"],
        "id": f"{_RUN}-{stream_seq}",
        "recorded_at": _RECORDED_AT_MS + stream_seq,
        "item": item,
    }


def _step_finished(*, stream_seq: int, node: str | None, status: object) -> dict[str, Any]:
    """A `step.finished` envelope whose verdict sits where the engine puts it."""
    return _envelope(
        stream_seq=stream_seq,
        node=node,
        body={"event": "step.finished", "attempt": 1, "outcome": {"status": status}},
    )


def _petri_events(*, node: str, failure: dict[str, Any]) -> list[object]:
    """The routing stage's own failed ending, with the terminal's beside it."""
    return [
        _envelope(
            stream_seq=11,
            node=node,
            body={"event": "step.started", "attempt": 1},
        ),
        _step_finished(stream_seq=12, node=node, status={"failure": failure}),
        _step_finished(
            stream_seq=13,
            node=_TERMINAL_STAGE,
            status={"failure": {"message": _TERMINAL_MESSAGE, "class": "node_error"}},
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
    *,
    tmp_path: Path,
    inspect_payload: list[object],
    events_payload: list[object] | None,
    plan: DispatchPlan | None = None,
) -> DispatchOutcome:
    """The terminal outcome, with both payloads read by the production parsers."""
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(tmp_path=tmp_path) if plan is None else plan,
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


@pytest.mark.parametrize("node", [_ROUTING_STAGE, "pr"])
def test_a_petri_routing_stage_cause_chain_reaches_both_needs_human_surfaces(
    tmp_path: Path, node: str
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
            node=node,
            failure={
                "class": "node_error",
                "causes": [_WRAPPER_CAUSE, _INNERMOST_CAUSE],
                "category": "deterministic",
            },
        ),
    )

    assert outcome.fabro_failure_cause == _INNERMOST_CAUSE
    assert f"innermost cause: {_INNERMOST_CAUSE}" in outcome.detail
    assert f"innermost cause: {_INNERMOST_CAUSE}" in needs_human_cause_body(outcome=outcome)
    assert _WRAPPER_CAUSE not in outcome.detail


def test_the_measured_petri_failure_message_is_named_as_the_cause(
    tmp_path: Path,
) -> None:
    """The shape the engine IS measured writing: one `message`, no chain.

    This is the case a real Petri ending takes, and it is NOT redundant with
    the chain case above: the two travel through different arms of the shared
    cause-chain classifier, so a reader that only understood a `causes` list
    would satisfy the chain case and still report nothing here.
    """
    outcome = _outcome(
        tmp_path=tmp_path,
        inspect_payload=_petri_inspect(),
        events_payload=_petri_events(
            node=_ROUTING_STAGE,
            failure={"message": _FAILURE_MESSAGE, "class": "retry_requested"},
        ),
    )

    assert outcome.fabro_failure_cause == _FAILURE_MESSAGE
    assert f"innermost cause: {_FAILURE_MESSAGE}" in outcome.detail
    assert f"innermost cause: {_FAILURE_MESSAGE}" in needs_human_cause_body(outcome=outcome)


def test_a_petri_stage_output_supplies_a_provider_limit_when_events_timed_out(
    tmp_path: Path,
) -> None:
    """The stage record is the fallback when no terminal-event payload arrived.

    Petri keeps an ACP error in the failing stage's ``output`` while the run
    conclusion records only the deliberate needs-human script exit.  A timed-out
    ``fabro events`` read therefore cannot be treated as evidence that the stage
    supplied no cause: the inspect record already carries the provider's own
    sentence.
    """
    inspect_payload = _petri_inspect()
    record = inspect_payload[0]
    assert isinstance(record, dict)
    stages = record["stages"]
    assert isinstance(stages, dict)
    stage = stages[_ROUTING_STAGE]
    assert isinstance(stage, dict)
    stage["output"] = f"ACP error: code -32603, Internal error: {_WEEKLY_LIMIT_MESSAGE}"

    outcome = _outcome(
        tmp_path=tmp_path,
        inspect_payload=inspect_payload,
        events_payload=None,
    )

    assert outcome.status == PROVIDER_LIMIT_RELEASE_STATUS
    assert outcome.provider_limit_release is not None
    assert outcome.fabro_failure_cause == _WEEKLY_LIMIT_MESSAGE
    assert outcome.provider_usage_limit is True
    assert outcome.provider_usage_limit_provider == "anthropic"
    assert f"innermost cause: {_WEEKLY_LIMIT_MESSAGE}" in outcome.detail
    assert f"innermost cause: {_WEEKLY_LIMIT_MESSAGE}" in needs_human_cause_body(outcome=outcome)


def test_stage_output_provider_limit_survives_a_legacy_plan_without_acp_nodes(
    tmp_path: Path,
) -> None:
    """The terminal fallback does not require optional plan routing metadata.

    The proof-capture reproduction deliberately supplies only the plan fields
    this terminal needs.  ``acp_nodes`` is optional on ``DispatchPlan`` and a
    terminal cause must still be reported when that metadata is absent.
    """
    inspect_payload = _petri_inspect()
    record = inspect_payload[0]
    assert isinstance(record, dict)
    stages = record["stages"]
    assert isinstance(stages, dict)
    stage = stages[_ROUTING_STAGE]
    assert isinstance(stage, dict)
    stage["output"] = f"ACP error: code -32603, Internal error: {_WEEKLY_LIMIT_MESSAGE}"
    legacy_plan = cast(
        DispatchPlan,
        SimpleNamespace(
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
        ),
    )
    assert not hasattr(legacy_plan, "acp_nodes")

    outcome = _outcome(
        tmp_path=tmp_path,
        inspect_payload=inspect_payload,
        events_payload=None,
        plan=legacy_plan,
    )

    assert outcome.fabro_failure_cause == _WEEKLY_LIMIT_MESSAGE
    assert outcome.provider_usage_limit is True
    assert outcome.provider_usage_limit_provider == "anthropic"


def test_a_succeeded_step_on_the_routing_node_is_not_read_as_its_failure(
    tmp_path: Path,
) -> None:
    """The verdict is told by the failure BLOCK, never by a verdict word.

    A succeeded Petri step carries `outcome.status == "success"` — a bare
    string on the very field a failure nests its block under — so a reader
    keyed on the presence of `outcome`, or on any word inside it, counts a
    success as a failure. Here the node's only OTHER record is the success, so
    a reader that did would attribute a cause-free block to the stage and then
    report the absence clause for a run whose real ending it skipped.
    """
    events: list[object] = [
        _step_finished(stream_seq=11, node=_ROUTING_STAGE, status="success"),
        _step_finished(
            stream_seq=12,
            node=_ROUTING_STAGE,
            status={"failure": {"message": _FAILURE_MESSAGE, "class": "retry_requested"}},
        ),
    ]

    outcome = _outcome(tmp_path=tmp_path, inspect_payload=_petri_inspect(), events_payload=events)

    assert outcome.fabro_failure_cause == _FAILURE_MESSAGE


def test_a_later_cause_free_record_does_not_discard_the_cause_already_recorded(
    tmp_path: Path,
) -> None:
    """The newest block that YIELDS a cause wins, not merely the newest block.

    One node can record more than one failure — the bounded fix loop retries
    it, and an engine may follow an ending with a further node-scoped record —
    so taking the last block unconditionally lands on whichever happened to
    come last. When that one carries no readable cause the real one, two
    records earlier, is discarded and the surfaces report the absence clause
    for a cause the engine did supply. That is strictly worse than the silence
    this item is closing: it is a confident claim about the engine, drawn from
    the reader's own choice of record.
    """
    events: list[object] = [
        _step_finished(
            stream_seq=11,
            node=_ROUTING_STAGE,
            status={
                "failure": {
                    "class": "node_error",
                    "causes": [_WRAPPER_CAUSE, _INNERMOST_CAUSE],
                }
            },
        ),
        _step_finished(
            stream_seq=12,
            node=_ROUTING_STAGE,
            status={"failure": {"class": "node_error"}},
        ),
    ]

    outcome = _outcome(tmp_path=tmp_path, inspect_payload=_petri_inspect(), events_payload=events)

    assert outcome.fabro_failure_cause == _INNERMOST_CAUSE
    assert f"innermost cause: {_INNERMOST_CAUSE}" in needs_human_cause_body(outcome=outcome)


def test_a_failure_naming_no_node_is_not_attributed_to_the_routing_stage(
    tmp_path: Path,
) -> None:
    """An event the engine could not place must not be placed by this reader.

    The whole read is node-scoped, so a record carrying a failure and no
    subject belongs to no node's list. Attributing it to whichever stage the
    checkpoint happened to name would report another node's fault — or a
    run-level one — as this stage's innermost cause.
    """
    events: list[object] = [
        _step_finished(
            stream_seq=11,
            node=None,
            status={"failure": {"message": "run aborted by the scheduler"}},
        )
    ]

    outcome = _outcome(tmp_path=tmp_path, inspect_payload=_petri_inspect(), events_payload=events)

    assert outcome.fabro_failure_cause is None
    assert "run aborted by the scheduler" not in outcome.detail


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
            node=_ROUTING_STAGE,
            failure={"message": _FAILURE_MESSAGE, "class": "retry_requested"},
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
