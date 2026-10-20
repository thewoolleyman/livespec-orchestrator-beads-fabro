"""Grading the coverage registry's rows: what each one covers, and what it owes.

This is the JOIN's right-hand pass. One walk over the registry answers both
questions a scan needs — which triples a test genuinely exercises, and which
rows are DEFECTIVE — because both answers come from the same row and the same
test-node resolution. Splitting them would resolve every node id twice and let
the two halves disagree about one row.

WHY A DEFECTIVE ROW IS A FINDING AND NOT ONLY A GAP. Per
`SPECIFICATION/contracts.md`, a dangling row (its test names no existing
test) and an incomplete one (it identifies a live heading and states no test
value) are each an uncovered heading AND a surfaced finding, "never as a
clean absence". Reported as a gap alone they are indistinguishable from a
heading nobody has entered yet — so the row an operator must repair is never
named, and a renamed test silently converts proven coverage into ordinary
debt.

WHY THE `TODO` SENTINEL IS NOT A DEFECT, which is the distinction that keeps
the findings readable. `TODO` is the sanctioned debt row: it states the
coverage it owes and carries a `reason` saying so, and the shared
`heading_coverage` gate plus the debt register already govern it. This
repository carries 128 of them against 6 genuinely dangling rows, so grading
the sentinel as a defect would bury every real finding twenty deep.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from livespec_orchestrator_beads_fabro.commands._heading_coverage_map import CoverageEntry
from livespec_orchestrator_beads_fabro.commands._heading_coverage_test_nodes import (
    names_an_existing_test,
)

__all__: list[str] = [
    "CoverageFinding",
    "CoverageGrading",
    "Defect",
    "grade_coverage_entries",
]

Defect = Literal["dangling-test", "incomplete-entry"]

_FINDING_PREFIX = "FINDING"


@dataclass(frozen=True, kw_only=True)
class CoverageFinding:
    """One registry row a run reports as defective, with the defect named.

    `detail` names the ROW — its position and the triple it identifies — so an
    operator can reach the line to repair without re-deriving which row the
    run meant.
    """

    defect: Defect
    detail: str

    def render(self) -> str:
        return f"{_FINDING_PREFIX}: {self.defect} — {self.detail}"


@dataclass(frozen=True, kw_only=True)
class CoverageGrading:
    """One grading pass: the triples genuinely covered, and the rows that owe."""

    covered: frozenset[tuple[str, str, str]]
    findings: tuple[CoverageFinding, ...]


def grade_coverage_entries(
    *, entries: tuple[CoverageEntry, ...], project_root: Path
) -> CoverageGrading:
    """Grade every registry row against the tree, in file order.

    A triple is covered when AT LEAST ONE identifying row names an existing
    test. That is what keeps "exactly one gap per heading" true in the face of
    duplicate rows: a `TODO` row beside a real one must not re-open a heading
    some test does exercise.
    """
    covered: set[tuple[str, str, str]] = set()
    findings: list[CoverageFinding] = []
    for entry in entries:
        if not entry.identifies_a_heading:
            continue
        if entry.names_the_todo_sentinel:
            continue
        if not entry.test:
            findings.append(
                CoverageFinding(
                    defect="incomplete-entry",
                    detail=f"{entry.describe()} states no test value",
                )
            )
            continue
        if names_an_existing_test(project_root=project_root, test_node=entry.test):
            covered.add(entry.key)
            continue
        findings.append(
            CoverageFinding(
                defect="dangling-test",
                detail=f"{entry.describe()} names test {entry.test!r}, which does not exist",
            )
        )
    return CoverageGrading(covered=frozenset(covered), findings=tuple(findings))
