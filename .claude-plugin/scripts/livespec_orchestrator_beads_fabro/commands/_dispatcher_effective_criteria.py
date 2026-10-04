"""The one public primitive resolving a work-item's effective acceptance criteria.

The effective-acceptance-criteria clause of `SPECIFICATION/contracts.md`
requires exactly ONE public primitive here, used by every producer and consumer
gate: the capture and groom front-ends' parse display, the entry-to-`ready` wall
(the human `approve` transition), the pre-dispatch wall, and the post-merge
acceptance pass. No surface may re-derive criteria by another path. Before this
module the acceptance pass owned a PRIVATE resolution and no other gate had one
at all, so "the criteria" meant a different thing at each wall — and the two
walls the spec ratifies had nothing to be implemented against.

The resolution order, which is the spec's:

1. The item description's Definition of Done section (parsed by
   `_dispatcher_definition_of_done`, the ONE path the clause permits) when it
   yields gradeable content.
2. Otherwise the item's MATERIALIZED criteria value — the merged store read in
   which the native `acceptance_criteria` field wins over a metadata-held one,
   so a criteria field written into metadata by an older writer is NOT read as
   absent — when it yields gradeable content. That materialization IS the
   merged read; nothing here re-reads raw metadata separately.
3. Otherwise the item description's "Exit criteria" section (a heading whose
   title case-insensitively equals "Exit criteria"; the section body is the
   criteria text).

The resolved source is reported as exactly one of the three ratified values,
`description-definition-of-done`, `criteria-field` or
`description-exit-criteria`. Steps 2 and 3 are LEGACY: an item that resolves
from either carries no Definition of Done section that yields assertions, and
the parse display says so, so the gap is repaired when the item is next touched.
Gradeability is defined at the ASSERTION level, so an effective-criteria set is
empty when the shipped parser (`criteria_lines`) yields no assertion — never
when a physical-line count happens to reach zero.

The two walls share `ungradeable_criteria_refusal` deliberately. An item that
the approve valve refuses and an item the pre-dispatch gate refuses are the
same item failing the same test, and a second copy of that test is how the two
gates drift into disagreeing about what "ungradeable" means. Both reach it
through `_dispatcher_acceptance_eligibility`, which is the ONE decision that
combines this resolution with the workflow variant and the Definition-of-Done
findings; the variant-aware wall lives there rather than here because resolving
a variant needs the repository and three of this module's consumers hold only
the item.

`change_classification` lives here for the same reason. The spec's
change-implying/change-optional split is a property OF the resolved criteria —
a gradeable criteria set is presumed to require file changes — so it belongs
beside the resolution rather than inside the one consumer that reads it today.
It is deliberately a two-value classification with the DEFAULT on the refusing
side: an item is change-implying unless it explicitly DECLARES otherwise, and
a marker nobody can read is not a declaration.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_criteria import (
    criteria_lines,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_HOST_CAPTURED,
    PROOF_MODE_HUMAN_ATTESTED,
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_overrides import (
    effective_acceptance_policy,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_ACCEPTANCE_POLICY,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "AI_ONLY_POLICY",
    "CHANGE_IMPLYING_CLASSIFICATION",
    "CHANGE_OPTIONAL_CLASSIFICATION",
    "CHANGE_OPTIONAL_LABEL",
    "CRITERIA_FIELD_SOURCE",
    "DEFINITION_OF_DONE_MISSING_MARKER",
    "DESCRIPTION_DEFINITION_OF_DONE_SOURCE",
    "DESCRIPTION_EXIT_CRITERIA_SOURCE",
    "ChangeClassification",
    "EffectiveCriteria",
    "change_classification",
    "effective_criteria",
    "effective_policy",
    "ungradeable_criteria_refusal",
]

CRITERIA_FIELD_SOURCE = "criteria-field"
# The marker the capture, groom and approve displays render for an item that
# resolved from a legacy source. The wording is the clause's own, so a grep
# for it finds the spec text and every surface that honours it.
DEFINITION_OF_DONE_MISSING_MARKER = "definition-of-done: missing"
DESCRIPTION_DEFINITION_OF_DONE_SOURCE = "description-definition-of-done"
DESCRIPTION_EXIT_CRITERIA_SOURCE = "description-exit-criteria"
CHANGE_IMPLYING_CLASSIFICATION = "change-implying"
CHANGE_OPTIONAL_CLASSIFICATION = "change-optional"
# The declared marker is a raw ledger label, deliberately DISTINCT from the
# item's `acceptance_policy`: `human-only` says who judges the item, not
# whether the item is expected to change any files.
CHANGE_OPTIONAL_LABEL = "change-optional:"

# The one policy under which a machine may close the item WITHOUT a human, and
# therefore the one the derived proof routing has to refuse for an item carrying
# a human-attested assertion.
AI_ONLY_POLICY = "ai-only"
# The two effective `acceptance_policy` values under which a machine grades the
# item. `human-only` is deliberately outside the walls: a human judgement call
# is exactly the case where machine-gradeable criteria are inapplicable.
_AI_DISPOSITIVE_POLICIES = frozenset({AI_ONLY_POLICY, "ai-then-human"})
_EXIT_CRITERIA_TITLE = "exit criteria"
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
# The ONE marker value that DECLARES the exemption. Anything else — a typo, an
# empty value, `yes`, `1` — is a marker value the classification cannot honour.
_DECLARED_CHANGE_OPTIONAL_VALUE = "true"


@dataclass(frozen=True, kw_only=True)
class EffectiveCriteria:
    """One work-item's resolved criteria text, its source, and its assertions.

    `proof_modes` is EITHER empty or parallel to `assertions`. Empty means the
    item resolved from a legacy source and therefore declared no mode at all,
    which is deliberately distinguishable from declaring every assertion
    `factory_captured`: the acceptance pass keeps grading a legacy item by
    merged-diff vocabulary, and applying that matching to an assertion that
    DOES carry a mode is exactly what the proof evidence leg forbids.
    """

    text: str | None
    source: str
    assertions: tuple[str, ...]
    proof_modes: tuple[str, ...] = ()

    @property
    def gradeable(self) -> bool:
        """Whether the set carries at least one gradeable assertion."""
        return bool(self.assertions)

    @property
    def host_captured_assertions(self) -> tuple[str, ...]:
        """The assertions an agent session must capture on a host, in section order.

        Empty for a legacy source, exactly as the human-attested projection is and
        for the same reason.
        """
        return self._with_mode(mode=PROOF_MODE_HOST_CAPTURED)

    @property
    def human_attested_assertions(self) -> tuple[str, ...]:
        """The assertions a human must attest, in the section's own order.

        Empty for a legacy source, which declares no mode at all: the item-level
        routing derived from this is therefore the factory-captured one, matching
        the pre-v114 behaviour for work already in flight.
        """
        return self._with_mode(mode=PROOF_MODE_HUMAN_ATTESTED)

    @property
    def pending_leg_assertions(self) -> tuple[str, ...]:
        """Every assertion whose proof leg the AI acceptance pass does not grade.

        The v115 evidence rule draws ONE line here: "a PASS with any pending leg
        (host or human) MUST NOT accept the item to `done` under any policy,
        `ai-only` included". The two legs are otherwise unrelated — one is
        performed by an agent session on an operator host and the other by a
        human — so a disposition that tested them separately would be two tests
        of one rule, and the way that fails is that a mode added later is wired
        into one of them. Host assertions lead because the host leg is the
        earlier one in the order the deliverable policy ranks the modes.
        """
        return self.host_captured_assertions + self.human_attested_assertions

    def _with_mode(self, *, mode: str) -> tuple[str, ...]:
        """The assertions declaring one mode, in the section's own order.

        `strict=False` is load-bearing rather than lax: `proof_modes` is EMPTY for
        a legacy source while `assertions` is not, and the zip has to yield
        nothing for that item rather than raise.
        """
        return tuple(
            assertion
            for assertion, declared in zip(self.assertions, self.proof_modes, strict=False)
            if declared == mode
        )

    def parse_display(self) -> str:
        """The one-line parse result the capture, groom and approve displays render.

        A LEGACY source carries the `definition-of-done: missing` marker the
        clause requires, so the gap is visible on the surface an operator is
        already looking at when they touch the item. Without it the line reads as
        a clean parse — a positive assertion count from a source the walls will
        refuse — and the display that exists to prompt the repair instead
        reassures.

        The marker is APPENDED rather than substituted: the count and the resolved
        source are what tell an operator WHICH repair applies (author a section,
        or move criteria that already exist), so dropping them to make room for
        the marker would remove the information the marker is pointing at.
        """
        line = (
            f"effective acceptance criteria: {len(self.assertions)} gradeable"
            f" assertion(s) resolved from {self.source}"
        )
        if self.source == DESCRIPTION_DEFINITION_OF_DONE_SOURCE:
            return line
        return f"{line}; {DEFINITION_OF_DONE_MISSING_MARKER}"

    def as_record(self) -> dict[str, object]:
        """The leak-free projection of the parse for a journal or JSON envelope."""
        return {
            "source": self.source,
            "gradeable_assertions": len(self.assertions),
            "gradeable": self.gradeable,
        }


@dataclass(frozen=True, kw_only=True)
class ChangeClassification:
    """Whether an item's gradeable criteria are presumed to require file changes.

    Exactly two values, because the empty-diff refusal the spec builds on this
    is a two-way branch: `change-implying` (the default AND the fail-closed
    answer) or `change-optional` (the one declared exemption).

    `declared_marker` carries the raw marker value that was READ, which is the
    only thing that separates "no marker was present" from "a marker was
    present and could not be honoured". Both classify identically — that is the
    fail-closed rule — so without the recorded value an operator who mistypes
    the marker sees an item behaving exactly as if they had never declared it,
    with nothing anywhere saying why.
    """

    classification: str
    declared_marker: str | None

    @property
    def change_implying(self) -> bool:
        """Whether an empty merged diff is ungradeable for this item."""
        return self.classification == CHANGE_IMPLYING_CLASSIFICATION

    def as_record(self) -> dict[str, object]:
        """The projection the acceptance pass journals as the classification used."""
        return {
            "classification": self.classification,
            "declared_marker": self.declared_marker,
        }


def change_classification(*, raw_labels: Sequence[str] = ()) -> ChangeClassification:
    """Classify change-implying by default; change-optional only when declared.

    An item with a non-empty gradeable effective-criteria set is presumed to
    require file changes, so it classifies as change-implying and the empty-diff
    refusal applies to it. The ONLY exemption is an item explicitly declared
    change-optional through the `change-optional:true` ledger marker.

    Everything else fails CLOSED, toward refusing an empty diff rather than
    accepting one: an absent marker classifies change-implying, and so does a
    malformed or unknown marker value. Fail-open here would be the expensive
    direction — a mistyped marker would silently exempt an item from the very
    refusal that catches a merge which delivered nothing, and the exemption
    would look identical to a deliberate one.
    """
    marker = _change_optional_marker(raw_labels=raw_labels)
    if marker == _DECLARED_CHANGE_OPTIONAL_VALUE:
        return ChangeClassification(
            classification=CHANGE_OPTIONAL_CLASSIFICATION, declared_marker=marker
        )
    return ChangeClassification(
        classification=CHANGE_IMPLYING_CLASSIFICATION, declared_marker=marker
    )


def effective_criteria(*, item: WorkItem) -> EffectiveCriteria:
    """Resolve one item's effective acceptance criteria and report the source.

    The Definition of Done section wins whenever it yields gradeable content,
    then the merged criteria value; otherwise the description's "Exit criteria"
    section is the fallback, and it is reported as the source even when that
    section is absent — the fallback is the step that was resolved, and an absent
    section is an ungradeable result rather than a fourth source value.
    """
    section = definition_of_done(description=item.description)
    if section.assertions:
        return EffectiveCriteria(
            text=section.criteria_text,
            source=DESCRIPTION_DEFINITION_OF_DONE_SOURCE,
            assertions=tuple(one.text for one in section.assertions),
            proof_modes=tuple(one.proof_mode for one in section.assertions),
        )
    field_assertions = criteria_lines(criteria_text=item.acceptance_criteria)
    if field_assertions:
        return EffectiveCriteria(
            text=item.acceptance_criteria,
            source=CRITERIA_FIELD_SOURCE,
            assertions=field_assertions,
        )
    text = _description_exit_criteria(description=item.description)
    return EffectiveCriteria(
        text=text,
        source=DESCRIPTION_EXIT_CRITERIA_SOURCE,
        assertions=criteria_lines(criteria_text=text),
    )


def ungradeable_criteria_refusal(*, item: WorkItem, cwd: Path) -> str | None:
    """The refusal detail for an AI-dispositive item with no gradeable assertions.

    `None` means the item clears the wall — either it has gradeable criteria, or
    its effective `acceptance_policy` is `human-only` and no machine grades it.
    The detail names the item, states that the effective criteria are empty or
    ungradeable, carries the parse, and gives the remedy, exactly as the two
    ratified walls require.
    """
    resolved = effective_criteria(item=item)
    if resolved.gradeable or not _is_ai_dispositive(item=item, cwd=cwd):
        return None
    return (
        f"work-item {item.id}: effective acceptance criteria are empty or"
        f" ungradeable ({resolved.parse_display()}); author criteria via groom"
        " or edit, or set the item's acceptance_policy to human-only where"
        " machine grading is genuinely inapplicable"
    )


def effective_policy(*, item: WorkItem, cwd: Path) -> str:
    """The item's effective `acceptance_policy`, resolved ONCE for every reader.

    ⚠️ `unsafe_perform_io` is not ceremony. `IOResult.value_or` returns
    `IO[value]`, not the value — without it a membership test is against an
    `IO` wrapper and is False for EVERY item, which silently disarms both walls.
    An unreadable config falls back to the `ai-then-human` default, so the walls
    stay armed rather than opening on a config the operator got wrong.

    It is PUBLIC because the shared eligibility decision needs the same answer to
    derive the item's proof routing. Resolving the policy a second time there is
    how the gradeability wall and the routing wall would come to disagree about
    which policy an item is actually under.
    """
    return unsafe_perform_io(
        effective_acceptance_policy(item=item, cwd=cwd).value_or(DEFAULT_ACCEPTANCE_POLICY)
    )


def _is_ai_dispositive(*, item: WorkItem, cwd: Path) -> bool:
    """Whether a machine grades this item's acceptance."""
    return effective_policy(item=item, cwd=cwd) in _AI_DISPOSITIVE_POLICIES


def _change_optional_marker(*, raw_labels: Sequence[str]) -> str | None:
    """The raw value of the declared change-optional marker, or `None` if absent."""
    for label in raw_labels:
        if label.startswith(CHANGE_OPTIONAL_LABEL):
            return label[len(CHANGE_OPTIONAL_LABEL) :]
    return None


def _description_exit_criteria(*, description: str) -> str | None:
    lines = description.splitlines()
    section_lines: list[str] = []
    in_section = False
    section_level = 0
    for raw in lines:
        heading = _HEADING.match(raw)
        if heading is not None:
            level = len(heading.group(1))
            title = heading.group(2).strip().casefold()
            if in_section and level <= section_level:
                break
            if title == _EXIT_CRITERIA_TITLE:
                in_section = True
                section_level = level
                continue
        if in_section:
            section_lines.append(raw)
    text = "\n".join(section_lines).strip()
    if not text:
        return None
    return text
