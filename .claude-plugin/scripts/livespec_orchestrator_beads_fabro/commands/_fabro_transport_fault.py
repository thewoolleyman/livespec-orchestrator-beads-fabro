"""An ACP TRANSPORT fault, told apart from an agent that asked a question.

The engine reports EVERY one of these under the single stage label `ACP turn
failed`, and the label is the one thing that carries no information. Measured
families behind it: a shell call the harness moved to a background task, an
adapter process that exited before the protocol handshake, a turn that reached
its ceiling, and a provider spend ceiling
(`plan/pr-stage-backgrounded-push-fault/research/001-failure-analysis-and-mechanism-candidates-2026-10-08.md`
sections 3.6 and 4; `bd-ib-g56f`, `bd-ib-9ek4`, `bd-ib-qulf`). So this module
keys on the CAUSE and never on the label — a classifier that keyed on the label
would conflate all four and report whichever family it happened to be written
for.

WHAT IS AND IS NOT A TRANSPORT FAULT, which is the distinction the whole module
exists to hold. A transport fault is the CARRIER between the engine and the
agent breaking. It is NOT evidence that an agent asked anything, so it must not
be rendered as a decision request; and it is NOT a provider refusal, which is
the agent's model declining to work rather than the transport failing to carry
it. `None` is therefore a first-class answer: a provider ceiling, an agent's own
structured needs-human ending, and a plain node failure all return it, and the
caller renders each under its own account.

THE PROVIDER CEILING IS DELIBERATELY NOT A FAMILY HERE even though it shares
the `ACP turn failed` label, because it already has a typed classification of
its own (`FabroFailureDetail.provider_usage_limit` plus its vendor) that an
admission gate consumes. Adding a second name for it would give one condition
two classifications that could disagree.

EACH MARKER IS MEASURED, AND THE LOOSEST ONE IS LAST. The backgrounded wording
is the one the engine's own parser keys on
(`lib/crates/fabro-acp/src/session.rs`, fork commit `4b8cc85e0`,
`bd-ib-bindom`) and was carried verbatim by both runs in the cited research;
the adapter-exit wording was measured on `bd-ib-qulf`. The timeout marker is
the broadest, so it is tested only after the two specific ones have been ruled
out — a backgrounded cause that also mentions a timeout must classify as
backgrounded, because that is the condition with the remedy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__: list[str] = [
    "ADAPTER_EXITED",
    "BACKGROUNDED_TOOL",
    "TURN_TIMED_OUT",
    "TransportFault",
    "transport_fault_clause",
    "transport_fault_from_cause",
]

BACKGROUNDED_TOOL = "backgrounded-tool"
ADAPTER_EXITED = "adapter-exited"
TURN_TIMED_OUT = "turn-timed-out"

_BACKGROUNDED_MARKER = "continued in background"
_ADAPTER_EXITED_MARKER = "exited before protocol completed"
_TIMED_OUT_MARKERS = ("timed out", "timeout")

# The measured cause reads `ACP tool call <id> (<the command>) continued in
# background as task <task>; Fabro terminated the turn ...`. The command is
# GREEDY up to the marker because a shell pipeline can itself carry
# parentheses; the task id is `[\w-]+` so it stops at the clause's semicolon
# rather than swallowing the sentence after it.
_BACKGROUNDED_RE = re.compile(
    r"\((?P<command>.+)\)\s+continued in background(?:\s+as task\s+(?P<task>[\w-]+))?",
    re.DOTALL | re.IGNORECASE,
)

_FAMILY_CLAUSES: dict[str, str] = {
    BACKGROUNDED_TOOL: (
        "the harness moved a shell call into a background task and the engine ended "
        "the turn rather than let the agent work beside a detached process"
    ),
    ADAPTER_EXITED: "the ACP adapter process exited before the protocol completed",
    TURN_TIMED_OUT: "the ACP turn reached its ceiling before the agent finished it",
}


@dataclass(frozen=True, kw_only=True)
class TransportFault:
    """One classified ACP transport fault.

    `command` and `task_id` are populated only for the backgrounded family, and
    only when the cause names them: the engine owns that wording, so a cause
    that classifies but does not name its command yields the family alone
    rather than an invented command. They are carried rather than left for each
    consumer to re-match out of `cause` prose, which is the same seam rationale
    `provider_usage_limit` rides.
    """

    family: str
    command: str | None
    task_id: str | None


def transport_fault_from_cause(*, cause: str | None) -> TransportFault | None:
    """Classify one innermost failure cause, or None when it is not a transport fault."""
    if cause is None:
        return None
    lowered = cause.lower()
    if _BACKGROUNDED_MARKER in lowered:
        return _backgrounded(cause=cause)
    if _ADAPTER_EXITED_MARKER in lowered:
        return TransportFault(family=ADAPTER_EXITED, command=None, task_id=None)
    if any(marker in lowered for marker in _TIMED_OUT_MARKERS):
        return TransportFault(family=TURN_TIMED_OUT, command=None, task_id=None)
    return None


def transport_fault_clause(*, fault: TransportFault) -> str:
    """One operator-facing clause naming the family and whatever it identified."""
    clauses = [f"transport fault ({fault.family}): {_FAMILY_CLAUSES[fault.family]}"]
    if fault.command is not None:
        clauses.append(f"the backgrounded command was `{fault.command}`")
    if fault.task_id is not None:
        clauses.append(f"background task {fault.task_id}")
    return "; ".join(clauses)


def _backgrounded(*, cause: str) -> TransportFault:
    match = _BACKGROUNDED_RE.search(cause)
    if match is None:
        return TransportFault(family=BACKGROUNDED_TOOL, command=None, task_id=None)
    command = match.group("command").strip()
    return TransportFault(
        family=BACKGROUNDED_TOOL,
        command=command or None,
        task_id=match.group("task"),
    )
