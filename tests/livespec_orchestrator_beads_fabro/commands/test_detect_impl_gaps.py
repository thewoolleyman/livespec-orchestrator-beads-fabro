"""Tests for the detect-impl-gaps thin-transport command.

The command is a HEADING-COVERAGE enumerator per `SPECIFICATION/contracts.md`
and Scenario 205 of `SPECIFICATION/scenarios.md`: it emits one gap per H2
heading of the governed spec tree that no test exercises, and never
enumerates MUST/SHOULD clauses.

Gap-ids are asserted as FROZEN GOLDEN CONSTANTS rather than recomputed
through the derivation under test. Recomputing them would make every
assertion here true by construction — a renamed heading, a changed
payload separator or a different hash would all keep passing — and the
whole point of the id is that the SAME heading yields the SAME id across
runs and releases, which only a frozen value can hold the implementation
to.
"""

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands.detect_impl_gaps import main

# Frozen heading-derived gap-ids for the fixture headings below. Each is a
# pure function of the spec-root-relative spec file and the verbatim H2
# heading line, so the same pair reproduces the same id on every platform.
_GAP_ABSENT = "gap-yazf6mdi"  # spec.md "## Absent heading"
_GAP_TODO = "gap-cklnfbug"  # spec.md "## Todo heading"
_GAP_DANGLING = "gap-z7ijrvk5"  # spec.md "## Dangling heading"
_GAP_SHARED_IN_CONTRACTS = "gap-furwz3zz"  # contracts.md "## Shared heading"
_GAP_SHARED_IN_SCENARIOS = "gap-ycahxxq5"  # scenarios.md "## Shared heading"

_EXISTING_TEST_NODE = "tests.integration.test_present.test_present_case"

_THREE_UNCOVERED_HEADINGS = (
    "# Title\n\n## Absent heading\n\nProse.\n\n## Todo heading\n\nProse.\n\n"
    "## Dangling heading\n\nProse.\n"
)


