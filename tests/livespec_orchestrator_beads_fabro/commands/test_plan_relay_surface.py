"""The relay vocabulary a plan session reaches through the `plan` facade.

`plan.py` is the surface the plan operation's own prose instructs a session to
call, and that prose names every type a caller has to construct: the request,
the two legs it may supply, and the supersession a conflicting target takes. A
name the prose tells a reader to use and the facade does not export is a
documented call that raises — and it raises at the moment a plan is trying to
displace an obligation, which is the one moment the guidance exists for.

WHY THE CASE READS THE PROSE RATHER THAN LISTING NAMES. A hand-written list
agrees with the facade on the day it is written and drifts the moment either
side moves, in the direction that looks fine: the list keeps passing while the
prose names something new. Taking the names OUT of the shipped prose makes the
two unable to disagree without failing here.

WHY THE SCAN READS THE WHOLE SPAN AND NOT ITS OPENING. This module's first draft
anchored on the backtick — `` `(Relay[A-Za-z]*) `` — and passed against a facade
that was genuinely missing a name, because the one missing name is spelled
`supersedes=RelaySupersession(...)` and a span-opening anchor can never match
inside it. An instrument that cannot return a hit reporting no hits is the
expensive kind of green, so the span is extracted first and the identifiers are
found anywhere within it.
"""

from __future__ import annotations

import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import plan

_PROSE = Path(".claude-plugin/prose/plan.md")

# A code span, then every `Relay…` identifier ANYWHERE inside one. The span is
# what distinguishes a name from prose that happens to capitalise a word; the
# prefix is what selects the relay types a caller constructs.
_CODE_SPAN = re.compile(r"`([^`\n]+)`")
_RELAY_NAME = re.compile(r"\b(Relay[A-Za-z]*)")


def _named_in_prose() -> list[str]:
    """Every relay type the shipped plan prose tells a caller to construct."""
    spans = _CODE_SPAN.findall(_PROSE.read_text(encoding="utf-8"))
    return sorted({name for span in spans for name in _RELAY_NAME.findall(span)})


def test_the_facade_exports_every_relay_name_its_own_prose_tells_a_caller_to_use() -> None:
    """The prose and the facade are two halves of one surface."""
    named = _named_in_prose()

    assert named, "the plan prose names no relay type, so this case measures nothing"
    missing = [name for name in named if name not in plan.__all__ or not hasattr(plan, name)]
    assert missing == [], f"the plan facade exports no {missing}"


def test_the_scan_finds_a_name_spelled_inside_a_span_rather_than_opening_one() -> None:
    """The positive control for the scan's aim, not for the facade's contents.

    `RelaySupersession` is spelled `supersedes=RelaySupersession(...)` in the
    prose, which is the shape the first draft of this module could not see. A
    scan that silently stopped finding mid-span names would keep reporting an
    empty `missing` list for a facade that had lost one.
    """
    assert "RelaySupersession" in _named_in_prose()


def test_the_recording_primitive_itself_is_on_that_facade() -> None:
    """The control: every type above is only reachable work if the verb is too."""
    assert "record_relay" in plan.__all__
    assert callable(plan.record_relay)
