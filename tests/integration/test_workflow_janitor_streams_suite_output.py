"""The janitor's stage output carries the check suite's lines while the suite still runs.

The janitor used to hold the suite's whole output in a shell variable and print
it only after the suite returned, so a visit killed by its node timeout lost every
line the suite had printed (measured 2026-11-08 on livespec-dev-tooling-h5sifx
run 01M6X5HVCGAB visits 1 to 3 and livespec-dev-tooling-4pchid run
01M6X4NQE2CC visit 3). These cases execute the shipped janitor script through
Bash against a stand-in suite, so the claim is measured at the command boundary.

The refresh repair brief's `failed-gate-targets` for a non-zero suite is bound by
`test_workflow_refresh_repair_brief_target_output.py`, which executes this same
node; it stays the owner of that clause.
"""

from __future__ import annotations

import functools
import os
import signal
import subprocess
import threading
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_cache_gate import (
    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR,
)

from tests.prepare_step_support import plugin_gate_installer_script

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
_DEFAULT_BRANCH_TOKEN = "{{ inputs.default_branch }}"
_CONFORMANCE_HOOK_INSTALL_TOKEN = "{{ inputs.conformance_hook_install }}"
_SUITE_LINE = "suite-line-printed-before-the-kill"
_WAIT_SECONDS = 8.0


def _janitor_script(*, check_suite: str) -> str:
    graph = parse_dot_graph(text=_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script: str = graph.nodes["janitor"]["script"]
    return (
        script.replace(_DEFAULT_BRANCH_TOKEN, "master")
        .replace(_CHECK_SUITE_TOKEN, check_suite)
        .replace(_CONFORMANCE_HOOK_INSTALL_TOKEN, "")
    )


def _suite(*, tmp_path: Path, body: str) -> Path:
    path = tmp_path / "declared-check-suite"
    _ = path.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _environment(*, tmp_path: Path) -> dict[str, str]:
    """A plugins root prepared by the gate's own prepare-step body, and a stub git."""
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    bin_dir = plugins_root / "bin"
    bin_dir.mkdir()
    git = bin_dir / "git"
    _ = git.write_text(
        "#!/usr/bin/env bash\n"
        "set -eu\n"
        'case "${1:-}" in\n'
        "  fetch|rebase) exit 0 ;;\n"
        "  rev-parse)\n"
        "    if test \"${2:-}\" = --git-path; then printf '%s\\n' \"$PWD/.git/${3:?}\"; else printf '%s\\n' test-head; fi ;;\n"
        "  *) printf 'unexpected git argv: %s\\n' \"$*\" >&2; exit 1 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    git.chmod(0o755)
    environment = {
        "PATH": f"{bin_dir}:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR: str(plugins_root),
    }
    installer = tmp_path / "install-plugin-gate.sh"
    _ = installer.write_text(plugin_gate_installer_script(), encoding="utf-8")
    _ = subprocess.run(
        ["bash", str(installer)],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return environment


def test_a_line_the_suite_printed_is_in_the_stage_output_when_the_stage_is_killed(
    *, tmp_path: Path
) -> None:
    suite = _suite(tmp_path=tmp_path, body=f"printf '%s\\n' {_SUITE_LINE}\nsleep 60")
    process = subprocess.Popen(
        ["bash", "-c", _janitor_script(check_suite=str(suite))],
        cwd=tmp_path,
        env=_environment(tmp_path=tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )
    # The read below blocks on the janitor's own stdout, so which lines run never
    # depends on timing. The timer is only a liveness ceiling: a janitor that holds
    # the suite's output until the suite returns would block here for the suite's
    # 60 seconds, so the ceiling kills the group, the read returns empty, and the
    # assertion fails.
    ceiling = threading.Timer(
        _WAIT_SECONDS, functools.partial(os.killpg, process.pid, signal.SIGKILL)
    )
    ceiling.start()
    assert process.stdout is not None
    first_line = process.stdout.readline()
    ceiling.cancel()
    os.killpg(process.pid, signal.SIGKILL)
    _ = process.wait()
    process.stdout.close()

    assert _SUITE_LINE in first_line


def test_a_zero_exit_stage_output_carries_each_suite_line_once(*, tmp_path: Path) -> None:
    suite = _suite(tmp_path=tmp_path, body=f"printf '%s\\n' {_SUITE_LINE}")

    completed = subprocess.run(
        ["bash", "-c", _janitor_script(check_suite=str(suite))],
        cwd=tmp_path,
        env=_environment(tmp_path=tmp_path),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.count(_SUITE_LINE) == 1
