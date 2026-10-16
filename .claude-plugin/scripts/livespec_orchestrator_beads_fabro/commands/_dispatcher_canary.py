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

WHY EACH CANARY IS A FRESH LEDGER ITEM RATHER THAN A REPLAY OF ONE. A replayed
item carries the history of its earlier dispatches — a journal row, a publish
branch, a recorded factory — so the second canary would differ from the first in
exactly the dimension a canary is taken to hold still. Filing goes through the
ordinary intake door with every Definition-of-Ready gate answered, so the canary
is a real ready item a real dispatch selects, not a special case the dispatch
path has to know about.

This module performs filesystem and ledger IO; it never raises, and every
expected refusal rides back as `CanaryFixtureUnusable`.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from livespec_runtime.work_items.rank import key_between
from returns.pipeline import is_successful

from livespec_orchestrator_beads_fabro._ids import new_work_item_id
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import utc_now_iso
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    file_captured_work_item,
)
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "CANARY_FIXTURE_RELATIVE_PATH",
    "CANARY_MARKER_RELATIVE_PATH",
    "CanaryFixture",
    "CanaryFixtureUnusable",
    "add_file_canary_arguments",
    "file_canary_work_item",
    "parse_canary_fixture",
    "read_canary_fixture",
    "run_file_canary_command",
]

# The committed fixture template, and the dedicated marker file its Definition
# of Done names. Both are repository-relative so the dispatch surface and the
# runbook name the same two paths rather than two spellings of them.
CANARY_FIXTURE_RELATIVE_PATH = "orchestrator-image/canary-fixture.md"
CANARY_MARKER_RELATIVE_PATH = "orchestrator-image/canary-marker.md"

_TITLE_PREFIX = "# "
# The canary is filed with every intake gate answered, because the committed
# fixture is authored to satisfy all six: one coherent done, graded from the
# marker file alone, factory-eligible, dependency-free, repo-targeted and above
# the slice floor. Answering them here rather than asking an operator is what
# makes taking a canary a one-liner instead of a dialogue.
_CHECKLIST = DefinitionOfReadyChecklist(
    single_coherent_done=True,
    autonomously_verifiable=True,
    autonomy_tiered=True,
    dependency_linked=True,
    repo_targeted=True,
    above_floor=True,
)


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


def file_canary_work_item(
    *, repo: Path, config: StoreConfig, now_iso: str
) -> str | CanaryFixtureUnusable:
    """File one fresh canary work-item from the committed fixture; return its id."""
    fixture = read_canary_fixture(repo=repo)
    if isinstance(fixture, CanaryFixtureUnusable):
        return fixture
    return _filed(fixture=fixture, config=config, now_iso=now_iso)


def add_file_canary_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Attach the canary filing surface to its subparser.

    `--repo` is the whole surface. There is deliberately no `--title`, no
    `--description` and no `--fixture` flag: a canary whose brief a caller could
    supply is a canary whose brief can differ between two canaries, which is the
    one property the committed fixture exists to remove.
    """
    _ = parser.add_argument("--repo", dest="repo", required=True)


def run_file_canary_command(*, args: argparse.Namespace) -> int:
    """File one canary and print its id, or name the fixture's fault and refuse.

    The id goes to STDOUT alone, because the recipe captures that stream and
    hands it to `dispatch --item`; every narration goes to stderr for the same
    reason.

    The fixture is read BEFORE the store configuration is resolved, and the order
    is the point: `resolve_store_config` refuses a directory that carries no
    readable `.livespec.jsonc`, so resolving first would answer "your connection
    prefix is missing" to an operator whose actual fault is the fixture — the
    truthful-cause failure that reader's own comment warns about.
    """
    repo = Path(args.repo)
    fixture = read_canary_fixture(repo=repo)
    if isinstance(fixture, CanaryFixtureUnusable):
        return _refused(unusable=fixture)
    filed = _filed(
        fixture=fixture,
        config=resolve_store_config(cwd=repo, work_items_arg=None),
        now_iso=utc_now_iso(),
    )
    if isinstance(filed, CanaryFixtureUnusable):
        return _refused(unusable=filed)
    write_stdout(text=f"{filed}\n")
    return 0


def _refused(*, unusable: CanaryFixtureUnusable) -> int:
    write_stderr(text=f"LIVESPEC_CANARY_FIXTURE_UNUSABLE: {unusable.detail}\n")
    return 1


def _filed(
    *, fixture: CanaryFixture, config: StoreConfig, now_iso: str
) -> str | CanaryFixtureUnusable:
    """File one already-read fixture as a fresh ledger item; return its id.

    An intake route that fails is reported with the minted id in it: the record
    EXISTS in the ledger at that point, and a refusal that hid the id would
    leave an orphan nobody could find to dispose of.
    """
    item = _canary_work_item(fixture=fixture, prefix=config.prefix, now_iso=now_iso)
    routed = file_captured_work_item(path=config, item=item, checklist=_CHECKLIST)
    if not is_successful(routed):
        return CanaryFixtureUnusable(
            detail=(
                f"the canary work-item {item.id} was filed but intake could not route it,"
                " so the ledger holds the record and no dispatch was attempted"
            )
        )
    return item.id


def _canary_work_item(*, fixture: CanaryFixture, prefix: str, now_iso: str) -> WorkItem:
    """The fresh ledger record one canary is filed as.

    `admission_policy="auto"` is what carries it from intake straight to
    `ready`, so the recipe's second command has a dispatchable item without an
    operator driving the approve valve in between. `type="chore"` because the
    canary changes no product behaviour, and the rank is the canonical first key
    rather than the bottom sentinel, which the ledger's own closed-item
    integrity reading treats as an unranked row.
    """
    return WorkItem(
        id=new_work_item_id(prefix=prefix),
        type="chore",
        status="backlog",
        title=fixture.title,
        description=fixture.description,
        origin="freeform",
        gap_id=None,
        rank=key_between(a=None, b=None),
        assignee=None,
        depends_on=(),
        captured_at=now_iso,
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        admission_policy="auto",
    )


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
