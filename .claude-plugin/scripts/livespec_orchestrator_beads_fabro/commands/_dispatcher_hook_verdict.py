"""A hook-refused commit's RECORDED verdict, read off the run's own tool output.

`SPECIFICATION/contracts.md` "The recorded hook verdict outranks the agent's
account of it" (v211, work-item `bd-ib-k3nmbi`). When a run ends at the
`needs_human` terminal after an agent turn whose latest commit attempt the
repository's commit hook refused, the needs-human cause and the dispatch
journal's outcome row carry the hook's own exit status and failed target names,
read from the run's recorded tool output and never from the agent's reply; and
where the agent's text describes the hook as interrupted or not completed
while the record shows a completed refusal, the agent's text is labelled
agent-reported and the recorded refusal is stated beside it.

WHY A SECOND SOURCE BESIDE THE STAGE'S OWN FAILURE REASON. `bd-ib-36d3x5` made
the needs-human cause read the failing stage's `failure_reason`, and on run
`01M5QNH88NHN68ST28Y80CZJ48` (`bd-ib-8zyan`, 2026-10-24) that reason is the
AGENT'S text: "the Green amend hook did not complete". The run's own record says
otherwise — the Green amend's tool call completed with exit status 1 after the
hook ran for 711 s and refused on `check-types` — and ~196 minutes of allowance
were abandoned on a fixable refusal described as an interruption. The agent's
sentence is kept, because it is what the agent believed; it is labelled, because
the record contradicts it.

THE RECORD SHAPE IS MEASURED, on that run's `fabro events --json` stream (the
Petri-era engine, carrier 0.382.0-nightly.0). Each ACP update arrives as a
`step.progress.recorded` envelope: the node on `item.subject.node.name`, the
update at `item.record.body.ev.custom.event.update`. A tool call's START is a
`tool_call` update carrying `rawInput.command`; its COMPLETION is a
`tool_call_update` carrying `rawOutput.exit_code` and the terminal's
`rawOutput.formatted_output`; the streaming deltas in between are
`tool_call_update`s with no `rawOutput`, and are skipped.

WHAT COUNTS AS A COMMIT ATTEMPT IS DECIDED BY THE OUTPUT, NOT THE COMMAND. The
same turn ran a dozen `ps … | rg 'git commit|lefthook'` inspections, each
containing the literal `git commit`, each exiting 0, and the LAST tool call of
the turn was one of them. A reader keyed on the command alone would report that
the latest commit attempt passed. A commit whose hook ran leaves the hook's own
banner in the recorded output, so the banner is the discriminator, and a
commit attempt whose output shows no hook run is — as the clause says — not
governed here and keeps its existing classification.

A COMMIT ROUTED THROUGH THE SANDBOX RUNNER IS READ FROM THE RUNNER'S REPORT.
"A commit leg completes past one tool call" (`bd-ib-atyefi`) has the agent
start each commit through `livespec-commit-runner.py` and wait on it in later
tool calls; both of those calls exit 0 whatever the hook decided, so the
tool call's own exit status says nothing. `CommitRunnerReplay` drives the
`DetachedCommitRunner` state machine from the recorded `start` and `wait`
reports instead, and each runner `start` is a new attempt: a run that ends
with that attempt still `running`, or `no-verdict`, reports no refusal here,
because an earlier attempt's refusal is not the latest attempt's verdict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner import (
    CommitRunResult,
    result_from_observation,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_program import (
    HOOK_BANNER_PATTERN,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_replay import (
    CommitRunnerReplay,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroInspectResult

__all__: list[str] = [
    "HookVerdict",
    "hook_verdict_cause_lines",
    "hook_verdict_for",
    "hook_verdict_from_events",
    "innermost_cause_label",
]

# The lefthook banner a hook run prints; the sandbox runner reports the same test.
_HOOK_BANNER = re.compile(HOOK_BANNER_PATTERN)

# `git commit` as an invoked command rather than as a quoted search pattern.
_GIT_COMMIT = re.compile(r"\bgit commit\b")

# An agent sentence that describes the hook as having NOT reached a verdict.
_INTERRUPTION_CLAIM = re.compile(
    (
        r"did not (?:complete|finish)|not completed|incomplete hook|interrupt|terminat|"
        r"timed? ?out|killed|cut off|hung|stall"
    ),
    re.IGNORECASE,
)

_TOOL_CALL = "tool_call"
_TOOL_CALL_UPDATE = "tool_call_update"


@dataclass(frozen=True, kw_only=True)
class HookVerdict:
    """The recorded result of the latest hook-running commit attempt of one stage.

    `failed_targets` is what the hook's own output named; a commit-msg refusal
    names none and the exit status alone is the verdict.
    """

    node: str
    exit_code: int
    failed_targets: tuple[str, ...]


def hook_verdict_for(
    *, inspect: FabroInspectResult | None, stages: tuple[str, ...] | None
) -> HookVerdict | None:
    """The terminal mapper's one-line entry: the causal verdict's LAST stage, or nothing.

    A one-liner at the call site on purpose: `_dispatcher_fabro_terminal` sits at
    its file-size ceiling, and the conditions it would otherwise spell out — no
    inspect result, no established causal stage — are the reader's own answers.
    """
    return hook_verdict_from_events(
        events_payload=None if inspect is None else inspect.events_payload,
        stage=stages[-1] if stages else None,
    )


def hook_verdict_from_events(
    *, events_payload: object | None, stage: str | None
) -> HookVerdict | None:
    """The refused verdict of `stage`'s latest hook-running commit attempt, or None.

    None is the ordinary answer: no readable stream, no commit attempt whose
    output shows a hook ran, or a latest such attempt that PASSED. A passing
    latest attempt is not a refusal to report, whatever an earlier attempt did.
    """
    if stage is None or not isinstance(events_payload, list):
        return None
    node = _node_id(stage=stage)
    commands: dict[str, str] = {}
    replay = CommitRunnerReplay()
    latest: CommitRunResult | None = None
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
        if update.get("sessionUpdate") == _TOOL_CALL:
            commands[call_id] = _command(update=update)
        if update.get("sessionUpdate") == _TOOL_CALL_UPDATE:
            completion = _completed_commit(
                update=update, command=commands.get(call_id, ""), replay=replay
            )
            if completion is not None:
                latest = completion
    if latest is None or latest.state != "failed" or latest.exit_code is None:
        return None
    return HookVerdict(node=node, exit_code=latest.exit_code, failed_targets=latest.failed_targets)


def hook_verdict_cause_lines(
    *, verdict: HookVerdict | None, agent_cause: str | None
) -> tuple[str, ...]:
    """The needs-human cause's account of the recorded refusal, when there is one.

    OUR OWN TEXT, so it does not pass through the comment sanitizer: the node is
    a graph node id, the exit status an integer, and the target names are recipe
    names the gate itself printed.
    """
    if verdict is None:
        return ()
    targets = ", ".join(verdict.failed_targets) if verdict.failed_targets else "none named"
    lines = [
        (
            f"recorded hook verdict: the {verdict.node} stage's latest commit attempt completed "
            f"with exit status {verdict.exit_code} after its hook ran; failed targets: {targets}"
        )
    ]
    if _contradicted(verdict=verdict, agent_cause=agent_cause):
        refusal = (
            "recorded refusal: the innermost cause above is agent-reported and describes the "
            "hook as not completed; the run's recorded output shows the hook completed with "
            "that refusal"
        )
        lines.append(refusal)
    return tuple(lines)


def innermost_cause_label(*, verdict: HookVerdict | None, agent_cause: str | None) -> str:
    """`innermost cause (agent-reported)` when the record contradicts the agent's text."""
    if _contradicted(verdict=verdict, agent_cause=agent_cause):
        return "innermost cause (agent-reported)"
    return "innermost cause"


def _contradicted(*, verdict: HookVerdict | None, agent_cause: str | None) -> bool:
    return (
        verdict is not None
        and agent_cause is not None
        and _INTERRUPTION_CLAIM.search(agent_cause) is not None
    )


def _completed_commit(
    *, update: dict[str, object], command: str, replay: CommitRunnerReplay
) -> CommitRunResult | None:
    """The commit attempt's result when this completion is a commit or runner call."""
    raw_output = _mapping(value=update.get("rawOutput"))
    exit_code = raw_output.get("exit_code")
    output = raw_output.get("formatted_output")
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        return None
    if not isinstance(output, str):
        return None
    runner_result = replay.observe(command=command, output=output)
    if runner_result is not None:
        return runner_result
    if _GIT_COMMIT.search(command) is None or _HOOK_BANNER.search(output) is None:
        return None
    return result_from_observation(exit_code=exit_code, output=output)


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


def _node_id(*, stage: str) -> str:
    """`implement` for `implement`, `implement@1` and `050-implement@1` alike."""
    return re.sub(r"^\d+-", "", stage.split("@", maxsplit=1)[0].strip())


def _mapping(*, value: object) -> dict[str, object]:
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}
