"""The one-shot plan-record migration's DECISIONS, held apart from its writes.

Per contracts.md's plan-record conformance clauses, one idempotent migration
runs per family tenant before the error-verdict checks arm there, and it owes
three obligations that are each a judgement about existing state: derive
a missing `plan_slug` and REFUSE a colliding derivation, anchor every plan
directory to its epic or to `unassigned`, and seed a typed `next_action` for
every open plan epic that lacks one.

THE DECISIONS LIVE HERE SO IDEMPOTENCE IS TESTABLE RATHER THAN MERELY INTENDED.
"Running it twice MUST change nothing the second time" is a property of what the
migration DECIDES, not of how it writes: `anchor_content` returns None when the
anchor already stands, and `slug_decisions` returns no decision at all for an
epic that already carries a slug. A second run therefore has nothing to hand its
writer, and the report says zero because there was zero to do — not because a
write was suppressed downstream.

REFUSAL IS A RESULT, NOT AN ERROR. A derived slug that another epic already
carries is reported with BOTH epic ids and left unwritten, because the collision
is genuinely ambiguous — two plans want one handle — and a migration that picked
a winner would silently rename somebody's plan. The refusal rides the report
beside the writes rather than aborting the run, so one ambiguous pair does not
strand the rest of the tenant.

A SLUG CLAIMED EARLIER IN THE SAME RUN COUNTS AS TAKEN. `plan_slug` MUST be
unique across a tenant's epics, so two untagged epics that derive the same slug
are the same collision as one deriving a slug already written — the first claims
it and the second is refused. Deciding both against the ledger as it stood at
the start of the run would write the duplicate the contract forbids.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._plan_anchor import (
    PLAN_HINT_PREFIX,
    is_plan_anchor,
)
from livespec_orchestrator_beads_fabro.commands._plan_identity import (
    UNASSIGNED_ANCHOR,
    canonical_plan_slug,
)
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    HUMAN_KIND,
    NONE_KIND,
    NextAction,
)
from livespec_orchestrator_beads_fabro.commands._plan_timeline import recorded_next_actions

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__: list[str] = [
    "MIGRATION_SESSION",
    "UNSEEDED_ACTION_TEXT",
    "PlanEpic",
    "PlanRecordMigrationReport",
    "SlugDecision",
    "anchor_content",
    "derived_plan_slug",
    "render_report",
    "seeded_next_action",
    "slug_decisions",
    "total_writes",
]

# The identity the migration stamps into `last_session`, so a reader of a
# seeded pointer can tell a migration's guess from a session's decision.
MIGRATION_SESSION = "plan-record-migration"
# The `kind: none` text. `text` MUST be one imperative sentence a person can act
# on without other context, and "the migration found nothing to seed from" is
# the whole truth about a pointer nobody has written yet.
UNSEEDED_ACTION_TEXT = "Record this plan's next action; the migration found none to seed from."

_NOTES_SLUG_PREFIX = "plan_slug="
_EXACTLY_ONE_ACTION = 1


@dataclass(frozen=True, kw_only=True)
class PlanEpic:
    """One ledger epic, projected onto the facts the migration decides from.

    `plan_slug` is the empty string when the epic carries none — the state the
    slug derivation exists to repair — and `notes` and `spec_commitment_hint`
    are empty when the record carries neither, because beads records are
    `omitempty`-sparse and a missing key is not evidence of anything. The hint
    is a plain `str` rather than `str | None` deliberately: the only question
    ever asked of it here is `is_plan_anchor`, and an absent-versus-empty
    distinction would invite the presence test that predicate exists to retire.
    """

    epic_id: str
    title: str
    notes: str
    spec_commitment_hint: str
    plan_slug: str
    is_open: bool
    has_next_action: bool


@dataclass(frozen=True, kw_only=True)
class SlugDecision:
    """The slug one untagged epic gains, or the epic already holding it.

    `holder_id` is None when the slug is free and the migration writes it; when
    it names an epic, that epic already carries the slug and this decision is a
    refusal reported for a human to resolve.
    """

    epic_id: str
    slug: str
    holder_id: str | None


@dataclass(frozen=True, kw_only=True)
class PlanRecordMigrationReport:
    """What one tenant's migration wrote, skipped, and refused."""

    slugs_written: tuple[str, ...]
    anchors_written: tuple[str, ...]
    next_actions_seeded: tuple[str, ...]
    skipped: tuple[str, ...]
    refused: tuple[str, ...]


