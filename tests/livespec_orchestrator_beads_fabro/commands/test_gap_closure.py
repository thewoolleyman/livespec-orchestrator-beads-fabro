"""Check-path-anchored gap-tied closure — never gap_id-anchored (F3, F4)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro.commands import _gap_closure
from livespec_orchestrator_beads_fabro.commands._gap_closure import (
    GAP_CHECK_BASELINE_BLOB_KEY,
    GAP_CHECK_PATH_KEY,
    GAP_DRIFT_PROPOSE_CHANGE_KEY,
    decide_gap_closure,
    evaluate_gap_closure,
    record_drift_propose_change,
    record_gap_check,
)


def test_decide_refuses_when_no_check_recorded() -> None:
    decision = decide_gap_closure(
        check_recorded=False,
        check_passed=False,
        negative_control_failed=False,
        check_modified=False,
        drift_propose_change_recorded=False,
    )
    assert decision.verdict == "refuse-no-check-recorded"
    assert decision.may_close is False


def test_decide_refuses_when_check_fails() -> None:
    decision = decide_gap_closure(
        check_recorded=True,
        check_passed=False,
        negative_control_failed=True,
        check_modified=False,
        drift_propose_change_recorded=False,
    )
    assert decision.verdict == "refuse-check-failed"
    assert decision.may_close is False


def test_decide_refuses_when_negative_control_does_not_fail() -> None:
    decision = decide_gap_closure(
        check_recorded=True,
        check_passed=True,
        negative_control_failed=False,
        check_modified=False,
        drift_propose_change_recorded=False,
    )
    assert decision.verdict == "refuse-check-failed"
    assert decision.may_close is False


def test_decide_closes_when_check_passes_and_control_fails_unmodified() -> None:
    decision = decide_gap_closure(
        check_recorded=True,
        check_passed=True,
        negative_control_failed=True,
        check_modified=False,
        drift_propose_change_recorded=False,
    )
    assert decision.verdict == "close"
    assert decision.may_close is True


def test_decide_refuses_when_check_modified_without_drift_record() -> None:
    decision = decide_gap_closure(
        check_recorded=True,
        check_passed=True,
        negative_control_failed=True,
        check_modified=True,
        drift_propose_change_recorded=False,
    )
    assert decision.verdict == "refuse-drift-required"
    assert decision.may_close is False


def test_decide_closes_when_check_modified_with_drift_record() -> None:
    decision = decide_gap_closure(
        check_recorded=True,
        check_passed=True,
        negative_control_failed=True,
        check_modified=True,
        drift_propose_change_recorded=True,
    )
    assert decision.verdict == "close"
    assert decision.may_close is True


def test_decide_never_takes_a_gap_id_parameter() -> None:
    import inspect

    parameters = inspect.signature(decide_gap_closure).parameters
    assert "gap_id" not in parameters


_CHECK_SCRIPT = """
import sys

def main() -> int:
    return 1 if "--negative-control" in sys.argv else 0

if __name__ == "__main__":
    raise SystemExit(main())
"""

_ALWAYS_PASSING_CHECK_SCRIPT = """
import sys

def main() -> int:
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
"""

_SHELL_CHECK_SCRIPT = """#!/bin/sh
if [ "$1" = "--negative-control" ]; then
    exit 1
fi
exit 0
"""

_UNAVAILABLE_INTERPRETER_CHECK_SCRIPT = """#!/definitely/not/an/interpreter
import sys

raise SystemExit(1 if "--negative-control" in sys.argv else 0)
"""


_ENV_INTERPRETER_CHECK_SCRIPT = """#!/usr/bin/env gap-check-interpreter
if [ "$1" = "--negative-control" ]; then
    exit 1
