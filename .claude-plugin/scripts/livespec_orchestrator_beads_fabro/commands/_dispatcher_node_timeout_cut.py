"""A turn cut by its node timeout: what the cut left running, named on the ledger.

`SPECIFICATION/contracts.md` section "ACP node timeouts" -> "A commit run outlives
a node-timeout cut" and "Repository hooks that outlive a limit" (Scenario 192,
work-item `bd-ib-ptnxyg`). When the engine ends an `implement`, `fix` or
`review_fix` turn at its node's resolved timeout, the agent sends no final
message and cannot stop what it started. The `needs_human` node therefore waits
on, then stops, every commit run still running before it makes its preservation
commit, and reports what it found on stderr as the two sentinel lines declared
below. This module is the HOST half: it reads those lines, decides whether the
needs-human ending IS a node-timeout cut, and renders the cause and the
`hook-over-limit` event the contract asks for.

WHY THE NODE AND THE LIMIT COME FROM THE HOST AND NOT FROM THE SANDBOX. The
sandbox script runs after the cut, in a node that does not know which node was
cut or what its timeout resolved to. The host does: the causal stage names the
node, and the dispatch plan carries the resolved timeouts the graph was rendered
from. Joining the two here is what keeps the figure in the cause the one the
engine enforced, instead of a second reading nothing proves agrees with it.

WHY A CUT IS NAMED ONLY FOR A TIMED-OUT TURN. The sentinel lines are printed on
every needs-human ending that has a commit run on record, because the sandbox
cannot tell why it was reached. Naming a node-timeout from the lines alone would
attribute every such ending to a cut. The attribution is the failing stage's own
recorded cause being a timed-out ACP turn, and the lines only supply what the cut
left behind.

WHICH COMMIT RUNS ARE NAMED. The sandbox's run directory holds every commit run
of the whole sandbox, earlier stages' included, so the lines report all of them.
The contract names "each commit run the cut turn had started", so the host keeps
the ones the cut stage's own recorded `start` calls printed. A started run the
sandbox never reported is named `unobserved` rather than dropped or presumed
passed: a run whose state is not known is the one an operator must go and look at.

THE HOOK RUN FIGURE IS OBSERVED WHEN THE NODE RUNS, which trails the cut by the
routing latency. It is the elapsed time of the surviving hook run when it was
found and terminated, and it is reported as that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_over_limit import (
    HookOverLimit,
    journal_hook_over_limit,
)
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import STAGE_FAILURE
from livespec_orchestrator_beads_fabro.commands._fabro_transport_fault import (
    TURN_TIMED_OUT,
    transport_fault_from_cause,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import JournalWriter
    from livespec_orchestrator_beads_fabro.commands._node_timeouts import NodeTimeouts

__all__: list[str] = [
    "NODE_CUT_COMMIT_RUN_SENTINEL",
    "NODE_CUT_HOOK_RUN_SENTINEL",
    "CommitRunAtCut",
    "NodeTimeoutCut",
    "attach_node_timeout_cut",
    "node_timeout_cut",
    "node_timeout_cut_cause_lines",
    "started_commit_run_ids",
]

# The two lines the `needs_human` node's commit-runner pass prints. One spelling,
# substituted into the sandbox program, so the line printed and the line parsed
# cannot drift apart.
NODE_CUT_COMMIT_RUN_SENTINEL = "LIVESPEC_NODE_CUT_COMMIT_RUN"
NODE_CUT_HOOK_RUN_SENTINEL = "LIVESPEC_NODE_CUT_HOOK_RUN"

_UNOBSERVED = "unobserved"

_RUN_LINE = re.compile(
    re.escape(NODE_CUT_COMMIT_RUN_SENTINEL)
    + r": run=(?P<run>commit-[0-9a-f]+) state=(?P<state>passed|failed|no-verdict)"
)
_HOOK_LINE = re.compile(
    re.escape(NODE_CUT_HOOK_RUN_SENTINEL)
    + r": operation=(?P<operation>commit|push) hook_elapsed_ms=(?P<elapsed>\d+)"
)
_RUNNER_START = re.compile(r"livespec-commit-runner\.py[\"']?\s+start\b")
_RUN_ID = re.compile(r"^commit-[0-9a-f]+$")


@dataclass(frozen=True, kw_only=True)
class CommitRunAtCut:
    """One commit run and the state it was in when preservation began."""

    run_id: str
    state: str


@dataclass(frozen=True, kw_only=True)
class NodeTimeoutCut:
    """A needs-human ending caused by a node's resolved timeout ending its turn.

    `hook_operation` and `hook_elapsed_ms` are set together, only when the
    sandbox found a git commit or push whose hook run was still executing.
    """

    node: str
    timeout_seconds: int
    commit_runs: tuple[CommitRunAtCut, ...]
    hook_operation: str | None = None
    hook_elapsed_ms: int | None = None

    @property
    def hook_over_limit(self) -> HookOverLimit | None:
        """The `hook-over-limit` event this cut carries, or None when no hook was running."""
        if self.hook_operation is None or self.hook_elapsed_ms is None:
            return None
        return HookOverLimit(
            node=self.node,
            operation=self.hook_operation,
            limit_seconds=self.timeout_seconds,
            hook_elapsed_ms=self.hook_elapsed_ms,
        )


def node_timeout_cut(
    *,
    text: str,
    stage: str | None,
    cause: str | None,
    timeout_seconds: int | None,
    started_run_ids: tuple[str, ...] | None,
) -> NodeTimeoutCut | None:
    """The cut this ending is, or None when the failing stage did not time out.

    `started_run_ids` None means the stage's recorded calls could not be read, in
    which case every run the sandbox reported is named; an empty tuple means the
    record was read and the turn started none.
    """
    fault = transport_fault_from_cause(cause=cause)
    if stage is None or timeout_seconds is None or fault is None or fault.family != TURN_TIMED_OUT:
        return None
    reported = {match["run"]: match["state"] for match in _RUN_LINE.finditer(text)}
    names = tuple(reported) if started_run_ids is None else started_run_ids
    hook = _HOOK_LINE.search(text)
    return NodeTimeoutCut(
        node=_node_id(stage=stage),
        timeout_seconds=timeout_seconds,
        commit_runs=tuple(
            CommitRunAtCut(run_id=name, state=reported.get(name, _UNOBSERVED)) for name in names
        ),
        hook_operation=None if hook is None else hook["operation"],
        hook_elapsed_ms=None if hook is None else int(hook["elapsed"]),
    )


def node_timeout_cut_cause_lines(*, cut: NodeTimeoutCut | None) -> tuple[str, ...]:
    """The needs-human cause's account of the cut, OUR text throughout.

    The node is a graph node id, the timeout an integer, and each run an
    identity the sandbox runner minted plus a state from a closed set, so none of
    it is engine prose that could carry a MiniJinja opener or a tokenized URL.
    """
    if cut is None:
        return ()
    return (
        (
            f"cause: node-timeout — the {cut.node} node's turn was ended by its resolved "
            f"node timeout of {cut.timeout_seconds} seconds; no agent asked anything"
        ),
        *(
            f"commit run {run.run_id}: {run.state} when preservation began"
            for run in cut.commit_runs
        ),
    )


def started_commit_run_ids(
    *, events_payload: object | None, stage: str | None
) -> tuple[str, ...] | None:
    """The commit runs `stage`'s recorded calls started, or None when unreadable."""
    if stage is None or not isinstance(events_payload, list):
        return None
    node = _node_id(stage=stage)
    commands: dict[str, str] = {}
    started: list[str] = []
    for raw in cast("list[object]", events_payload):
        if not isinstance(raw, dict):
            continue
        envelope = cast("dict[str, object]", raw)
        if _node_id(stage=_envelope_node(envelope=envelope)) != node:
            continue
        update = _acp_update(envelope=envelope)
        call_id = update.get("toolCallId")
        if not isinstance(call_id, str):
            continue
        if update.get("sessionUpdate") == "tool_call":
            commands[call_id] = _command(update=update)
        elif _RUNNER_START.search(commands.get(call_id, "")) is not None:
            raw_output = update.get("rawOutput")
            output = (
                raw_output
                if isinstance(raw_output, str)
                else _mapping(value=raw_output).get("formatted_output")
            )
            run_id = output.strip().splitlines()[-1].strip() if isinstance(output, str) else ""
            if _RUN_ID.match(run_id) is not None and run_id not in started:
                started.append(run_id)
    return tuple(started)


