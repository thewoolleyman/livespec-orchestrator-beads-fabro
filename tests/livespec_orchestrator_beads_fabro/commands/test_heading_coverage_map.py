"""Tests for reading the heading-coverage registry.

The join that consumes these rows is driven end to end by
`test_detect_impl_gaps.py`. These cases cover the shapes a committed JSON
file can hold that a well-formed registry never reaches — and the one
decision that must NOT be taken here, which is dropping a malformed row.
"""

from __future__ import annotations

import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._heading_coverage_map import (
    COVERAGE_RELATIVE_PATH,
    TODO_SENTINEL,
    CoverageEntry,
    read_coverage_entries,
)


def _write_registry(*, project_root: Path, payload: object) -> None:
    path = project_root / COVERAGE_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def _entry(*, test: str = TODO_SENTINEL, heading: str = "## A heading") -> CoverageEntry:
    return CoverageEntry(
        position=0,
        spec_root="SPECIFICATION",
        spec_file="spec.md",
        heading=heading,
        test=test,
    )


def test_an_absent_registry_yields_no_rows(tmp_path: Path) -> None:
    """Which reads downstream as "every heading is uncovered" — the right answer."""
    assert read_coverage_entries(project_root=tmp_path) == ()


def test_a_registry_that_is_not_a_list_yields_no_rows(tmp_path: Path) -> None:
    _write_registry(project_root=tmp_path, payload={"entries": []})
    assert read_coverage_entries(project_root=tmp_path) == ()


def test_rows_are_read_in_file_order_and_carry_their_position(tmp_path: Path) -> None:
    """Position is how a finding names a row that identifies no heading at all."""
    _write_registry(
        project_root=tmp_path,
        payload=[
            {
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "heading": "## First",
                "test": TODO_SENTINEL,
            },
            {
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "heading": "## Second",
                "test": "tests.integration.test_x.test_y",
            },
        ],
    )
    rows = read_coverage_entries(project_root=tmp_path)
    assert [(row.position, row.heading, row.test) for row in rows] == [
        (0, "## First", TODO_SENTINEL),
        (1, "## Second", "tests.integration.test_x.test_y"),
    ]


def test_a_non_object_row_is_skipped_while_its_neighbours_keep_their_positions(
    tmp_path: Path,
) -> None:
    """A row that is not an object states no triple, so there is nothing to surface.

    Its neighbours keep their FILE positions rather than being renumbered, so
    a finding names the row an operator will find at that index.
    """
    _write_registry(
        project_root=tmp_path,
        payload=[
            "not an object",
            {
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "heading": "## Second",
                "test": TODO_SENTINEL,
            },
        ],
    )
    rows = read_coverage_entries(project_root=tmp_path)
    assert [(row.position, row.heading) for row in rows] == [(1, "## Second")]


def test_an_absent_field_and_a_wrongly_typed_one_both_read_as_unstated(
    tmp_path: Path,
) -> None:
    """Both spellings of "the row does not state this" collapse to the empty string.

    An `omitempty` serializer omits a field rather than retyping it, so a
    present wrong type is a hand-edited row — and neither shape states a
    value a match could key on.
    """
    _write_registry(
        project_root=tmp_path,
        payload=[{"spec_root": "SPECIFICATION", "spec_file": 7, "heading": "## A heading"}],
    )
    [row] = read_coverage_entries(project_root=tmp_path)
    assert (row.spec_file, row.test) == ("", "")


def test_field_values_are_stripped(tmp_path: Path) -> None:
    """The live registry is hand-edited, so an accidental pad must not miss a match."""
    _write_registry(
        project_root=tmp_path,
        payload=[
            {
                "spec_root": " SPECIFICATION ",
                "spec_file": " spec.md ",
                "heading": " ## A heading ",
                "test": " TODO ",
            }
        ],
    )
    [row] = read_coverage_entries(project_root=tmp_path)
    assert row.key == ("SPECIFICATION", "spec.md", "## A heading")
    assert row.names_the_todo_sentinel


def test_a_row_identifies_a_heading_only_when_all_three_fields_are_stated() -> None:
    assert _entry().identifies_a_heading
    assert not _entry(heading="").identifies_a_heading


def test_the_todo_sentinel_is_recognized_and_a_real_node_id_is_not() -> None:
    assert _entry(test=TODO_SENTINEL).names_the_todo_sentinel
    assert not _entry(test="tests.integration.test_x.test_y").names_the_todo_sentinel


def test_a_row_that_identifies_a_heading_is_described_by_it() -> None:
    assert _entry().describe() == "entry 0 (SPECIFICATION/spec.md '## A heading')"


def test_a_row_that_identifies_no_heading_is_described_by_its_stated_fields() -> None:
    """Which field it failed to state is the only actionable thing about it."""
    described = _entry(heading="").describe()
    assert described == ("entry 0 (spec_root='SPECIFICATION' spec_file='spec.md' heading='')")
