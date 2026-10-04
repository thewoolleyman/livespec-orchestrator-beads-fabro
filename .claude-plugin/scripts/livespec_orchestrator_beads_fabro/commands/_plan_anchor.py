"""The plan anchor marker, and its discrimination from a spec commitment.

A plan is anchored in the ledger by one epic, and that epic is stamped with
`spec_commitment_hint = "plan:<slug>"` so the plan's topic is recoverable
from the ledger alone. The store bridge maps `spec_commitment_hint` onto
the beads-native `spec_id` column — the SAME column a genuine commitment
to ratified spec text uses. The field is therefore OVERLOADED, and every
consumer of it is really asking one of two different questions.

⛔ PRESENCE IS NOT THE ANSWER TO EITHER QUESTION. A consumer that tests
the field for presence alone answers "was this created by the plan
primitive", not "does this commit to ratified spec text" — and it answers
it with the wrong one's name. FOUR consumers did exactly that, and the
collision made every plan epic permanently non-disposable: the
disposition guard refused every plan child, so the archive gate never
opened; the calibration proxy counted a plan anchor as touching spec
surface; the admission-policy resolver pinned every plan-anchored item to
the manual floor that config cannot override; and the GOAL RENDERER —
the fourth, and the only one whose blast radius is the brief itself
rather than a routing decision — told every plan-stamped item's
implementing agent it was working under a commitment to ratified spec
text.

FOUR IS EVIDENCE, NOT A TALLY OF SLIPS: it says which predicate is
attractive, and the preconditions that make it attractive are permanent
(see the un-overloading paragraph below). So a FIFTH will be written, and
a docstring does not fail a build. The check
`spec_id_presence_discipline` under `dev-tooling/checks/` makes this rule
executable — it fails on a bare presence or truthiness test anywhere in
the package outside a measured allowlist, and carries its own positive
controls so it cannot report a clean scan while blind.

THE DISCRIMINATOR IS THE PREFIX. It is well-aimed rather than merely
convenient — a genuine `spec_id` is an obligation `id_hint` parsed out of
proposed-change front-matter, and those are bare slugs, while the plan
prefix is punctuated in a way no obligation slug is.

⚠ BUT THE INPUT IS NOT SCHEMA-CONSTRAINED, and an earlier version of this
paragraph claimed it was. The front-matter pattern governs obligation
id_hints; it does NOT govern everything that can reach this column.
Measured on this tenant, `bd-ib-6huwuq` carries a native `spec_id` of
free-form prose — spaces, a slash, commas and quotes — so whatever wrote
it was not bound by that pattern, and the pattern therefore cannot be the
reason a plan-prefixed collision is impossible. Nothing is misclassified
today: no live value both starts with the plan prefix and represents a
genuine commitment, so both predicates return the right answer for every
record. The correction is to the ARGUMENT, not to the behaviour — the
discriminator rests on "no such value exists today", not on "the schema
forbids one", and a reader must not conclude the input is validated.

Un-overloading the field was considered and rejected for this module's
change: `WorkItem` is defined in the vendored runtime, so splitting the
field would take an upstream runtime change plus a data migration across
every live tenant, and adopter tenants are not hand-edited.

The literal lives here ONCE, and both the minting side (`plan_anchor_epic`,
the only place a marker is created) and every reading side import it from
here, so the two halves cannot drift apart again.

WHAT NARROWING THESE PREDICATES DOES NOT DO. Plan-prefixed values REMAIN in
the spec id field: this module narrows predicates only — it relocates no
data and migrates no tenant. Two components consume that `plan:<slug>` FORM
and must keep working:

- `_needs_attention_handoffs._plan_topic` (this repo) recovers a plan's
  topic slug from the marker.
- `_registry_epic.py` in the SEPARATE `livespec-overseer` repository reads
  the same form to key its plan registry. It is named here so a future
  contributor tidying this field finds the cross-repository dependent in
  this repo's record rather than discovering it afterwards. Its read is a
  disjunction whose second arm falls back to the metadata `plan_slug`, so
  no epic there depends on the spec id arm today.

Both are also CORRECT-PREDICATE PRECEDENT: each already discriminates on
the prefix rather than on presence.
"""

from __future__ import annotations

from livespec_runtime.work_items.rank import key_between

from livespec_orchestrator_beads_fabro._ids import new_work_item_id
from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    PlanDefinitionOfDone,
    plan_definition_of_done_section,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "PLAN_HINT_PREFIX",
    "is_plan_anchor",
    "is_spec_commitment",
    "plan_anchor_epic",
]

PLAN_HINT_PREFIX = "plan:"


def is_plan_anchor(*, spec_id: str | None) -> bool:
    """Whether the hint marks a plan anchor rather than committing to spec text."""
    return spec_id is not None and spec_id.startswith(PLAN_HINT_PREFIX)


def is_spec_commitment(*, spec_id: str | None) -> bool:
    """Whether the hint commits its work-item to ratified spec text.

    The question the spec-change-tier consumers mean to ask. An absent or
    empty hint commits to nothing, and a plan anchor marker commits to
    nothing either — it names where the work is TRACKED, not what the
    specification REQUIRES.
    """
    return bool(spec_id) and not is_plan_anchor(spec_id=spec_id)


def plan_anchor_epic(
    *,
    prefix: str,
    slug: str,
    title: str,
    now: str,
    definition_of_done: PlanDefinitionOfDone,
) -> WorkItem:
    """Mint the ledger epic that anchors one plan topic.

    The ONE place a plan anchor marker is created. The returned epic is not
    yet persisted; the caller owns the store write.

    The description carries the plan's Definition of Done as its FIRST heading,
    with the anchor prose ahead of it — the position the plan clause fixes, and
    the one that keeps the anchor line out of the graded section body.
    """
    return WorkItem(
        id=new_work_item_id(prefix=prefix),
        type="epic",
        status="backlog",
        title=title,
        description=(
            f"Plan anchor for plan/{slug}.\n\n"
            f"{plan_definition_of_done_section(definition=definition_of_done)}"
        ),
        origin="freeform",
        gap_id=None,
        rank=key_between(a=None, b=None),
        assignee=None,
        depends_on=(),
        captured_at=now,
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=f"{PLAN_HINT_PREFIX}{slug}",
        notes=f"plan_slug={slug}",
    )
