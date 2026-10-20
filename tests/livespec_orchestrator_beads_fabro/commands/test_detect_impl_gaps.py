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
