"""The janitor executes its declared check-suite across Fabro renderers.

The pinned engine substitutes workflow inputs as raw text, while the Petri-era
attractor frontend shell-quotes each interpolated input.  These tests render
the shipped janitor script both ways and execute that script through Bash, so
the compatibility claim is measured at the command boundary where the two
engines previously diverged.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)
_CHECK_SUITE_TOKEN = "{{ inputs.sandbox_check_suite }}"


def _janitor_script() -> str:
    text = _WORKFLOW.read_text(encoding="utf-8")
    node = re.search(r"^\s*janitor\s*\[(?P<body>.*?)^\s*\]", text, re.DOTALL | re.MULTILINE)
    assert node is not None
    script = re.search(r'^\s*script="(?P<value>[^"]*)"', node.group("body"), re.MULTILINE)
    assert script is not None
    return script.group("value")


def _rendered_script(*, check_suite: str, shell_quoted_input: bool) -> str:
    script = _janitor_script()
    assert script.count(_CHECK_SUITE_TOKEN) == 1
    replacement = shlex.quote(check_suite) if shell_quoted_input else check_suite
    return script.replace(_CHECK_SUITE_TOKEN, replacement)


def _check_suite(*, tmp_path: Path, body: str) -> Path:
    path = tmp_path / "declared-check-suite"
    path.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _run(
    *,
    check_suite: str,
    shell_quoted_input: bool,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            "-c",
            _rendered_script(check_suite=check_suite, shell_quoted_input=shell_quoted_input),
        ],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )


def test_petri_shell_quoted_input_runs_the_declared_suite_with_arguments(*, tmp_path: Path) -> None:
    record = tmp_path / "arguments"
    suite = _check_suite(
        tmp_path=tmp_path,
        body='printf "%s\\n%s\\n" "$1" "$2" > "$JANITOR_ARGUMENT_RECORD"',
    )
    env = {**os.environ, "JANITOR_ARGUMENT_RECORD": str(record)}

    completed = _run(
        check_suite=f"{suite} alpha beta",
        shell_quoted_input=True,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert record.read_text(encoding="utf-8") == "alpha\nbeta\n"


def test_raw_input_runs_the_declared_suite_with_arguments(*, tmp_path: Path) -> None:
    record = tmp_path / "arguments"
    suite = _check_suite(
        tmp_path=tmp_path,
        body='printf "%s\\n%s\\n" "$1" "$2" > "$JANITOR_ARGUMENT_RECORD"',
    )
    env = {**os.environ, "JANITOR_ARGUMENT_RECORD": str(record)}

    completed = _run(
        check_suite=f"{suite} alpha beta",
        shell_quoted_input=False,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert record.read_text(encoding="utf-8") == "alpha\nbeta\n"


@pytest.mark.parametrize("shell_quoted_input", [False, True])
def test_nonzero_suite_exit_status_fails_the_janitor(
    *,
    tmp_path: Path,
    shell_quoted_input: bool,
) -> None:
    suite = _check_suite(tmp_path=tmp_path, body='exit "$1"')

    completed = _run(
        check_suite=f"{suite} 23",
        shell_quoted_input=shell_quoted_input,
    )

    assert completed.returncode == 23