def attach_node_timeout_cut(
    *,
    outcome: DispatchOutcome,
    node_timeouts: NodeTimeouts,
    text: str,
    events_payload: object | None,
    journal: JournalWriter,
) -> DispatchOutcome:
    """The outcome carrying the cut, with its `hook-over-limit` row journaled.

    Applies only to a needs-human ending attributed to a failed stage; every other
    outcome passes through untouched. The row is written here, at the moment the
    ending is attributed, because the sandbox that observed the hook run is gone
    once the run ends.
    """
    if outcome.needs_human_kind != STAGE_FAILURE or not outcome.needs_human_stages:
        return outcome
    stage = outcome.needs_human_stages[-1]
    cut = node_timeout_cut(
        text=text,
        stage=stage,
        cause=outcome.fabro_failure_cause,
        timeout_seconds=node_timeouts.seconds_for(node=_node_id(stage=stage)),
        started_run_ids=started_commit_run_ids(events_payload=events_payload, stage=stage),
    )
    if cut is None:
        return outcome
    event = cut.hook_over_limit
    journal_hook_over_limit(journal=journal, work_item_id=outcome.work_item_id, event=event)
    return replace(
        outcome,
        node_timeout_cut=cut,
        hook_over_limit=outcome.hook_over_limit if event is None else event,
    )


def _node_id(*, stage: str) -> str:
    """`fix` for `fix`, `fix@1` and `050-fix@1` alike."""
    return re.sub(r"^\d+-", "", stage.split("@", maxsplit=1)[0].strip())


def _command(*, update: dict[str, object]) -> str:
    command = _mapping(value=update.get("rawInput")).get("command")
    if isinstance(command, str):
        return command
    title = update.get("title")
    return title if isinstance(title, str) else ""


def _acp_update(*, envelope: dict[str, object]) -> dict[str, object]:
    body = _mapping(
        value=_mapping(value=_mapping(value=envelope.get("item")).get("record")).get("body")
    )
    custom = _mapping(value=_mapping(value=body.get("ev")).get("custom"))
    return _mapping(value=_mapping(value=custom.get("event")).get("update"))


def _envelope_node(*, envelope: dict[str, object]) -> str:
    subject = _mapping(value=_mapping(value=envelope.get("item")).get("subject"))
    name = _mapping(value=subject.get("node")).get("name")
    return name if isinstance(name, str) else ""


def _mapping(*, value: object) -> dict[str, object]:
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}
