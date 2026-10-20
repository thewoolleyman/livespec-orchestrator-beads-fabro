"""The governed spec tree's H2 headings, and the gap-ids they derive.

`SPECIFICATION/contracts.md` and Scenario 205 of
`SPECIFICATION/scenarios.md` make heading coverage the gap signal: a gap
names an H2 heading of the governed spec tree that no test exercises. This
module owns the LEFT side of that join — which headings exist, and what
stable id each one carries — so that the classification against the
coverage map, and the thin CLI above it, each read one population rather
than re-deriving it.

WHY THE POPULATION IS THE NLSPEC FILE SET AND NOT EVERY MARKDOWN FILE.
The signal is a JOIN against `tests/heading-coverage.json`, and that
registry's own population is the template-declared NLSpec files — the
shared `heading_coverage` check walks exactly those and treats any entry
outside them as an orphan. Enumerating a wider set would report every
heading of, say, the skill-owned `SPECIFICATION/README.md` as a permanent
gap that no coverage entry may ever close, because an entry for it would
fail that check from the other direction. Measured over this repository's
live tree: the NLSpec set yields 252 headings against the registry's 252
entries, with zero uncovered and zero orphaned on either side, while
`README.md` alone would add three headings nobody can ever cover.

WHY FENCED CODE BLOCKS ARE NOT SKIPPED, which looks like an omission and
is the opposite. The registry was built by the shared check's own
enumeration, which tracks no fences, so a heading-like line inside a fence
is already AN ENTRY. Skipping it here would make that entry identify no
live heading — a surfaced finding, on a row that is in the registry
precisely because the gate that governs the registry requires it.

WHY THE GAP-ID RIDES THE SHARED CLAUSE PRIMITIVE'S DERIVATION. `derive_gap_id`
is the fleet's single-sourced `gap-<8>` derivation, pinned to livespec core's
copy by a parity test, and a gap-id is a LABEL on a live work-item — so a
second hash recipe in this repository is a second way for two repositories
to disagree about one item's identity. The heading form supplies the heading
as the heading path and NO rule text, which also keeps it disjoint from every
clause-derived id by construction: a clause always carries non-empty text.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_spec_clauses import derive_gap_id
from returns.io import IOFailure, IOResult, IOSuccess
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._heading_coverage_map import (
    CoverageEntry,
    read_coverage_entries,
)
from livespec_orchestrator_beads_fabro.commands._heading_coverage_test_nodes import (
    names_an_existing_test,
)
from livespec_orchestrator_beads_fabro.errors import SpecVersionNotFoundError
from livespec_orchestrator_beads_fabro.spec_reader import (
    read_current_specification,
    read_specification_history,
)

__all__: list[str] = [
    "HeadingGapScan",
    "SpecHeading",
    "derive_heading_gap_id",
    "live_headings",
    "scan_heading_gaps",
]

# The template-declared NLSpec file set the coverage registry covers. A file
# outside it carries no registry entry by the shared check's own rule, so its
# headings are not gap candidates.
_NLSPEC_FILES: frozenset[str] = frozenset(
    {
        "spec.md",
        "contracts.md",
        "constraints.md",
        "non-functional-requirements.md",
        "scenarios.md",
    }
)

_H2_PREFIX = "## "
_SCENARIO_PREFIX = "Scenario:"
_SCENARIOS_FILE = "scenarios.md"

# The heading form of the shared derivation carries no rule text. Named rather
# than written inline because the EMPTY STRING is the load-bearing part: it is
# what makes a heading-derived id disjoint from every clause-derived one.
_HEADING_CARRIES_NO_RULE_TEXT = ""


@dataclass(frozen=True, kw_only=True)
class SpecHeading:
    """One H2 heading of the governed spec tree, with the gap-id it derives.

    `spec_root` and `spec_file` are the coverage registry's own vocabulary for
    this heading, so a caller matches an entry on the triple it already holds
    rather than reconstructing the registry's spelling of a path.
    """

    spec_root: str
    spec_file: str
    heading: str
    gap_id: str


@dataclass(frozen=True, kw_only=True)
class HeadingGapScan:
    """One scan's result: the headings this run reports as gaps."""

    gaps: tuple[SpecHeading, ...]