def _write_spec(*, root: Path, files: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    history = root / "history" / "v001"
    history.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (root / name).write_text(content)


def _write_coverage(*, project_root: Path, entries: list[dict[str, str]]) -> None:
    coverage = project_root / "tests" / "heading-coverage.json"
    coverage.parent.mkdir(parents=True, exist_ok=True)
    coverage.write_text(json.dumps(entries))


def _write_existing_test_node(*, project_root: Path) -> None:
    """Materialize the test `_EXISTING_TEST_NODE` names, so the node resolves.

    A real module with a real function, because "names an existing test" is a
    claim about the tree: an entry pointing at nothing must not read as
    covering, and only a resolvable counterpart can tell the two apart.
    """
    module = project_root / "tests" / "integration" / "test_present.py"
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text("def test_present_case() -> None:\n    pass\n")


def _uncovered_fixture(*, project_root: Path) -> None:
    """A spec tree whose three H2 headings are uncovered in three ways."""
    _write_spec(
        root=project_root / "SPECIFICATION",
        files={"spec.md": _THREE_UNCOVERED_HEADINGS},
    )
    _write_coverage(
        project_root=project_root,
        entries=[
            {
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "heading": "## Todo heading",
                "test": "TODO",
                "reason": "an integration-tier test is owed for this heading",
            },
            {
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "heading": "## Dangling heading",
                "test": "tests.integration.test_vanished.test_vanished_case",
            },
        ],
    )


def test_json_emits_one_gap_per_uncovered_heading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Absent, `TODO`-bound and dangling entries each leave their heading a gap."""
    monkeypatch.chdir(tmp_path)
    _uncovered_fixture(project_root=tmp_path)
    rc = main(argv=["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload["gap_ids"] == sorted([_GAP_ABSENT, _GAP_TODO, _GAP_DANGLING])


def test_json_payload_carries_only_the_gap_ids_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The machine surface stays the ratified one-key object.

    Doctor's two cross-boundary invariants subprocess this surface and read
    its stdout, so a second key here is a wire-format change for them.
    """
    monkeypatch.chdir(tmp_path)
    _uncovered_fixture(project_root=tmp_path)
    rc = main(argv=["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert list(json.loads(captured.out)) == ["gap_ids"]


def test_gap_ids_are_identical_across_two_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The same spec tree yields the same gap-id set, so an id can anchor a label."""
    monkeypatch.chdir(tmp_path)
    _uncovered_fixture(project_root=tmp_path)
    assert main(argv=["--json"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert main(argv=["--json"]) == 0
    second = json.loads(capsys.readouterr().out)
    assert first == second


def test_human_output_names_the_spec_file_and_heading_each_gap_derives_from(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _uncovered_fixture(project_root=tmp_path)
    rc = main(argv=[])
    captured = capsys.readouterr()
    assert rc == 0
    assert f"SPECIFICATION/spec.md > ## Absent heading  [{_GAP_ABSENT}]" in captured.out


def test_human_output_reports_an_entirely_covered_tree_as_no_gaps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_spec(root=tmp_path / "SPECIFICATION", files={"spec.md": "# Title\n\nProse only.\n"})
    _write_coverage(project_root=tmp_path, entries=[])
    rc = main(argv=[])
    captured = capsys.readouterr()
    assert rc == 0
    assert "(no uncovered headings detected)" in captured.out


def test_no_must_or_should_clause_is_enumerated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A clause-bearing file yields one gap for its heading, never one per clause."""
    monkeypatch.chdir(tmp_path)
    _write_spec(
        root=tmp_path / "SPECIFICATION",
        files={
            "spec.md": (
                "# Title\n\n## Absent heading\n\n"
                "Every reader MUST validate the input.\n"
                "Implementations SHOULD prefer the typed API.\n"
                "Callers MUST NOT pass null.\n"
                "Plugins SHOULD NOT shell out.\n"
            )
        },
    )
    _write_coverage(project_root=tmp_path, entries=[])
    rc = main(argv=["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["gap_ids"] == [_GAP_ABSENT]


def test_headings_outside_the_governed_nlspec_files_are_not_enumerated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The governed population is the NLSpec file set the coverage map covers.

    `SPECIFICATION/README.md` is skill-owned prose that carries no coverage
    entry, so enumerating its headings would report three permanent gaps
    nobody can ever close.
    """
    monkeypatch.chdir(tmp_path)
    _write_spec(
        root=tmp_path / "SPECIFICATION",
        files={
            "spec.md": "# Title\n\n## Absent heading\n\nProse.\n",
            "README.md": "# Readme\n\n## Not governed\n\nProse.\n",
            "schema.json": '{"note": "## not a heading"}\n',
        },
    )
    _write_coverage(project_root=tmp_path, entries=[])
    rc = main(argv=["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["gap_ids"] == [_GAP_ABSENT]


def test_proposed_changes_headings_are_not_enumerated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "SPECIFICATION"
    _write_spec(root=spec, files={"spec.md": "# Title\n\n## Absent heading\n\nProse.\n"})
    proposed = spec / "proposed_changes"
    proposed.mkdir()
    (proposed / "spec.md").write_text("# Draft\n\n## Pending heading\n\nProse.\n")
    _write_coverage(project_root=tmp_path, entries=[])
    rc = main(argv=["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["gap_ids"] == [_GAP_ABSENT]


def test_explicit_spec_target_and_project_root_resolve_the_coverage_map(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = tmp_path / "elsewhere"
    _write_spec(
        root=project / "MyCustomSpec",
        files={"spec.md": "# Title\n\n## Absent heading\n\nProse.\n"},
    )
    _write_coverage(project_root=project, entries=[])
    rc = main(
        argv=[
            "--project-root",
            str(project),
            "--spec-target",
            str(project / "MyCustomSpec"),
            "--json",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["gap_ids"] == [_GAP_ABSENT]


def test_project_root_alone_defaults_the_spec_target(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = tmp_path / "elsewhere"
    _write_spec(
        root=project / "SPECIFICATION",
        files={"spec.md": "# Title\n\n## Absent heading\n\nProse.\n"},
    )
    _write_coverage(project_root=project, entries=[])
    rc = main(argv=["--project-root", str(project), "--json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["gap_ids"] == [_GAP_ABSENT]


# ---------------------------------------------------------------
# A heading an existing test exercises is not a gap
# ---------------------------------------------------------------


def test_a_heading_whose_entry_names_an_existing_test_produces_no_gap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The covered heading drops out while its uncovered sibling stays.

    Both headings live in ONE fixture because each is the other's control: a
    build that emitted a gap for every heading satisfies the sibling's
    presence, and one that emitted none satisfies the covered heading's
    absence.
    """
    monkeypatch.chdir(tmp_path)
    _write_spec(
        root=tmp_path / "SPECIFICATION",
        files={"spec.md": "# Title\n\n## Covered heading\n\nProse.\n\n## Absent heading\n"},
    )
    _write_existing_test_node(project_root=tmp_path)
    _write_coverage(
        project_root=tmp_path,
        entries=[
            {
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "heading": "## Covered heading",
                "test": _EXISTING_TEST_NODE,
            }
        ],
    )
    rc = main(argv=["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["gap_ids"] == [_GAP_ABSENT]


def test_coverage_entries_match_on_spec_root_spec_file_and_heading_together(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One entry covers ONE file's heading, never every file's same-named one.

    Two spec files carry the identical H2 heading text and only `scenarios.md`
    is covered, so a match on heading alone — or on file-and-heading without
    the root — reports no gap at all and the contracts.md heading goes
    permanently unnoticed.
    """
    monkeypatch.chdir(tmp_path)
    _write_spec(
        root=tmp_path / "SPECIFICATION",
        files={
            "contracts.md": "# Contracts\n\n## Shared heading\n",
            "scenarios.md": "# Scenarios\n\n## Shared heading\n",
        },
    )
    _write_existing_test_node(project_root=tmp_path)
    _write_coverage(
        project_root=tmp_path,
        entries=[
            {
                "spec_root": "SPECIFICATION",
                "spec_file": "scenarios.md",
                "heading": "## Shared heading",
                "test": _EXISTING_TEST_NODE,
            }
        ],
    )
    rc = main(argv=["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["gap_ids"] == [_GAP_SHARED_IN_CONTRACTS]
    assert _GAP_SHARED_IN_SCENARIOS not in json.loads(captured.out)["gap_ids"]


def test_an_entry_naming_another_spec_root_covers_nothing_here(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The root is part of the key, so a sibling tree's entry is not this one's."""
    monkeypatch.chdir(tmp_path)
    _write_spec(
        root=tmp_path / "SPECIFICATION",
        files={"spec.md": "# Title\n\n## Absent heading\n"},
    )
    _write_existing_test_node(project_root=tmp_path)
    _write_coverage(
        project_root=tmp_path,
        entries=[
            {
                "spec_root": "SPECIFICATION/templates/other",
                "spec_file": "spec.md",
                "heading": "## Absent heading",
                "test": _EXISTING_TEST_NODE,
            }
        ],
    )
    rc = main(argv=["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["gap_ids"] == [_GAP_ABSENT]


# ---------------------------------------------------------------
# A defective entry is an uncovered heading AND a surfaced finding
# ---------------------------------------------------------------


def test_a_dangling_entry_is_surfaced_as_a_finding_naming_it_and_its_defect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A test that was renamed away leaves an entry nobody can read as evidence.

    The gap alone would be a CLEAN ABSENCE — indistinguishable from a heading
    that was never entered — so the entry and its defect are named too.
    """
    monkeypatch.chdir(tmp_path)
    _uncovered_fixture(project_root=tmp_path)
    rc = main(argv=["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert _GAP_DANGLING in json.loads(captured.out)["gap_ids"]
    assert "dangling-test" in captured.err
    assert "SPECIFICATION/spec.md" in captured.err
    assert "## Dangling heading" in captured.err
    assert "tests.integration.test_vanished.test_vanished_case" in captured.err


def test_an_entry_that_states_no_test_value_is_a_gap_and_a_finding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An incomplete entry identifies its heading and claims nothing for it."""
    monkeypatch.chdir(tmp_path)
    _write_spec(
        root=tmp_path / "SPECIFICATION",
        files={"spec.md": "# Title\n\n## Absent heading\n"},
    )
    _write_coverage(
        project_root=tmp_path,
        entries=[
            {
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "heading": "## Absent heading",
            }
        ],
    )
    rc = main(argv=["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["gap_ids"] == [_GAP_ABSENT]
    assert "incomplete-entry" in captured.err
    assert "## Absent heading" in captured.err


def test_the_todo_sentinel_is_a_gap_and_carries_no_finding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`TODO` is the sanctioned debt row, not a defect — this is the discriminator.

    Without it, a build that surfaced a finding for every uncovered heading
    satisfies both cases above while burying the two real defects under this
    repository's 128 `TODO` rows.
    """
    monkeypatch.chdir(tmp_path)
    _write_spec(
        root=tmp_path / "SPECIFICATION",
        files={"spec.md": "# Title\n\n## Todo heading\n"},
    )
    _write_coverage(
        project_root=tmp_path,
        entries=[
            {
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "heading": "## Todo heading",
                "test": "TODO",
                "reason": "an integration-tier test is owed for this heading",
            }
        ],
    )
    rc = main(argv=["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["gap_ids"] == [_GAP_TODO]
    assert captured.err == ""


def test_a_heading_with_no_entry_at_all_carries_no_finding_of_its_own(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An absent entry is the ordinary state of an un-entered heading."""
    monkeypatch.chdir(tmp_path)
    _write_spec(
        root=tmp_path / "SPECIFICATION",
        files={"spec.md": "# Title\n\n## Absent heading\n"},
    )
    _write_coverage(project_root=tmp_path, entries=[])
    rc = main(argv=["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["gap_ids"] == [_GAP_ABSENT]
    assert captured.err == ""


def test_findings_never_enter_the_machine_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Findings ride stderr so doctor's stdout read stays the one-key object."""
    monkeypatch.chdir(tmp_path)
    _uncovered_fixture(project_root=tmp_path)
    rc = main(argv=["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert list(json.loads(captured.out)) == ["gap_ids"]
    assert "dangling-test" not in captured.out


def test_findings_are_surfaced_in_the_human_form_too(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _uncovered_fixture(project_root=tmp_path)
    rc = main(argv=[])
    captured = capsys.readouterr()
    assert rc == 0
    assert "dangling-test" in captured.err


# ---------------------------------------------------------------
# An entry that identifies no live heading is a finding and never a gap
# ---------------------------------------------------------------


def test_an_entry_stating_no_heading_is_a_finding_and_produces_no_gap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The row identifies nothing, so there is no heading it could be a gap for.

    The live heading beside it is the control: it still becomes a gap, which is
    what tells "the unidentifiable row produced no gap" apart from "the scan
    produced no gaps".
    """
    monkeypatch.chdir(tmp_path)
    _write_spec(
        root=tmp_path / "SPECIFICATION",
        files={"spec.md": "# Title\n\n## Absent heading\n"},
    )
    _write_coverage(
        project_root=tmp_path,
        entries=[{"test": "TODO", "reason": "an integration-tier test is owed"}],
    )
    rc = main(argv=["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["gap_ids"] == [_GAP_ABSENT]
    assert "unidentifiable-entry" in captured.err


def test_an_entry_naming_a_heading_the_live_tree_does_not_contain_is_a_finding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A heading that was renamed or deleted leaves a row pointing at nothing.

    The row names an EXISTING test, so a build that only checked the test
    would read it as proven coverage and say nothing — the row then sits in
    the registry for ever, claiming a heading no longer there.
    """
    monkeypatch.chdir(tmp_path)
    _write_spec(
        root=tmp_path / "SPECIFICATION",
        files={"spec.md": "# Title\n\n## Absent heading\n"},
    )
    _write_existing_test_node(project_root=tmp_path)
    _write_coverage(
        project_root=tmp_path,
        entries=[
            {
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "heading": "## Ghost heading",
                "test": _EXISTING_TEST_NODE,
            }
        ],
    )
    rc = main(argv=["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["gap_ids"] == [_GAP_ABSENT]
    assert "unidentifiable-entry" in captured.err
    assert "## Ghost heading" in captured.err


def test_both_unidentifiable_shapes_surface_one_finding_each(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One finding per row, and every live heading with no entry still a gap."""
    monkeypatch.chdir(tmp_path)
    _write_spec(
        root=tmp_path / "SPECIFICATION",
        files={"spec.md": "# Title\n\n## Absent heading\n\n## Todo heading\n"},
    )
    _write_coverage(
        project_root=tmp_path,
        entries=[
            {"test": "TODO", "reason": "an integration-tier test is owed"},
            {
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "heading": "## Ghost heading",
                "test": "TODO",
                "reason": "an integration-tier test is owed",
            },
        ],
    )
    rc = main(argv=["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["gap_ids"] == sorted([_GAP_ABSENT, _GAP_TODO])
    assert captured.err.count("unidentifiable-entry") == 2


# ---------------------------------------------------------------
# --since-version validation
# ---------------------------------------------------------------


@pytest.mark.parametrize("raw", ["vXXX", "-3", "0"])
def test_since_version_that_is_not_a_positive_integer_exits_two(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    raw: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_spec(root=tmp_path / "SPECIFICATION", files={"spec.md": "# T\n\nProse.\n"})
    _write_coverage(project_root=tmp_path, entries=[])
    rc = main(argv=["--since-version", raw])
    captured = capsys.readouterr()
    assert rc == 2
    assert "ERROR" in captured.err
    assert "--since-version" in captured.err


def test_since_version_naming_an_absent_history_directory_exits_three(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_spec(root=tmp_path / "SPECIFICATION", files={"spec.md": "# T\n\nProse.\n"})
    _write_coverage(project_root=tmp_path, entries=[])
    rc = main(argv=["--since-version", "v999"])
    captured = capsys.readouterr()
    assert rc == 3
    assert "ERROR" in captured.err
    assert "v999" in captured.err
