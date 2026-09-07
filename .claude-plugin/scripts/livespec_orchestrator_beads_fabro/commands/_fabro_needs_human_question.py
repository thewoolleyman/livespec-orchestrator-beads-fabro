"""Why a TERMINATED factory run routed its work-item to a human, read off `inspect`.

Contract v093 in `SPECIFICATION/contracts.md` — the clause ruling that a
factory run never awaits a human — settles the shape this module is written
against, and it is the opposite of the obvious one. A factory run NEVER
parks on a question: a
needs-human outcome terminates the run non-green, preserves its tree by
reference, and rests the work-item at `blocked` with lane reason
`needs-human`. The ledger is the only place a human decision waits, and the
human's answer is a ledger valve — `resolve-blocked:<item-id>:ready` — never
an answer sent to a live run.

So the question this module reads is a fact about a DEAD run. There is
nothing to resume and nothing to answer on the factory side; what the
`needs_human` terminal node left behind is the only account of WHY the loop
gave up and WHERE the work survived, and today that account is visible
nowhere — the ledger item carries its title and nothing else.

Do NOT gate any read here on a run STATUS. A terminated run is `failed`, and
a park-shaped status filter would match nothing while reporting cleanly, which
is the wrong-instrument failure this repository catalogues. The discriminator
is the terminal node's own evidence, in two independent forms:

- the `LIVESPEC_NEEDS_HUMAN` sentinel the node writes to stderr before
  exiting 1, and
- a checkpoint whose `next_node_id` names the `needs_human` terminal.

Either alone is sufficient, and reading BOTH is what lets the sentinel leg be
narrow. The checkpoint leg reuses `_fabro_escalation`, whose `next_node_id`
structure was MEASURED on run 01M10CYZ8S9TNPZ2MW096NJW7V. Keep the sentinel
literal in lockstep with the workflows via `_dispatcher_plan.NEEDS_HUMAN_MARKER`.

THE ALL-STRINGS SEARCH THIS MODULE ONCE PERFORMED WAS WRONG, and the premise
that justified it — "the token is OURS, so it cannot appear by accident" — was
true and beside the point. The token does not appear by ACCIDENT; it appears
BY CONSTRUCTION, in the one place present in every record this reader ever
runs against. A fabro stage record carries the node's OWN SCRIPT SOURCE (its
status note reads `Script completed: <the whole script>`), and the
`needs_human` script CONTAINS every sentinel literal because it is the script
that echoes them. The script source sits earlier in the record than the output
does, so the first match was shell text.

MEASURED 2026-09-07 on run 01M1X6JBV2M1CCQCCEVNTJ2YXE, the groom propose phase
for bd-ib-z2ctra. The run wrote a 3,237-character drafted decomposition behind
the sentinel; what this reader returned, and what reached the ledger as the
approvable groom draft, was 333 characters of shell beginning
`$(head -n 1 /tmp/livespec-groom-draft)" >&2; else echo ...`.

So the sentinel is read from the run's OUTPUT: `_sentinel_lines` collects only
under output-bearing keys and refuses SCRIPT-SOURCE keys outright, at every
depth. Preferring the LAST match instead would not have fixed this — it would
make the answer depend on the serialization order of a record this code does
not own. Losing the read outright is the fail-CLOSED direction and is
survivable: the checkpoint leg still reports the routing, the attention row
degrades to "the run record carries no needs-human message", and the groom
park journals a skip naming the absent draft. Returning the WRONG text is not
survivable, because the groom apply phase acts on it.

WHY THE PAYLOAD CARRIES NO OFFERED OPTIONS, which is a deliberate absence and
not an oversight. Under v093 a terminated run cannot offer any: the former
`[R] Retry / [I] Re-implement / [A] Abandon` answers became ledger valves when
the `escalate` hexagon was replaced by this dead-end node. Scraping a run
record for options would be hunting for a shape the ratified contract forbids
from existing. The offered options are the valves, and naming them belongs to
the lane that renders the item, not to a reader of the run.

`tree_preserved` is carried separately from `preserved_ref` because the two
answer different questions and the expensive mistake is conflating them. The
node pushes best-effort; when the push FAILS it says so and no ref exists. A
human choosing to rework from the preserved tree needs to know that the tree
is not there before choosing, so a failed push is reported as a fact rather
than as a missing ref.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import NEEDS_HUMAN_MARKER
from livespec_orchestrator_beads_fabro.commands._fabro_escalation import (
    ESCALATION_NODE_ID,
    fabro_escalation_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import fabro_inspect_record

__all__: list[str] = [
    "NEEDS_HUMAN_NODE_ID",
    "NeedsHumanQuestion",
    "needs_human_question_from_payload",
]

# The workflow's terminal node id, shared with the escalation reader so one
# rename cannot leave two modules disagreeing about which node this is.
NEEDS_HUMAN_NODE_ID = ESCALATION_NODE_ID

# The three sentinels the `needs_human` script writes to stderr, all derived
# from the ONE shared marker so a workflow edit cannot desynchronise them.
# `_PRESERVED` and `_PUSH_FAILED` both CONTAIN the bare marker, so every match
# below keys on the colon-terminated form that distinguishes them.
_PROMPT_SENTINEL = f"{NEEDS_HUMAN_MARKER}: "
_PRESERVED_SENTINEL = f"{NEEDS_HUMAN_MARKER}_PRESERVED: "
_PUSH_FAILED_SENTINEL = f"{NEEDS_HUMAN_MARKER}_PUSH_FAILED"

# Keys whose value is a node's OWN SCRIPT SOURCE rather than anything the run
# emitted, refused at EVERY depth including inside an output subtree. `notes`
# is the measured carrier — a fabro stage status note reads `Script completed:
# <the whole script>` — and the rest are the names a record could plausibly
# give the same text.
_SCRIPT_SOURCE_KEYS = frozenset(
    {
        "acp.command",
        "args",
        "argv",
        "cmd",
        "command",
        "notes",
        "script",
        "script_source",
    }
)

# Keys carrying what a node WROTE. The sentinel is read from under these and
# nowhere else, so no literal a node merely CONTAINS can answer for what it
# said. `failure_reason` is the field the measured run's terminal stage status
# carried the real line in; the rest are the ordinary output names.
_OUTPUT_KEYS = frozenset(
    {
        "error",
        "failure_reason",
        "log",
        "logs",
        "message",
        "output",
        "stderr",
        "stdout",
    }
)


@dataclass(frozen=True, kw_only=True)
class NeedsHumanQuestion:
    """The terminated run's own account of why it routed the item to a human.

    Every field is independently optional because each comes from a different
    sentinel or structure, and a record carrying only one of them is still
    worth surfacing: the alternative is the status quo, where the ledger item
    says nothing but its title.
    """

    prompt: str | None
    reason: str | None
    preserved_ref: str | None
    tree_preserved: bool


def needs_human_question_from_payload(*, payload: object | None) -> NeedsHumanQuestion | None:
    """The needs-human account this run left, or `None` if it left none.

    `None` says the record shows no needs-human ending — neither the sentinel
    nor a checkpoint routing to the terminal node. It never means "ended that
    way but said nothing": a run whose sentinel is present but whose text is
    unreadable still yields a question, because the ROUTING is itself the fact
    a human needs.
    """
    record = fabro_inspect_record(payload=payload)
    if record is None:
        return None
    lines = _sentinel_lines(value=record)
    routed = _routed_to_terminal(record=record)
    if not lines and not routed:
        return None
    return NeedsHumanQuestion(
        prompt=_after(lines=lines, sentinel=_PROMPT_SENTINEL),
        reason=_engine_reason(record=record),
        preserved_ref=_after(lines=lines, sentinel=_PRESERVED_SENTINEL),
        tree_preserved=not any(_PUSH_FAILED_SENTINEL in line for line in lines),
    )


def _routed_to_terminal(*, record: dict[str, Any]) -> bool:
    """Whether any checkpoint routes to the needs-human terminal node."""
    for checkpoint in _checkpoint_mappings(record=record):
        candidate: object = checkpoint.get("next_node_id")
        if isinstance(candidate, str) and candidate.strip() == NEEDS_HUMAN_NODE_ID:
            return True
    return False


def _checkpoint_mappings(*, record: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Every checkpoint mapping on the record, wrappers and nested state alike.

    Deliberately looser than `_fabro_escalation`'s own walk: that reader needs
    the NEWEST checkpoint because it is discriminating between two endings,
    while this one only asks whether the terminal was ever routed to.
    """
    found: list[dict[str, Any]] = []
    entries: object = record.get("checkpoints")
    if isinstance(entries, list):
        for entry in cast("list[object]", entries):
            if not isinstance(entry, dict):
                continue
            typed = cast("dict[str, Any]", entry)
            found.append(typed)
            nested: object = typed.get("checkpoint")
            if isinstance(nested, dict):
                found.append(cast("dict[str, Any]", nested))
    top_level: object = record.get("checkpoint")
    if isinstance(top_level, dict):
        found.append(cast("dict[str, Any]", top_level))
    return tuple(found)