def derive_heading_gap_id(*, spec_file: str, heading: str) -> str:
    """The stable gap-id of one heading: a pure function of its file and itself.

    For an H2-only enumeration the canonical heading path IS the heading line,
    verbatim as the registry records it — which is also the value the match
    keys on, so the id names the registry entry it asks for.
    """
    return derive_gap_id(
        spec_file=spec_file,
        heading_path=heading,
        rule_text=_HEADING_CARRIES_NO_RULE_TEXT,
    )


def live_headings(*, spec_root: Path, project_root: Path) -> tuple[SpecHeading, ...]:
    """Every H2 heading of the governed NLSpec files, in file-then-document order.

    Deterministic by construction: the files are walked sorted and each file's
    headings keep their document order, so two runs over an unchanged tree
    enumerate the identical sequence.
    """
    snapshot = read_current_specification(spec_root=spec_root)
    spec_root_label = _spec_root_label(spec_root=spec_root, project_root=project_root)
    headings: list[SpecHeading] = []
    for spec_file in sorted(snapshot.files):
        if spec_file not in _NLSPEC_FILES:
            continue
        headings.extend(
            SpecHeading(
                spec_root=spec_root_label,
                spec_file=spec_file,
                heading=heading,
                gap_id=derive_heading_gap_id(spec_file=spec_file, heading=heading),
            )
            for heading in _h2_headings(content=snapshot.files[spec_file], spec_file=spec_file)
        )
    return tuple(headings)


def scan_heading_gaps(
    *,
    spec_root: Path,
    project_root: Path,
    since_version: int | None = None,
) -> IOResult[HeadingGapScan, SpecVersionNotFoundError]:
    """Scan the governed spec tree for headings to report as gaps.

    An absent `since_version` history directory is an EXPECTED failure and
    rides the failure track, because the caller turns it into a distinct exit
    code rather than a crash.
    """
    if since_version is not None:
        history = read_specification_history(spec_root=spec_root, version=since_version)
        if not is_successful(history):
            return IOFailure(unsafe_perform_io(history.failure()))
    entries = read_coverage_entries(project_root=project_root)
    covered = _covered_keys(entries=entries, project_root=project_root)
    gaps = tuple(
        heading
        for heading in live_headings(spec_root=spec_root, project_root=project_root)
        if (heading.spec_root, heading.spec_file, heading.heading) not in covered
    )
    return IOSuccess(HeadingGapScan(gaps=gaps))


def _covered_keys(
    *, entries: tuple[CoverageEntry, ...], project_root: Path
) -> frozenset[tuple[str, str, str]]:
    """Every triple a registry row proves is exercised by an existing test.

    A heading is covered when AT LEAST ONE identifying row names an existing
    test, which is what keeps "exactly one gap per heading" true in the face
    of duplicate rows: a `TODO` row beside a real one must not re-open a
    heading some test does exercise.
    """
    return frozenset(
        entry.key
        for entry in entries
        if entry.identifies_a_heading
        and not entry.names_the_todo_sentinel
        and names_an_existing_test(project_root=project_root, test_node=entry.test)
    )


def _spec_root_label(*, spec_root: Path, project_root: Path) -> str:
    """The registry's spelling of one spec root: its path relative to the project.

    A spec target OUTSIDE the project root cannot be spelled that way, so its
    own directory name stands in — the registry could only ever name it that
    way too.
    """
    if spec_root.is_relative_to(project_root):
        return spec_root.relative_to(project_root).as_posix()
    return spec_root.name


def _h2_headings(*, content: str, spec_file: str) -> list[str]:
    """The verbatim H2 heading lines of one spec file, in document order.

    A `## Scenario:`-prefixed heading is tracked granularly only in
    `scenarios.md`; elsewhere it is out of registry scope, so enumerating it
    would report a gap no entry may cover.
    """
    headings: list[str] = []
    for raw_line in content.splitlines():
        heading = raw_line.rstrip()
        if not heading.startswith(_H2_PREFIX):
            continue
        if spec_file != _SCENARIOS_FILE and heading.removeprefix(_H2_PREFIX).startswith(
            _SCENARIO_PREFIX
        ):
            continue
        headings.append(heading)
    return headings
