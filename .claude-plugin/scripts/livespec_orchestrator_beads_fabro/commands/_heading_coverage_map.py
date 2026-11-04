"""The repository's heading-coverage registry, as read.

`tests/heading-coverage.json` is the RIGHT side of the heading-coverage
join: a list of rows, each claiming that one `(spec_root, spec_file,
heading)` triple is exercised by one test. This module owns reading those
rows and saying what each one claims; whether a claim HOLDS against the
live spec tree is the join's business, not this one's.

WHY A ROW'S THREE IDENTIFYING FIELDS ARE READ AS A TRIPLE AND NEVER
SEPARATELY. `SPECIFICATION/contracts.md` requires the match on spec root,
spec file and heading TOGETHER. Two spec files legitimately carry the
same H2 heading text — `contracts.md` and `scenarios.md` both do here —
so a match on anything less lets one file's entry report the other
file's heading as covered, which is the one wrong answer that is
invisible: the heading simply stops appearing.

WHY A MALFORMED ROW IS KEPT RATHER THAN DROPPED. A row whose identifying
fields are not all present and non-empty identifies no heading, and the
contract requires it SURFACED as a finding rather than silently ignored.
Dropping it at the parse boundary is the one thing that would make it
indistinguishable from a registry that never carried it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

__all__: list[str] = [
    "COVERAGE_RELATIVE_PATH",
    "TODO_SENTINEL",
    "CoverageEntry",
    "read_coverage_entries",
]

# The registry's committed location, relative to the project root.
COVERAGE_RELATIVE_PATH = Path("tests") / "heading-coverage.json"

# The sanctioned debt sentinel: a row that owes a test and says so in its
# `reason`. It leaves its heading uncovered, and it is NOT a defect — the
# shared heading-coverage gate and the debt register already govern it.
TODO_SENTINEL = "TODO"


@dataclass(frozen=True, kw_only=True)
class CoverageEntry:
    """One registry row, as read.

    `position` is the row's index in the file, which is how a finding names a
    row that identifies nothing: such a row has no heading to name it by.
    """

    position: int
    spec_root: str
    spec_file: str
    heading: str
    test: str

    @property
    def identifies_a_heading(self) -> bool:
        """Whether the row names a triple at all — the precondition for a match."""
        return bool(self.spec_root and self.spec_file and self.heading)

    @property
    def key(self) -> tuple[str, str, str]:
        """The fully qualified triple this row claims to cover."""
        return (self.spec_root, self.spec_file, self.heading)

    @property
    def names_the_todo_sentinel(self) -> bool:
        return self.test == TODO_SENTINEL

    def describe(self) -> str:
        """How a surfaced finding names this row to an operator.

        A row that identifies a heading is named by it; one that identifies
        none has no heading to be named by, so its stated fields are shown
        verbatim — which is the only way an operator can tell WHICH of them
        the row failed to state.
        """
        if self.identifies_a_heading:
            return f"entry {self.position} ({self.spec_root}/{self.spec_file} {self.heading!r})"
        return (
            f"entry {self.position} (spec_root={self.spec_root!r} "
            f"spec_file={self.spec_file!r} heading={self.heading!r})"
        )


def read_coverage_entries(*, project_root: Path) -> tuple[CoverageEntry, ...]:
    """Every row of the project's coverage registry, in file order.

    An absent or non-list registry yields NO rows, which reads downstream as
    "every heading is uncovered" — the correct answer for a repository that
    carries no registry, and the same one the shared heading-coverage gate
    gives.
    """
    path = project_root / COVERAGE_RELATIVE_PATH
    if not path.is_file():
        return ()
    parsed: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, list):
        return ()
    rows = cast("list[object]", parsed)
    return tuple(
        _entry(row=cast("dict[str, object]", row), position=position)
        for position, row in enumerate(rows)
        if isinstance(row, dict)
    )


def _entry(*, row: dict[str, object], position: int) -> CoverageEntry:
    return CoverageEntry(
        position=position,
        spec_root=_text(value=row.get("spec_root")),
        spec_file=_text(value=row.get("spec_file")),
        heading=_text(value=row.get("heading")),
        test=_text(value=row.get("test")),
    )


def _text(*, value: object) -> str:
    """One field as text, with every absent or non-string shape reading empty.

    `omitempty` serializers omit a field rather than retyping it, so an
    absent field and one holding the wrong type both mean the row does not
    state that value — and the empty string is how every reader downstream
    spells that.
    """
    return value.strip() if isinstance(value, str) else ""
