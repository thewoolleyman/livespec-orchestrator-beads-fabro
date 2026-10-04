"""The carrier map: which child, or which plan-level proof, carries each assertion.

Per the plan Definition-of-Done clause of `SPECIFICATION/contracts.md` (v115): a
scope event is a CARRIER-MAP event when its body carries a `carriers:` block —
the line `carriers:` followed by one line per plan assertion, in Definition of
Done order, of the form `- <ordinal>: <work-item-id>[, <work-item-id>...]` or
`- <ordinal>: plan-level proof`. The scoping event, and every later scope event
that adds, removes or re-words a plan assertion or changes a carrier, MUST be a
carrier-map event, and the carrier relation is recorded ONLY here.

WHY THE `carriers:` BLOCK — NOT THE SECTION — DECIDES WHETHER THE GATE FIRES.
The clause says a ruling or deferral with no `carriers:` block "is unaffected:
it is recorded as before and does not restate the map". So the discriminator is
the BLOCK's presence in the event being recorded, never the epic's state. Keying
the refusal on "the epic has unmapped assertions" instead would refuse every
maintainer ruling on every plan whose map is not yet complete — which is every
plan at the moment a ruling is most likely to be recorded, and which would break
the `discuss-work-item` ruling path that shares this primitive.

⚠ `carriers:` IS A SUBSTRING OF THE HEADER EVERY SCOPE EVENT ALREADY CARRIES.
Every scope-event body opens with `Requirement carriers:` — which ENDS in
`carriers:` — so `"carriers:" in body` is True for an ordinary maintainer ruling
that carries no map at all. The clause defines the block as "the line
`carriers:`", and the LINE is the discriminator. Any future reader separating
carrier-map events from rulings on the ledger must match by line
(`CARRIERS_BLOCK_PREFIX in body.splitlines()`), never by substring. Nothing here
depends on it today, because `guard_carrier_map` keys on the `carriers` ARGUMENT
rather than on rendered text; it is recorded because the first consumer to read
these events back off the ledger will reach for the substring.

WHY A CLOSED CARRIER CHILD IS NOT A DISCHARGE. The map records WHO CARRIES an
assertion, not that the assertion is met. The clause is explicit that a closed
carrier child does not by itself discharge the plan assertion it carries; the
plan-level proof is what discharges one. Nothing here reads child status, and
nothing here should start to.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    plan_definition_of_done,
)

__all__: list[str] = [
    "CARRIERS_BLOCK_PREFIX",
    "PLAN_LEVEL_PROOF",
    "PlanCarrierMapRefusedError",
    "carrier_map_block",
    "guard_carrier_map",
]

CARRIERS_BLOCK_PREFIX = "carriers:"
# The literal a carrier line names when no child carries the assertion and the
# plan's own Proof of Done record is what will discharge it.
PLAN_LEVEL_PROOF = "plan-level proof"

_ORDINAL_SEPARATOR = ":"
_LIST_MARKER = "- "


class PlanCarrierMapRefusedError(Exception):
    """Expected refusal raised when a carrier-map event cannot be recorded."""

    @classmethod
    def unmapped_assertions(
        cls, *, unmapped: tuple[tuple[int, str], ...]
    ) -> PlanCarrierMapRefusedError:
        """Name every assertion the map left out, by ordinal AND by text.

        The ordinal alone would be a refusal that sends its reader back to count
        bullets in the epic description to learn which assertion it meant.
        """
        named = "; ".join(f"{ordinal}: {text}" for ordinal, text in unmapped)
        return cls(f"carrier-map event leaves plan assertions unmapped — {named}")

    @classmethod
    def missing_definition_of_done(cls, *, epic_id: str) -> PlanCarrierMapRefusedError:
        """Name the missing section.

        The wording covers all three shapes the guard refuses — no heading, a
        different first heading, and the heading with no bullet under it —
        because the remedy is identical for each: author the section with its
        gradeable assertions.
        """
        section = "no gradeable Definition of Done section as its first heading"
        consequence = "a carrier-map event has no plan assertions to map"
        remedy = "author the section and its assertions first"
        return cls(f"epic {epic_id} carries {section}, so {consequence}; {remedy}")


def guard_carrier_map(*, epic_id: str, description: str, carriers: tuple[str, ...]) -> None:
    """Refuse a carrier-map event that does not map every plan assertion.

    A no-op when `carriers` is empty: that event is a ruling or a deferral, which
    does not restate the map and is recorded as before.
    """
    if not carriers:
        return
    section = plan_definition_of_done(description=description)
    # `criteria_text`, NOT `present`. The parse sets it to None both for an
    # absent section and for a present one carrying no bullet, deliberately, so
    # that "a caller cannot accidentally read an empty section as gradeable" —
    # and a `present`-only guard is exactly that accident: the bare heading
    # `## Definition of Done` is present, yields zero assertions, so zero are
    # unmapped, and the map records clean having mapped nothing to nothing.
    if section.criteria_text is None:
        raise PlanCarrierMapRefusedError.missing_definition_of_done(epic_id=epic_id)
    mapped = _mapped_ordinals(carriers=carriers)
    unmapped = tuple(
        (ordinal, one.text)
        for ordinal, one in enumerate(section.assertions, start=1)
        if ordinal not in mapped
    )
    if unmapped:
        raise PlanCarrierMapRefusedError.unmapped_assertions(unmapped=unmapped)


def carrier_map_block(*, carriers: tuple[str, ...]) -> str:
    """Render the `carriers:` block, or the empty string for a non-map event.

    The empty string is what keeps a ruling's body byte-identical to what it was
    before this clause existed — a block header with nothing under it would make
    every ruling look like a carrier-map event to any later reader.
    """
    if not carriers:
        return ""
    lines = (CARRIERS_BLOCK_PREFIX, *(f"{_LIST_MARKER}{one}" for one in carriers))
    return "\n".join(lines)


def _mapped_ordinals(*, carriers: tuple[str, ...]) -> frozenset[int]:
    """The assertion ordinals the carrier lines name, ignoring the ones that are not.

    A line whose ordinal does not parse as an integer contributes NOTHING rather
    than raising. The assertion it was meant to map then reports as unmapped,
    which names the real problem — this line does not map assertion N — where a
    parse error would name the syntax and leave the author to work out which
    assertion went missing.
    """
    ordinals: set[int] = set()
    for raw in carriers:
        head, separator, _ = raw.strip().removeprefix(_LIST_MARKER).partition(_ORDINAL_SEPARATOR)
        if not separator:
            continue
        candidate = head.strip()
        if candidate.isdigit():
            ordinals.add(int(candidate))
    return frozenset(ordinals)
