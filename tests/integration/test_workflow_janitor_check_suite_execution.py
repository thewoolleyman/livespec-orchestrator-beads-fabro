"""The janitor executes its declared check-suite across Fabro renderers.

The pinned engine substitutes workflow inputs as raw text, while the Petri-era
attractor frontend shell-quotes each interpolated input.  These tests render
the shipped janitor script both ways and execute that script through Bash, so
the compatibility claim is measured at the command boundary where the two
engines previously diverged.

EVERY CASE NOW PROVISIONS A PLUGINS ROOT, because the node re-enters the
materialized plugin-cache gate before it runs the suite (bd-ib-3f79). That is
not this module's claim -- `test_check_suite_plugin_gate_reentry.py` owns the
re-entry -- but it is now a PRECONDITION of reaching the suite at all, and the
root has to be a fixture one: the gate reads `$HOME/.claude/plugins` by default,
so a case inheriting this process's environment would read, and repair, the
ENCLOSING factory run's own registry.

The script is read through `parse_dot_graph` rather than by regex for the same
change: the node's `script` now carries escaped double quotes, which a
`[^"]*` capture truncates at the first one -- silently, since the truncated
prefix is still a runnable fragment.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_cache_gate import (
    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR,
    plugin_cache_gate_script,
)

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
    graph = parse_dot_graph(text=_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script: str = graph.nodes["janitor"]["script"]
    return script


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


def _plugins_root(*, tmp_path: Path) -> Path:
    """A plugins root prepared by the gate's OWN prepare-step body.

    Running the shipped body rather than restating it is what makes the gate
    these cases satisfy the gate the Dispatcher ships. Nothing is registered, so
    the gate records an empty pin and exits 0 -- the sandbox-with-nothing-yet
    case its docstring names.
    """
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    installer = tmp_path / "install-plugin-gate.sh"
    _ = installer.write_text(plugin_cache_gate_script(), encoding="utf-8")
    _ = subprocess.run(
        ["bash", str(installer)],
        check=True,
        capture_output=True,
        text=True,
        env=_env(tmp_path=tmp_path, plugins_root=plugins_root),
    )
    return plugins_root


def _env(
    *, tmp_path: Path, plugins_root: Path, extra: dict[str, str] | None = None
) -> dict[str, str]:
    """The child environment, EXPLICIT rather than inherited.

    Built from nothing, so it withholds `COVERAGE_PROCESS_START` and
    `COV_CORE_*` by construction and no child self-instruments.
    """
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR: str(plugins_root),
        **(extra or {}),
    }


def _run(
    *,
    tmp_path: Path,
    check_suite: str,
    shell_quoted_input: bool,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    plugins_root = _plugins_root(tmp_path=tmp_path)
    return subprocess.run(
        [
            "bash",
            "-c",
            _rendered_script(check_suite=check_suite, shell_quoted_input=shell_quoted_input),
        ],
        check=False,
        capture_output=True,
        env=_env(tmp_path=tmp_path, plugins_root=plugins_root, extra=extra_env),
        text=True,
    )


def test_petri_shell_quoted_input_runs_the_declared_suite_with_arguments(*, tmp_path: Path) -> None:
    record = tmp_path / "arguments"
    suite = _check_suite(
        tmp_path=tmp_path,
        body='printf "%s\\n%s\\n" "$1" "$2" > "$JANITOR_ARGUMENT_RECORD"',
    )
    completed = _run(
        tmp_path=tmp_path,
        check_suite=f"{suite} alpha beta",
        shell_quoted_input=True,
        extra_env={"JANITOR_ARGUMENT_RECORD": str(record)},
    )

    assert completed.returncode == 0, completed.stderr
    assert record.read_text(encoding="utf-8") == "alpha\nbeta\n"


def test_raw_input_runs_the_declared_suite_with_arguments(*, tmp_path: Path) -> None:
    record = tmp_path / "arguments"
    suite = _check_suite(
        tmp_path=tmp_path,
        body='printf "%s\\n%s\\n" "$1" "$2" > "$JANITOR_ARGUMENT_RECORD"',
    )
    completed = _run(
        tmp_path=tmp_path,
        check_suite=f"{suite} alpha beta",
        shell_quoted_input=False,
        extra_env={"JANITOR_ARGUMENT_RECORD": str(record)},
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
        tmp_path=tmp_path,
        check_suite=f"{suite} 23",
        shell_quoted_input=shell_quoted_input,
    )

    assert completed.returncode == 23