def derived_plan_slug(*, epic: PlanEpic) -> str:
    """Derive an untagged epic's slug, in the precedence the contract states.

    The `plan:<slug>` anchor marker first, because it is what the plan
    front-end itself wrote; then a `plan_slug=<slug>` notes line, the form the
    anchor epic carries in prose; and only then the title, which is a guess
    rather than a record. Every route ends in the same canonicalization, so a
    written value equals its own canonicalization whichever route produced it.
    """
    if is_plan_anchor(spec_id=epic.spec_commitment_hint):
        return canonical_plan_slug(text=epic.spec_commitment_hint.removeprefix(PLAN_HINT_PREFIX))
    noted = _noted_slug(notes=epic.notes)
    if noted is not None:
        return canonical_plan_slug(text=noted)
    return canonical_plan_slug(text=epic.title)


def slug_decisions(*, epics: Sequence[PlanEpic]) -> tuple[SlugDecision, ...]:
    """Decide a slug for every epic carrying none, refusing a colliding one.

    An epic that already carries a slug produces NO decision — not a decision
    to leave it alone — which is what makes a second run's write count zero.
    """
    taken = {epic.plan_slug: epic.epic_id for epic in epics if epic.plan_slug != ""}
    decisions: list[SlugDecision] = []
    for epic in epics:
        if epic.plan_slug != "":
            continue
        slug = derived_plan_slug(epic=epic)
        holder = taken.get(slug)
        decisions.append(SlugDecision(epic_id=epic.epic_id, slug=slug, holder_id=holder))
        if holder is None:
            taken[slug] = epic.epic_id
    return tuple(decisions)


def anchor_content(*, current: str | None, epic_id: str | None) -> str | None:
    """Return the anchor line to write, or None when the anchor already stands.

    `epic_id` is None when no epic carries the directory's slug, which is the
    research-before-work-items state the literal `unassigned` records. The one
    rewrite is `unassigned` → the id of the epic that now carries the slug,
    exactly the completion `write_plan_anchor` performs; an anchor already
    naming an epic is write-once and returns None.
    """
    if current is None:
        return UNASSIGNED_ANCHOR if epic_id is None else epic_id
    if current.strip() == UNASSIGNED_ANCHOR and epic_id is not None:
        return epic_id
    return None


def seeded_next_action(*, handoff_body: str | None, prefix: str) -> NextAction:
    """Seed one open plan epic's typed pointer from its newest handoff body.

    A legacy handoff cannot supply an authoritative required result or budget,
    so even when its one recorded action names a work-item the migration writes
    `kind: human`: the work-item ref is retained and the text asks a maintainer
    to record the missing tracking before dispatch. A prose-only action also
    becomes `human` carrying its recorded text, and no/ambiguous action becomes
    `none`. Every migrated pointer therefore has the five-key shape without
    inventing a deadline or allowing unbounded continuation.
    """
    actions = () if handoff_body is None else recorded_next_actions(body=handoff_body)
    if len(actions) != _EXACTLY_ONE_ACTION:
        return NextAction(
            kind=NONE_KIND,
            ref="",
            text=UNSEEDED_ACTION_TEXT,
            required_result=None,
            budget=None,
        )
    [action] = actions
    ref = _work_item_ref(action=action, prefix=prefix)
    if ref is None:
        return NextAction(
            kind=HUMAN_KIND,
            ref="",
            text=action,
            required_result=None,
            budget=None,
        )
    return NextAction(
        kind=HUMAN_KIND,
        ref=ref,
        text=f"Confirm required-result tracking and budget before dispatching {ref}.",
        required_result=None,
        budget=None,
    )


def total_writes(*, report: PlanRecordMigrationReport) -> int:
    """Count every write one run made; zero is what idempotence looks like."""
    return len(report.slugs_written) + len(report.anchors_written) + len(report.next_actions_seeded)


def render_report(*, report: PlanRecordMigrationReport) -> str:
    """Render the per-tenant report of what was written, skipped, and refused.

    The write count leads because it is the line an operator re-reads on the
    second run: the contract's idempotence claim is exactly "this says 0".
    """
    written = (*report.slugs_written, *report.anchors_written, *report.next_actions_seeded)
    lines = [f"migrate-plan-records: {total_writes(report=report)} write(s)"]
    lines.extend(f"wrote: {entry}" for entry in written)
    lines.extend(f"skipped: {entry}" for entry in report.skipped)
    lines.extend(f"refused: {entry}" for entry in report.refused)
    return "".join(f"{line}\n" for line in lines)


def _noted_slug(*, notes: str) -> str | None:
    for line in notes.splitlines():
        stripped = line.strip()
        if not stripped.startswith(_NOTES_SLUG_PREFIX):
            continue
        value = stripped.removeprefix(_NOTES_SLUG_PREFIX).strip()
        if value != "":
            return value
    return None


def _work_item_ref(*, action: str, prefix: str) -> str | None:
    match = re.search(rf"\b{re.escape(prefix)}-[a-z0-9]+(?:\.\d+)*\b", action)
    return None if match is None else match.group(0)
