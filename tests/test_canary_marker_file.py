"""The dedicated canary marker file, and why a one-line edit to it is accepted.

A canary is a measurement of the ENGINE, so its deliverable has to be the
smallest change this repository has. `orchestrator-image/canary-marker.md` is
that change's target: a plain Markdown file nothing reads but a human counting
canaries.

The second test is the load-bearing one, and it is a POSITIVE control rather
than an argument. Asserting that the marker sits outside every scanned tree
would establish that no gate is pointed at it; it would NOT establish what the
commit gate actually does with a one-line edit there. So the real
mode-selection script is invoked, in a throwaway repository, against a staged
one-line edit at the marker's exact path — and the arm it selects is the
assertion.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_canary import (
    CANARY_MARKER_RELATIVE_PATH,
    read_canary_fixture,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MODE_SELECTION_SCRIPT = _REPO_ROOT / "dev-tooling" / "just-check-pre-commit.sh"
_RECORD_HEADING = "## Recorded canary dispatches"
_DOC_ONLY_ARM = "check-pre-commit-doc-only"
# Every tree this repository's own check configuration points a scanner at. The
# marker is under none of them, which is what makes the doc-only arm below the
# arm a marker edit can reach at all.
_SCANNED_TREE_PREFIXES = (
    ".claude-plugin/",
    ".claude/",
    "dev-tooling/",
    "tests/",
    "SPECIFICATION/",
    "plan/",
)


def _run(*, argv: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    run_env = os.environ.copy()
    if env is not None:
        run_env.update(env)
    result = subprocess.run(argv, cwd=cwd, env=run_env, check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_marker_file_is_the_one_target_the_fixture_assertion_names() -> None:
    marker = _REPO_ROOT / CANARY_MARKER_RELATIVE_PATH
    assert marker.is_file(), CANARY_MARKER_RELATIVE_PATH

    body = marker.read_text(encoding="utf-8")
    assert _RECORD_HEADING in body

    fixture = read_canary_fixture(repo=_REPO_ROOT)
    section = definition_of_done(description=fixture.description)
    assertion = section.assertions[0].text
    # One assertion, naming the marker path AND the heading the appended line
    # goes under, so the canary has nowhere else it could put the line.
    assert len(section.assertions) == 1
    assert CANARY_MARKER_RELATIVE_PATH in assertion
    assert _RECORD_HEADING in assertion


def test_the_marker_file_sits_outside_every_scanned_tree() -> None:
    for prefix in _SCANNED_TREE_PREFIXES:
        assert not CANARY_MARKER_RELATIVE_PATH.startswith(prefix), prefix
    assert CANARY_MARKER_RELATIVE_PATH.endswith(".md")


def test_a_one_line_marker_edit_selects_the_doc_only_commit_arm(*, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / Path(CANARY_MARKER_RELATIVE_PATH).parent).mkdir(parents=True)
    _run(argv=["git", "init"], cwd=repo)
    _run(argv=["git", "config", "user.email", "test@example.com"], cwd=repo)
    _run(argv=["git", "config", "user.name", "Test User"], cwd=repo)
    marker = repo / CANARY_MARKER_RELATIVE_PATH
    marker.write_text(f"# Canary marker\n\n{_RECORD_HEADING}\n", encoding="utf-8")
    _run(argv=["git", "add", "."], cwd=repo)
    _run(argv=["git", "commit", "-m", "baseline"], cwd=repo)

    # The canary's whole change: one appended line under the record heading.
    marker.write_text(
        f"# Canary marker\n\n{_RECORD_HEADING}\n\n- 2026-10-16 — canary dispatch recorded.\n",
        encoding="utf-8",
    )
    _run(argv=["git", "add", CANARY_MARKER_RELATIVE_PATH], cwd=repo)

    bin_dir = repo / "fake-bin"
    bin_dir.mkdir()
    fake_just = bin_dir / "just"
    fake_just.write_text(
        '#!/usr/bin/env bash\nset -uo pipefail\nprintf "%s\\n" "$*" >> just.log\n',
        encoding="utf-8",
    )
    fake_just.chmod(fake_just.stat().st_mode | stat.S_IXUSR)
    _run(
        argv=["bash", str(_MODE_SELECTION_SCRIPT)],
        cwd=repo,
        env={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
    )

    assert (repo / "just.log").read_text(encoding="utf-8").strip() == _DOC_ONLY_ARM