def _engine_reason(*, record: dict[str, Any]) -> str | None:
    """Why the loop routed here, when the ENGINE routed it rather than an agent.

    `None` is the agent-reported ending — a node that SUCCEEDED and rode a
    conditional edge — which records no loop failure signature. That absence is
    itself informative, so the lane renders the two differently rather than
    treating a missing reason as a missing read.
    """
    escalation = fabro_escalation_from_payload(payload=record)
    if escalation is None:
        return None
    return ", ".join(escalation.loop_failure_signatures)


def _after(*, lines: tuple[str, ...], sentinel: str) -> str | None:
    """The text following the first occurrence of one sentinel."""
    for line in lines:
        index = line.find(sentinel)
        if index >= 0:
            trailing = line[index + len(sentinel) :].strip()
            if trailing != "":
                return trailing
    return None


def _sentinel_lines(*, value: object) -> tuple[str, ...]:
    """Every line carrying a needs-human sentinel, from the record's OUTPUT.

    Collected under output-bearing keys only and never under a script-source
    key, so the `needs_human` node's own script — which contains every sentinel
    literal by construction — cannot supply a line. The module docstring
    carries the measured substitution this rule exists to prevent.

    Lines are kept VERBATIM rather than stripped. The sentinels this feeds are
    colon-and-space terminated, so trimming a line would silently unmatch a
    sentinel whose message is empty — and that is precisely the case `_after`
    exists to reject rather than report as content.
    """
    return _lines_in(value=value, under_output=False)


def _lines_in(*, value: object, under_output: bool) -> tuple[str, ...]:
    """The sentinel lines in one subtree; `under_output` names the key it hangs from.

    A string answers only when an output-bearing key is above it. Containers
    are walked either way, because the output key can sit at any depth and the
    record's shape is fabro's to change.
    """
    if isinstance(value, str):
        if not under_output:
            return ()
        return tuple(line for line in value.splitlines() if NEEDS_HUMAN_MARKER in line)
    if isinstance(value, dict):
        return _lines_in_mapping(mapping=cast("dict[str, Any]", value), under_output=under_output)
    if isinstance(value, list):
        entries = cast("list[object]", value)
        return tuple(
            line for item in entries for line in _lines_in(value=item, under_output=under_output)
        )
    return ()


def _lines_in_mapping(*, mapping: dict[str, Any], under_output: bool) -> tuple[str, ...]:
    """One mapping's sentinel lines, script-source keys dropped whole."""
    found: list[str] = []
    for key, item in mapping.items():
        folded = key.casefold()
        if folded in _SCRIPT_SOURCE_KEYS:
            continue
        nested = under_output or folded in _OUTPUT_KEYS
        found.extend(_lines_in(value=item, under_output=nested))
    return tuple(found)