fi
%s "$GAP_CHECK_INTERPRETER"
exit 0
"""

_INTERPRETER_WRAPPER_SCRIPT = """#!/bin/sh
check_path="$1"
shift
exec /bin/sh "$check_path" "$@"
"""


class _FakeClient:
    def __init__(self, *, metadata: dict[str, Any]) -> None:
        self._metadata = metadata
        self.updated_metadata: dict[str, Any] | None = None

    def show_issue(self, *, issue_id: str) -> dict[str, Any]:
        assert issue_id == "bd-ib-gap1"
        return {"id": issue_id, "metadata": dict(self._metadata)}

    def update_issue(
        self, *, issue_id: str, metadata: dict[str, Any] | None = None, **_: Any
    ) -> None:
        assert issue_id == "bd-ib-gap1"
        assert metadata is not None
        self._metadata = dict(metadata)
        self.updated_metadata = dict(metadata)


def _init_git_repo(*, repo_root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo_root, check=True)


def test_evaluate_refuses_when_no_check_path_recorded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _FakeClient(metadata={})
    monkeypatch.setattr(_gap_closure, "make_beads_client", lambda **_kwargs: client)
    decision = evaluate_gap_closure(
        config=cast("Any", None), project_root=tmp_path, item_id="bd-ib-gap1"
    )
    assert decision.verdict == "refuse-no-check-recorded"


def test_evaluate_closes_when_check_passes_and_control_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _init_git_repo(repo_root=tmp_path)
    check_path = tmp_path / "checks" / "example_check.py"
    check_path.parent.mkdir(parents=True)
    check_path.write_text(_CHECK_SCRIPT, encoding="utf-8")

    client = _FakeClient(
        metadata={GAP_CHECK_PATH_KEY: "checks/example_check.py"},
    )
    monkeypatch.setattr(_gap_closure, "make_beads_client", lambda **_kwargs: client)

    decision = evaluate_gap_closure(
        config=cast("Any", None), project_root=tmp_path, item_id="bd-ib-gap1"
    )
    assert decision.verdict == "close"


def test_evaluate_closes_generic_shell_check_with_declared_interpreter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _init_git_repo(repo_root=tmp_path)
    check_path = tmp_path / "checks" / "generic_check.sh"
    check_path.parent.mkdir(parents=True)
    check_path.write_text(_SHELL_CHECK_SCRIPT, encoding="utf-8")
    check_path.chmod(0o755)

    client = _FakeClient(metadata={GAP_CHECK_PATH_KEY: "checks/generic_check.sh"})
    monkeypatch.setattr(_gap_closure, "make_beads_client", lambda **_kwargs: client)

    decision = evaluate_gap_closure(
        config=cast("Any", None), project_root=tmp_path, item_id="bd-ib-gap1"
    )

    assert decision.verdict == "close"


def test_evaluate_refuses_unavailable_declared_interpreter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _init_git_repo(repo_root=tmp_path)
    check_path = tmp_path / "checks" / "unavailable_interpreter.py"
    check_path.parent.mkdir(parents=True)
    check_path.write_text(_UNAVAILABLE_INTERPRETER_CHECK_SCRIPT, encoding="utf-8")
    check_path.chmod(0o755)

    client = _FakeClient(metadata={GAP_CHECK_PATH_KEY: "checks/unavailable_interpreter.py"})
    monkeypatch.setattr(_gap_closure, "make_beads_client", lambda **_kwargs: client)

    decision = evaluate_gap_closure(
        config=cast("Any", None), project_root=tmp_path, item_id="bd-ib-gap1"
    )

    assert decision.verdict == "refuse-check-failed"
    assert decision.detail == "the recorded check did not pass"


@pytest.mark.parametrize(
    ("interpreter_mutation", "process_umask"),
    [
        ("rm", None),
        pytest.param("chmod a-x", None, id="chmod -x"),
        pytest.param("chmod a-x", 0o077, id="chmod -x-umask-077"),
    ],
)
def test_evaluate_refuses_when_env_interpreter_becomes_unavailable_between_legs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    interpreter_mutation: str,
    process_umask: int | None,
) -> None:
    """An env-shebang launch failure cannot prove a negative control discriminates."""
    _init_git_repo(repo_root=tmp_path)
    interpreter_dir = tmp_path / "bin"
    interpreter_dir.mkdir()
    interpreter_path = interpreter_dir / "gap-check-interpreter"
    interpreter_path.write_text(_INTERPRETER_WRAPPER_SCRIPT, encoding="utf-8")
    interpreter_path.chmod(0o755)
    check_path = tmp_path / "checks" / "interpreter_changes_between_legs.sh"
    check_path.parent.mkdir(parents=True)
    check_path.write_text(
        _ENV_INTERPRETER_CHECK_SCRIPT % interpreter_mutation,
        encoding="utf-8",
    )
    check_path.chmod(0o755)
    monkeypatch.setenv(
        "PATH",
        f"{interpreter_dir}:{os.environ['PATH']}",
    )
    monkeypatch.setenv("GAP_CHECK_INTERPRETER", str(interpreter_path))

    client = _FakeClient(
        metadata={GAP_CHECK_PATH_KEY: "checks/interpreter_changes_between_legs.sh"}
    )
    monkeypatch.setattr(_gap_closure, "make_beads_client", lambda **_kwargs: client)

    if process_umask is None:
        decision = evaluate_gap_closure(
            config=cast("Any", None), project_root=tmp_path, item_id="bd-ib-gap1"
        )
    else:
        previous_umask = os.umask(process_umask)
        try:
            decision = evaluate_gap_closure(
                config=cast("Any", None), project_root=tmp_path, item_id="bd-ib-gap1"
            )
        finally:
            os.umask(previous_umask)

    assert decision.verdict == "refuse-check-failed"


def test_evaluate_refuses_unavailable_check_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _init_git_repo(repo_root=tmp_path)
    client = _FakeClient(metadata={GAP_CHECK_PATH_KEY: "checks/missing_check.py"})
    monkeypatch.setattr(_gap_closure, "make_beads_client", lambda **_kwargs: client)

    decision = evaluate_gap_closure(
        config=cast("Any", None), project_root=tmp_path, item_id="bd-ib-gap1"
    )

    assert decision.verdict == "refuse-check-failed"


def test_evaluate_refuses_when_check_does_not_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _init_git_repo(repo_root=tmp_path)
    check_path = tmp_path / "checks" / "always_fails.py"
    check_path.parent.mkdir(parents=True)
    check_path.write_text("raise SystemExit(1)\n", encoding="utf-8")

    client = _FakeClient(metadata={GAP_CHECK_PATH_KEY: "checks/always_fails.py"})
    monkeypatch.setattr(_gap_closure, "make_beads_client", lambda **_kwargs: client)

    decision = evaluate_gap_closure(
        config=cast("Any", None), project_root=tmp_path, item_id="bd-ib-gap1"
    )
    assert decision.verdict == "refuse-check-failed"


def test_evaluate_refuses_when_negative_control_is_not_discriminating(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A check that always passes (even in --negative-control mode) proves nothing."""
    _init_git_repo(repo_root=tmp_path)
    check_path = tmp_path / "checks" / "vacuous_check.py"
    check_path.parent.mkdir(parents=True)
    check_path.write_text(_ALWAYS_PASSING_CHECK_SCRIPT, encoding="utf-8")

    client = _FakeClient(metadata={GAP_CHECK_PATH_KEY: "checks/vacuous_check.py"})
    monkeypatch.setattr(_gap_closure, "make_beads_client", lambda **_kwargs: client)

    decision = evaluate_gap_closure(
        config=cast("Any", None), project_root=tmp_path, item_id="bd-ib-gap1"
    )
    assert decision.verdict == "refuse-check-failed"
    assert "not discriminating" in decision.detail


