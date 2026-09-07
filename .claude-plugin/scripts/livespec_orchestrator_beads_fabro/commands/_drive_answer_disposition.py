"""WHO may answer an attention item: the enforcer of the answer disposition.

The fifth dispatcher policy setting of the dispatcher-policy-settings contract
in `SPECIFICATION/contracts.md` (ratified in v104) governs who may answer an
ATTENTION ITEM — a work-item resting at `blocked` / `blocked_reason:
needs-human`, parked on a question. `drive` MUST refuse a
`resolve-blocked:<work-item-id>:ready|backlog` press CARRYING `--answer` that
the item's effective answer disposition does not admit, naming the work-item
and that disposition, mirroring the effective-manual `approve` refusal.

This module is that enforcer. Its sibling `_needs_attention_answer_disposition`
is the ADVERTISER: it reports the same disposition on the attention snapshot
and, under the advertiser-and-enforcer binding, offers no answer handoff this
module would refuse. Both read one resolver, `effective_answer_disposition`, so
the two can never disagree about an item.

WHAT MAKES A PRESS A HUMAN OPERATOR'S. The setting's values are ACTOR-CLASS
names, and so is the `<role>` half of the `<role>:<name>` identity convention
the journal-invoker-attribution contract in the same file recommends (its own
examples are `human:<name>`, `session:<session-name>`, `foreman:<seat>`,
`console:<principal>`). So the gate is a comparison between the two: the
`human` disposition admits a press whose invoker asserts the `human` role, and
when livespec core ratifies the consensus tier its role joins the `consensus`
entry of `_ADMITTED_ROLES` — the one place that table is written.

IT FAILS CLOSED, DELIBERATELY, AND THAT INCLUDES THE FALLBACK MARK. An identity
asserting no role at all — the derived `unattributed:<os-user>@<hostname>` MARK
above all — is not a human operator's press, and this repository has already
ruled on that direction where it matters most: the human-only clearance in
`_dispatcher_provider_exhaustion_clear` refuses the same mark outright, because
that mark is exactly the identity an unattended process carries by default.
Reading it as "a person at a shell" would therefore admit precisely the
automation the disposition exists to keep out.

A CALLER ACTING FOR A HUMAN ASSERTS THAT HUMAN, and the same contract already
says so ("callers acting on a human's explicit order SHOULD carry that human in
the identity they assert"). That is the point rather than a workaround: a
console or an agent pressing on an operator's explicit decision names them,
which makes "a human decided this" an attributable claim on the record instead
of an inference nobody can check later. And the two costs are not symmetric —
a refused press writes NOTHING, so an operator re-runs the identical action
seconds later, while an admitted answer is a ledger comment that can never be
edited or deleted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro._store_answer_disposition import (
    read_answer_disposition_labels,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_overrides import (
    effective_answer_disposition,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_ANSWER_DISPOSITION,
)
from livespec_orchestrator_beads_fabro.commands._drive_valve_result import valve_refusal

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._drive_answer import AnswerDelivery
    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "answer_press_refusal",
]

_HUMAN_ROLE = "human"
_ROLE_SEPARATOR = ":"

# The invoker roles each effective disposition admits as an answerer. Both
# entries name the human role today, and that is the ratified equivalence
# rather than a duplicate: `consensus` behaves as `human` until livespec core
# ratifies the consensus tier. Spelling it as a table keeps the equivalence
# where a reader can see it — and makes ratifying the tier one edit here rather
# than a search for every place the rule was implied.
_ADMITTED_ROLES: dict[str, frozenset[str]] = {
    "human": frozenset({_HUMAN_ROLE}),
    "consensus": frozenset({_HUMAN_ROLE}),
}


def answer_press_refusal(
    *, config: StoreConfig, item: WorkItem, aid: str, delivery: AnswerDelivery
) -> dict[str, Any] | None:
    """Refuse a press the item's effective answer disposition does not admit.

    `None` means ADMITTED, so the caller may go on to deliver the answer. A
    returned payload is a refusal that wrote nothing at all — it is graded
    before the ledger comment, the journal line and the status transition, so a
    refused press leaves the item exactly as it was resting.

    Taking the whole `delivery` rather than an answer string is what scopes the
    gate to the press the contract names: an invocation carrying no `--answer`
    has no delivery, so a plain `resolve-blocked` transition is never gated on
    who pressed it.
    """
    disposition = _effective_disposition(config=config, item=item, cwd=delivery.repo)
    admitted = _ADMITTED_ROLES.get(disposition, frozenset({_HUMAN_ROLE}))
    if _asserted_role(invoker=delivery.identity.invoker) in admitted:
        return None
    identities = ", ".join(f"{role}:<name>" for role in sorted(admitted))
    return valve_refusal(
        aid=aid,
        wid=item.id,
        err="answer-disposition-refused",
        msg=(
            f"resolve-blocked refused: the effective answer disposition for "
            f"{item.id} is {disposition}, which admits an answer only from "
            f"{identities}, and this press asserted {delivery.identity.invoker!r} "
            f"(resolved as {delivery.identity.invoker_source}). Nothing was "
            f"written; re-run naming the human who decided."
        ),
    )


def _effective_disposition(*, config: StoreConfig, item: WorkItem, cwd: Path) -> str:
    """This item's effective answer disposition, falling back to the safe default.

    Fail-SOFT in one direction only, and it is the safe one: `human` is the most
    restrictive disposition, so a repository configuration that cannot be read
    never widens who may answer.

    `unsafe_perform_io` is required rather than decorative — `IOResult.value_or`
    returns `IO[value]`, not the value, and an `IO` wrapper matches no
    disposition in the table above, which would refuse every press including a
    human's.
    """
    raw_labels = read_answer_disposition_labels(path=config).get(item.id, ())
    return unsafe_perform_io(
        effective_answer_disposition(item=item, cwd=cwd, raw_labels=raw_labels).value_or(
            DEFAULT_ANSWER_DISPOSITION
        )
    )


def _asserted_role(*, invoker: str) -> str:
    """The `<role>` half of a `<role>:<name>` identity, or `""` when none is asserted.

    An identity with no separator, or with a separator and no name after it,
    asserts no role. The empty-name case matters as much as the missing one:
    `resolve_invoker` already holds that an empty value is not an assertion, so
    a bare `human:` must not be allowed to claim the role that a named human
    would.
    """
    role, separator, name = invoker.partition(_ROLE_SEPARATOR)
    if separator == "" or name.strip() == "":
        return ""
    return role
