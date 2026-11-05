"""The installed breakage pass reads the committed workflow and real Actions logs."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_breakage_forge import (
    FailedJob,
    failing_tests,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TIMESTAMPED_LOG = (
    "2026-11-05T01:02:03.4567890Z ============ short test summary info ============\n"
    "2026-11-05T01:02:03.4567891Z FAILED tests/test_a.py::test_one - AssertionError: x\n"
    "2026-11-05T01:02:03.4567892Z ERROR tests/test_b.py::test_two\n"
    "2026-11-05T01:02:03.4567893Z ##[error]Process completed with exit code 1.\n"
)


def test_the_committed_config_watches_the_root_uid_workflow() -> None:
    """Scenario 313 needs the installed timer to read ci-root-uid.yml."""
    assert dispatcher_block(cwd=_REPO_ROOT).get("breakage_workflows") == ["ci-root-uid.yml"]


def test_failing_tests_are_named_from_timestamp_prefixed_actions_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario 313 names each failing test; GitHub prefixes every log line with a timestamp."""
    log = tmp_path / "log.txt"
    log.write_text(_TIMESTAMPED_LOG, encoding="utf-8")
    fake_gh = tmp_path / "bin" / "gh"
    fake_gh.parent.mkdir()
    fake_gh.write_text(f'#!/bin/sh\ncat "{log}"\n', encoding="utf-8")
    fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{fake_gh.parent}:/usr/bin:/bin")

    tests, problem = failing_tests(
        repo=tmp_path, job=FailedJob(identifier=7, name="root-uid", failed_step="pytest")
    )

    assert problem is None
    assert tests == ("tests/test_a.py::test_one", "tests/test_b.py::test_two")