def test_evaluate_forces_drift_when_check_file_modified_since_baseline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _init_git_repo(repo_root=tmp_path)
    check_path = tmp_path / "checks" / "example_check.py"
    check_path.parent.mkdir(parents=True)
    check_path.write_text(_CHECK_SCRIPT, encoding="utf-8")
    baseline_blob = subprocess.run(
        ["git", "hash-object", "checks/example_check.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    # Loosen the check after the baseline was recorded — the dangerous case.
    check_path.write_text(_ALWAYS_PASSING_CHECK_SCRIPT, encoding="utf-8")

    client = _FakeClient(
        metadata={
            GAP_CHECK_PATH_KEY: "checks/example_check.py",
            GAP_CHECK_BASELINE_BLOB_KEY: baseline_blob,
        },
    )
    monkeypatch.setattr(_gap_closure, "make_beads_client", lambda **_kwargs: client)

    decision = evaluate_gap_closure(
        config=cast("Any", None), project_root=tmp_path, item_id="bd-ib-gap1"
    )
    assert decision.verdict == "refuse-drift-required"


def test_evaluate_closes_when_check_modified_and_drift_propose_change_recorded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _init_git_repo(repo_root=tmp_path)
    check_path = tmp_path / "checks" / "example_check.py"
    check_path.parent.mkdir(parents=True)
    check_path.write_text(_CHECK_SCRIPT, encoding="utf-8")
    baseline_blob = subprocess.run(
        ["git", "hash-object", "checks/example_check.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    check_path.write_text(_CHECK_SCRIPT + "\n# retightened\n", encoding="utf-8")

    client = _FakeClient(
        metadata={
            GAP_CHECK_PATH_KEY: "checks/example_check.py",
            GAP_CHECK_BASELINE_BLOB_KEY: baseline_blob,
            GAP_DRIFT_PROPOSE_CHANGE_KEY: "example-drift-topic",
        },
    )
    monkeypatch.setattr(_gap_closure, "make_beads_client", lambda **_kwargs: client)

    decision = evaluate_gap_closure(
        config=cast("Any", None), project_root=tmp_path, item_id="bd-ib-gap1"
    )
    assert decision.verdict == "close"


def test_record_gap_check_writes_path_and_baseline_blob(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _init_git_repo(repo_root=tmp_path)
    check_path = tmp_path / "checks" / "example_check.py"
    check_path.parent.mkdir(parents=True)
    check_path.write_text(_CHECK_SCRIPT, encoding="utf-8")

    client = _FakeClient(metadata={})
    monkeypatch.setattr(_gap_closure, "make_beads_client", lambda **_kwargs: client)

    record_gap_check(
        config=cast("Any", None),
        project_root=tmp_path,
        item_id="bd-ib-gap1",
        check_path="checks/example_check.py",
    )

    assert client.updated_metadata is not None
    assert client.updated_metadata[GAP_CHECK_PATH_KEY] == "checks/example_check.py"
    assert GAP_CHECK_BASELINE_BLOB_KEY in client.updated_metadata


def test_record_gap_check_omits_baseline_blob_when_git_hash_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A recorded path that git cannot hash (e.g. it does not exist) still records the path."""
    _init_git_repo(repo_root=tmp_path)

    client = _FakeClient(metadata={})
    monkeypatch.setattr(_gap_closure, "make_beads_client", lambda **_kwargs: client)

    record_gap_check(
        config=cast("Any", None),
        project_root=tmp_path,
        item_id="bd-ib-gap1",
        check_path="checks/does_not_exist.py",
    )

    assert client.updated_metadata is not None
    assert client.updated_metadata[GAP_CHECK_PATH_KEY] == "checks/does_not_exist.py"
    assert GAP_CHECK_BASELINE_BLOB_KEY not in client.updated_metadata


def test_record_drift_propose_change_writes_topic(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeClient(metadata={GAP_CHECK_PATH_KEY: "checks/example_check.py"})
    monkeypatch.setattr(_gap_closure, "make_beads_client", lambda **_kwargs: client)

    record_drift_propose_change(
        config=cast("Any", None),
        item_id="bd-ib-gap1",
        propose_change_topic="example-drift-topic",
    )

    assert client.updated_metadata is not None
    assert client.updated_metadata[GAP_DRIFT_PROPOSE_CHANGE_KEY] == "example-drift-topic"
