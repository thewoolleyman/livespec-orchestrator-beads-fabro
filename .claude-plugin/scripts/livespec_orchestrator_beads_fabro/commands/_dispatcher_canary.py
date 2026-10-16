"""The committed canary fixture — the one work-item every candidate canary runs.

A CANDIDATE CANARY is a dispatch taken to find out whether a candidate engine
runs this repository's factory end to end. It is a measurement of the ENGINE, so
every other variable has to be held still — and the variable that was not held
still is the WORK-ITEM. Canaries 5 and 6 of plan `fabro-currency` (hp-candidate
runs `01M4NWARSD8T` and `01M4PBFW4MP8`, 2026-10-11) were taken against a real
backlog item, `bd-ib-o6aeji`, whose `References:` line named a heading that
governs something else; both reached `dod_gate` and were REFUSED there. That is
an item-quality failure wearing an engine failure's clothes, and canary 6
repeated it, because nothing about taking a canary said which item to take it
with.

So the item is COMMITTED. `orchestrator-image/canary-fixture.md` is the fixture
template: its first `# ` line is the canary's title and everything below it is
the canary's description, whose first heading is its Definition of Done and
whose reference line names a heading of the governed spec tree.

WHY THE FIXTURE IS VALIDATED HERE RATHER THAN TRUSTED. The file is committed, so
a malformed one is a repository defect rather than an operational fault — which
is precisely why it must be caught where the canary is assembled rather than at
`dod_gate` on a factory host, half an hour and one sandbox later. Validation goes
through `definition_of_done`, the ONE ratified parse the gate's host-side wall
also reads, so "the fixture is fileable" and "the wall admits it" cannot come
apart.

It deliberately does NOT re-check whether the reference RESOLVES against the
spec tree. That is the wall's own measurement, and a second resolution here would
be a second implementation of the very rule this module exists to stay on the
right side of — the shape that produced the refused canaries in the first place.

This module performs filesystem IO; it never raises, and every expected refusal
rides back as `CanaryFixtureUnusable`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "CANARY_FIXTURE_RELATIVE_PATH",
    "CANARY_MARKER_RELATIVE_PATH",
    "CanaryFixture",
    "CanaryFixtureUnusable",
    "parse_canary_fixture",
    "read_canary_fixture",
]

# The committed fixture template, and the dedicated marker file its Definition
# of Done names. Both are repository-relative so the dispatch surface and the
# runbook name the same two paths rather than two spellings of them.
CANARY_FIXTURE_RELATIVE_PATH = "orchestrator-image/canary-fixture.md"
CANARY_MARKER_RELATIVE_PATH = "orchestrator-image/canary-marker.md"

_TITLE_PREFIX = "# "


@dataclass(frozen=True, kw_only=True)
class CanaryFixture:
    """The canary work-item's title and description, as the fixture defines them."""

    title: str
    description: str


@dataclass(frozen=True, kw_only=True)
class CanaryFixtureUnusable:
    """Why no canary could be assembled, in one line naming the fixture's fault."""

    detail: str


def parse_canary_fixture(*, text: str) -> CanaryFixture | CanaryFixtureUnusable:
    """Read one fixture template's text into the work-item it defines.

    The FIRST `# ` line is the title and everything after it is the description,
    so the title cannot be mistaken for the description's own first heading —
    which is exactly what the ratified Definition-of-Done parse keys on.
    """
    lines = text.splitlines()
    for index, raw in enumerate(lines):
        if raw.startswith(_TITLE_PREFIX):
            return _validated(
                title=raw[len(_TITLE_PREFIX) :].strip(),
                description="\n".join(lines[index + 1 :]).strip(),
            )
    return CanaryFixtureUnusable(
        detail=(
            f"the canary fixture {CANARY_FIXTURE_RELATIVE_PATH} carries no `# ` title line,"
            " so it defines no canary work-item title"
        )
    )


def read_canary_fixture(*, repo: Path) -> CanaryFixture | CanaryFixtureUnusable:
    """Read and parse the committed fixture template out of one repository."""
    path = repo / CANARY_FIXTURE_RELATIVE_PATH
    read = attempt(action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(read, AttemptFailure):
        return CanaryFixtureUnusable(
            detail=(
                f"the canary fixture {CANARY_FIXTURE_RELATIVE_PATH} could not be read"
                f" from {repo}: {read.error}"
            )
        )
    return parse_canary_fixture(text=read)


def _validated(*, title: str, description: str) -> CanaryFixture | CanaryFixtureUnusable:
    """Refuse a fixture the Definition-of-Done wall could not admit.

    The four refusals are the four things the wall grades that a committed file
    can get wrong on its own: an untitled canary, a description whose first
    heading is something else, a section with nothing gradeable in it, and a
    section naming no governing heading.
    """
    if not title:
        return CanaryFixtureUnusable(
            detail=f"the canary fixture {CANARY_FIXTURE_RELATIVE_PATH} title line carries no text"
        )
    section = definition_of_done(description=description)
    if not section.present:
        return CanaryFixtureUnusable(
            detail=(
                f"the canary fixture {CANARY_FIXTURE_RELATIVE_PATH} description carries no"
                " Definition of Done section as its first heading"
            )
        )
    if not section.assertions:
        return CanaryFixtureUnusable(
            detail=(
                f"the canary fixture {CANARY_FIXTURE_RELATIVE_PATH} Definition of Done section"
                " carries no gradeable assertion"
            )
        )
    if not section.references:
        return CanaryFixtureUnusable(
            detail=(
                f"the canary fixture {CANARY_FIXTURE_RELATIVE_PATH} Definition of Done section"
                " carries no `References:` line"
            )
        )
    return CanaryFixture(title=title, description=description)
