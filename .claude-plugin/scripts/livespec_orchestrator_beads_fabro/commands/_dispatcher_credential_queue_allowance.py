"""The credential queue allowance one dispatch resolved, and the layer that gave it.

`SPECIFICATION/contracts.md`'s worker-credential-projection section governs
`dispatcher.credential_queue_allowance_seconds`: a COMMITTED-ONLY positive
integer of seconds, default 86400, which bounds how long a run may sit between
the instant its credential was projected and its first coding-agent launch. Its
resolution and journaling follow the whole-run wall budget key, so the coercion,
the layer names and the journal shape are that module's rather than new ones.

WHAT THIS FIGURE IS FOR, because it is easy to read as a second wall budget and
it is not. The wall budget bounds RUNNING time and excludes the queue
deliberately -- a run that waits four hours for a factory slot has spent none of
its budget. That exclusion is correct for slot accounting and wrong for a
credential: the queue is exactly the interval that ages a projected credential
while nothing is running, and the credential-use deadline is anchored at
projection precisely so that aging counts. This key is therefore how much of
that aging a dispatch is willing to absorb before a first launch is refused
rather than permitted to start against a credential most of whose life went to
waiting.

WHY IT IS COMMITTED-ONLY, with no per-dispatch argument beside the wall budget's
`--run-wall-budget-seconds`. The figure is half of the bound the in-sandbox guard
enforces, and the guard reads an ABSOLUTE instant the host stamped -- so a
per-invocation widening would move a bound the sandbox has already been handed,
on the one surface where the host and the worker are required to use ONE figure.
A repository that genuinely queues longer raises the committed key, which is a
change a reviewer can see.

THE DEFAULT IS A CEILING AND NOT A TARGET, exactly as the wall budget's is.
86400 seconds is a day, which is far wider than any healthy queue: the measured
hp queues are minutes. What the default must never do is sit so low that an
ordinary wait refuses a dispatch, and what it must never be is unbounded -- an
unbounded queue allowance makes the credential-use window larger than any graph
allowance, which retires the smaller-of-two rule and restores the defect it was
ratified to fix.

THE COERCION IS THE NODE TIMEOUTS' OWN, imported rather than re-written for the
reason `_dispatcher_run_wall_budget` imports it: a second coercion is a second
place to forget that `bool` is an `int` in Python, and `true` in a config file
resolving to a one-second queue allowance both passes a naive validation and
refuses every dispatch that queued at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    REPOSITORY_LAYER,
    WORKFLOW_DEFAULT_LAYER,
    positive_int_seconds,
)

__all__: list[str] = [
    "CREDENTIAL_QUEUE_ALLOWANCE_KEY",
    "DEFAULT_CREDENTIAL_QUEUE_ALLOWANCE",
    "DEFAULT_CREDENTIAL_QUEUE_ALLOWANCE_SECONDS",
    "CredentialQueueAllowance",
    "credential_queue_allowance_from_block",
    "credential_queue_allowance_journal_record",
]

_CREDENTIAL_QUEUE_ALLOWANCE_BLOCK_KEY = "credential_queue_allowance_seconds"

# The key as an operator spells it, so the refusal below names the surface that
# has to be edited rather than paraphrasing it.
CREDENTIAL_QUEUE_ALLOWANCE_KEY = f"dispatcher.{_CREDENTIAL_QUEUE_ALLOWANCE_BLOCK_KEY}"

DEFAULT_CREDENTIAL_QUEUE_ALLOWANCE_SECONDS = 86_400


@dataclass(frozen=True, kw_only=True)
class CredentialQueueAllowance:
    """One dispatch's credential queue allowance, and which layer supplied it.

    `seconds` is an INTEGER rather than the float `RunWallBudget` carries,
    because nothing compares this figure against a measured wall-clock span: it
    is summed with the wall budget into the credential-use window and that sum
    is stamped into an absolute epoch, so a float would only invite a
    fractional deadline the guard cannot express.

    The LAYER rides with the value for the reason it rides with the wall
    budget's: 86400 seconds is the fleet default on one target and a deliberate
    repository decision on another, and only the layer says whether raising the
    key would have admitted a refused dispatch or whether it had already been
    raised.
    """

    seconds: int
    layer: str


# The fully-defaulted allowance: what a dispatch target declaring nothing
# resolves to. A VALUE as well as a resolution so a caller that needs one in a
# signature or a dataclass default does not have to carry None and make every
# reader branch on an absence with a perfectly good answer.
DEFAULT_CREDENTIAL_QUEUE_ALLOWANCE = CredentialQueueAllowance(
    seconds=DEFAULT_CREDENTIAL_QUEUE_ALLOWANCE_SECONDS,
    layer=WORKFLOW_DEFAULT_LAYER,
)


def credential_queue_allowance_from_block(
    *, block: dict[str, Any]
) -> CredentialQueueAllowance | str:
    """Resolve the allowance from a dispatcher config block, or refuse by name.

    Returns the resolution, or an actionable refusal message NAMING THE KEY. The
    caller routes that message as a failed dispatch BEFORE any Fabro run exists,
    which is what the clause requires of a non-positive or non-integer value:
    the figure is half of a bound the sandbox is handed as an absolute instant,
    so a value this resolution cannot read is one no guard could enforce, and
    discovering it by watching a run die is the expensive route.

    An ABSENT key is the documented default rather than a refusal, because a
    repository declaring nothing is an ordinary repository and 86400 is the
    figure the clause names for it.
    """
    raw: object = block.get(_CREDENTIAL_QUEUE_ALLOWANCE_BLOCK_KEY)
    if raw is None:
        return DEFAULT_CREDENTIAL_QUEUE_ALLOWANCE
    seconds = positive_int_seconds(value=raw)
    if seconds is None:
        return (
            f"{CREDENTIAL_QUEUE_ALLOWANCE_KEY} must be a positive integer of seconds; "
            f"got {raw!r}"
        )
    return CredentialQueueAllowance(seconds=seconds, layer=REPOSITORY_LAYER)


def credential_queue_allowance_journal_record(
    *, allowance: CredentialQueueAllowance
) -> dict[str, object]:
    """Project the resolved allowance for the dispatch record.

    One nested object rather than two sibling keys, so a reader joining the
    figure to its layer cannot pick up one from a record that carried the
    other -- the same shape `run_wall_budget_journal_record` gives the budget
    this figure is summed with.
    """
    return {
        "credential_queue_allowance": {
            "seconds": allowance.seconds,
            "layer": allowance.layer,
        }
    }
