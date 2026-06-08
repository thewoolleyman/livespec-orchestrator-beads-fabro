"""Tests for the detect-impl-gaps thin-transport command."""

import json
from pathlib import Path

import pytest
from livespec_impl_beads.commands.detect_impl_gaps import (
    detect_rules,
    main,
)


def _write_spec(*, root: Path, files: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    history = root / "history" / "v001"
    history.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (root / name).write_text(content)


def test_main_no_rules_human_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "SPECIFICATION"
    _write_spec(root=spec, files={"spec.md": "# Heading\n\nNo rules here.\n"})
    rc = main([])
    captured = capsys.readouterr()
    assert rc == 0
    assert "(no rules detected)" in captured.out


def test_main_detects_must_and_should_rules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "SPECIFICATION"
    _write_spec(
        root=spec,
        files={
            "spec.md": (
                "# Top\n\n"
                "## Section A\n\n"
                "Every reader MUST validate the input.\n"
                "Implementations SHOULD prefer the typed API.\n"
                "Callers MUST NOT pass null.\n"
                "Plugins SHOULD NOT shell out.\n"
                "\n"
                "## Section B\n\n"
                "Just a normal paragraph with must in lowercase — no rule.\n"
            ),
        },
    )
    rc = main([])
    captured = capsys.readouterr()
    assert rc == 0
    assert "MUST validate" in captured.out
    assert "SHOULD prefer" in captured.out
    assert "MUST NOT pass" in captured.out
    assert "SHOULD NOT shell out" in captured.out
    # Lowercase 'must' MUST NOT match.
    assert "no rule" not in captured.out


def test_main_excludes_code_fences(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "SPECIFICATION"
    _write_spec(
        root=spec,
        files={
            "spec.md": (
                "# Top\n\n"
                "Outside the fence: implementations MUST honor this.\n"
                "\n"
                "```python\n"
                "# inside fence: this MUST be skipped\n"
                "def f(): pass\n"
                "```\n"
                "\n"
                "After the fence: callers SHOULD retry.\n"
            ),
        },
    )
    rc = main([])
    captured = capsys.readouterr()
    assert rc == 0
    assert "MUST honor" in captured.out
    assert "SHOULD retry" in captured.out
    assert "MUST be skipped" not in captured.out


def test_main_emits_json_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "SPECIFICATION"
    _write_spec(
        root=spec,
        files={"spec.md": "# T\n\nEverything MUST be deterministic.\n"},
    )
    rc = main(["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert "gap_ids" in payload
    assert len(payload["gap_ids"]) == 1
    assert payload["gap_ids"][0].startswith("gap-")


def test_main_excludes_proposed_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "SPECIFICATION"
    _write_spec(
        root=spec,
        files={"spec.md": "# T\n\nLive rules MUST land here.\n"},
    )
    proposed = spec / "proposed_changes"
    proposed.mkdir()
    (proposed / "draft.md").write_text("# Draft\n\nThis pending rule MUST not surface.\n")
    rc = main(["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    # Only the live spec.md rule surfaces; the proposed_changes draft does not.
    assert len(payload["gap_ids"]) == 1


def test_main_uses_explicit_spec_target_and_project_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = tmp_path / "elsewhere"
    spec = project / "MyCustomSpec"
    _write_spec(root=spec, files={"spec.md": "# T\n\nReaders MUST cope.\n"})
    rc = main(["--project-root", str(project), "--spec-target", str(spec), "--json"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert len(payload["gap_ids"]) == 1


def test_main_project_root_with_default_spec_target(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = tmp_path / "elsewhere"
    spec = project / "SPECIFICATION"
    _write_spec(root=spec, files={"spec.md": "# T\n\nReaders MUST cope.\n"})
    rc = main(["--project-root", str(project), "--json"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert len(payload["gap_ids"]) == 1


def test_main_skips_non_markdown_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "SPECIFICATION"
    _write_spec(
        root=spec,
        files={
            "spec.md": "# T\n\nMarkdown rule MUST surface.\n",
            "schema.json": '{"note": "JSON files MUST not be scanned"}\n',
        },
    )
    rc = main(["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert len(payload["gap_ids"]) == 1


def test_main_skips_blank_lines_with_keyword(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # A line that's only whitespace MUST NOT count even if the regex
    # would otherwise match (defensive — the regex needs a real word
    # boundary).
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "SPECIFICATION"
    _write_spec(
        root=spec,
        files={
            "spec.md": (
                "# Top\n"
                "\n"
                "MUST\n"  # standalone keyword on its own line — still a rule
                "\n"
                "Real rule: callers MUST do X.\n"
            ),
        },
    )
    rc = main(["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    # Two non-empty lines matched: "MUST" alone and "callers MUST do X."
    assert len(payload["gap_ids"]) == 2


def test_main_detects_rule_at_top_of_file_without_heading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "SPECIFICATION"
    _write_spec(
        root=spec,
        files={"spec.md": "Readers MUST handle the no-heading case.\n# Then Heading\n"},
    )
    rc = main([])
    captured = capsys.readouterr()
    assert rc == 0
    assert "(top)" in captured.out


def test_main_heading_stack_handles_level_jumps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Skip from H1 directly to H3 (no H2). Stack should pad an empty H2.
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "SPECIFICATION"
    _write_spec(
        root=spec,
        files={
            "spec.md": (
                "# H1\n"
                "\n"
                "### H3 (jumped)\n"
                "\n"
                "Rule MUST appear under jumped heading path.\n"
            ),
        },
    )
    rc = main([])
    captured = capsys.readouterr()
    assert rc == 0
    assert "H1 >  > H3 (jumped)" in captured.out


def test_detect_rules_deterministic_across_calls(tmp_path: Path) -> None:
    spec = tmp_path / "SPECIFICATION"
    _write_spec(
        root=spec,
        files={"spec.md": "# Heading\n\nReaders MUST cope.\nCallers SHOULD retry.\n"},
    )
    first = detect_rules(spec_root=spec)
    second = detect_rules(spec_root=spec)
    assert [r.gap_id for r in first] == [r.gap_id for r in second]


def test_detect_rules_returns_sorted_by_file_heading_text(tmp_path: Path) -> None:
    spec = tmp_path / "SPECIFICATION"
    _write_spec(
        root=spec,
        files={
            "z_last.md": "# Z\n\nFile Z MUST appear after.\n",
            "a_first.md": "# A\n\nFile A MUST appear first.\n",
        },
    )
    rules = detect_rules(spec_root=spec)
    spec_files = [r.spec_file for r in rules]
    assert spec_files == sorted(spec_files)


# ---------------------------------------------------------------
# --since-version flag tests
# ---------------------------------------------------------------


def _write_history_version(*, spec_root: Path, version: int, files: dict[str, str]) -> None:
    """Populate <spec_root>/history/v<NNN>/ with the given files."""
    version_dir = spec_root / "history" / f"v{version:03d}"
    version_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        target = version_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)


def test_since_version_filters_to_diff_against_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--since-version v080 filters detection to spec diff v080→latest."""
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "SPECIFICATION"
    spec.mkdir()
    # v080 baseline: two files, both with one rule each.
    _write_history_version(
        spec_root=spec,
        version=80,
        files={
            "stable.md": "# Stable\n\nLegacy callers MUST honor this.\n",
            "changed.md": "# Changed\n\nOld rule MUST survive.\n",
        },
    )
    # Latest history snapshot (v081) and live tree: stable.md untouched;
    # changed.md gains a NEW rule.
    _write_history_version(
        spec_root=spec,
        version=81,
        files={
            "stable.md": "# Stable\n\nLegacy callers MUST honor this.\n",
            "changed.md": ("# Changed\n\nOld rule MUST survive.\nBrand-new readers MUST adapt.\n"),
        },
    )
    (spec / "stable.md").write_text("# Stable\n\nLegacy callers MUST honor this.\n")
    (spec / "changed.md").write_text(
        "# Changed\n\nOld rule MUST survive.\nBrand-new readers MUST adapt.\n"
    )
    rc = main(["--json", "--since-version", "v080"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    # Only rules in `changed.md` (the diffing file) surface.
    # stable.md's rule MUST NOT appear because the file is unchanged.
    assert len(payload["gap_ids"]) == 2
    # And human form names changed.md only.
    rc2 = main(["--since-version", "v080"])
    captured2 = capsys.readouterr()
    assert rc2 == 0
    assert "changed.md" in captured2.out
    assert "stable.md" not in captured2.out


def test_since_version_accepts_bare_integer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--since-version 80 (bare integer) works identically to v080."""
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "SPECIFICATION"
    spec.mkdir()
    _write_history_version(
        spec_root=spec,
        version=80,
        files={"spec.md": "# T\n\nOld rule MUST hold.\n"},
    )
    (spec / "spec.md").write_text("# T\n\nOld rule MUST hold.\nNew rule MUST land.\n")
    rc = main(["--json", "--since-version", "80"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert len(payload["gap_ids"]) == 2


def test_no_since_version_preserves_full_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Flag absent → existing behavior: full scan, all gaps."""
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "SPECIFICATION"
    spec.mkdir()
    _write_history_version(
        spec_root=spec,
        version=80,
        files={
            "stable.md": "# Stable\n\nLegacy callers MUST honor this.\n",
            "changed.md": "# Changed\n\nOld rule MUST survive.\n",
        },
    )
    (spec / "stable.md").write_text("# Stable\n\nLegacy callers MUST honor this.\n")
    (spec / "changed.md").write_text(
        "# Changed\n\nOld rule MUST survive.\nNew readers MUST adapt.\n"
    )
    rc = main(["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    # Without scoping, all three live rules surface (stable + 2 from changed).
    assert len(payload["gap_ids"]) == 3


def test_since_version_invalid_non_integer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Invalid --since-version value (vXXX) → exit 2 with usage error."""
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "SPECIFICATION"
    _write_spec(root=spec, files={"spec.md": "# T\n\nReaders MUST cope.\n"})
    rc = main(["--since-version", "vXXX"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "ERROR" in captured.err
    assert "--since-version" in captured.err


def test_since_version_invalid_negative(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Negative integer → exit 2 with usage error."""
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "SPECIFICATION"
    _write_spec(root=spec, files={"spec.md": "# T\n\nReaders MUST cope.\n"})
    rc = main(["--since-version", "-3"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "ERROR" in captured.err


def test_since_version_invalid_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Zero is not a positive integer → exit 2 with usage error."""
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "SPECIFICATION"
    _write_spec(root=spec, files={"spec.md": "# T\n\nReaders MUST cope.\n"})
    rc = main(["--since-version", "0"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "ERROR" in captured.err


def test_since_version_nonexistent_history_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Missing version dir → exit 3 with PreconditionError naming the path."""
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "SPECIFICATION"
    _write_spec(root=spec, files={"spec.md": "# T\n\nReaders MUST cope.\n"})
    # Only v001 exists (created by _write_spec). v999 does not.
    rc = main(["--since-version", "v999"])
    captured = capsys.readouterr()
    assert rc == 3
    assert "ERROR" in captured.err
    assert "v999" in captured.err


def test_since_version_equals_latest_empty_diff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--since-version v<N> where the live tree matches v<N> → empty gap-id set."""
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "SPECIFICATION"
    spec.mkdir()
    files = {"spec.md": "# T\n\nReaders MUST cope.\nWriters MUST close.\n"}
    _write_history_version(spec_root=spec, version=42, files=files)
    # Live tree matches v042 byte-for-byte.
    for name, content in files.items():
        (spec / name).write_text(content)
    rc = main(["--json", "--since-version", "v042"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload["gap_ids"] == []


def test_since_version_skips_removed_in_diff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Rules removed by the diff are NOT gaps — only LIVE rules surface."""
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "SPECIFICATION"
    spec.mkdir()
    # v050: file has a rule that gets removed in the live spec.
    _write_history_version(
        spec_root=spec,
        version=50,
        files={"shrink.md": "# Shrink\n\nA: callers MUST quack.\nB: writers MUST close.\n"},
    )
    # Live tree: rule A removed, B retained.
    (spec / "shrink.md").write_text("# Shrink\n\nB: writers MUST close.\n")
    rc = main(["--json", "--since-version", "v050"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    # The file CHANGED, so it's in scope. Only the surviving rule
    # (rule B) surfaces — rule A was removed.
    assert len(payload["gap_ids"]) == 1


def test_since_version_passes_through_spec_target(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--since-version composes with explicit --spec-target / --project-root."""
    project = tmp_path / "elsewhere"
    spec = project / "MySpec"
    spec.mkdir(parents=True)
    _write_history_version(
        spec_root=spec,
        version=10,
        files={"spec.md": "# T\n\nOld rule MUST survive.\n"},
    )
    (spec / "spec.md").write_text("# T\n\nOld rule MUST survive.\nNew rule MUST land.\n")
    rc = main(
        [
            "--project-root",
            str(project),
            "--spec-target",
            str(spec),
            "--json",
            "--since-version",
            "v010",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert len(payload["gap_ids"]) == 2
