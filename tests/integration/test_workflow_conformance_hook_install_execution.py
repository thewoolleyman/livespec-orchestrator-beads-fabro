"""Every refresh-time conformance installer executes its resolved argv.

The Fabro renderer shell-quotes node-script inputs.  A multi-word installer
therefore arrives as one shell argument, which must be parsed back into its
declared argv before it is executed.  This test reads the shipped workflow
sources, renders the exact installer form the renderer supplies, and uses a
``uv`` stand-in to observe installation of all three hook bodies.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOWS = (
    _REPO_ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro",
    _REPO_ROOT / ".fabro/workflows/groom-work-item/workflow.fabro",
)
_TOKEN = "{{ inputs.conformance_hook_install }}"
_INSTALLER = "uv run python -m livespec_dev_tooling.install_commit_refuse_hooks"
_INSTALLER_FORM = (
    'set -- {{ inputs.conformance_hook_install }}; if test \\"$#\\" -eq 1; '
    'then eval \\"set -- $1\\"; fi; test $# -eq 0 || \\"$@\\"'
)
_FAIL_CLOSED_SUFFIX = (
    '; installer_status=$?; if test \\"$installer_status\\" -ne 0; then echo '
    '\\"LIVESPEC_CONFORMANCE_HOOK_INSTALL_FAILED: the resolved conformance hook '
    'installer failed after refresh with exit status $installer_status\\" >&2; exit \\"$installer_status\\"; fi'
)


def _installer(*, root: Path, exit_status: int) -> Path:
    """Create the stand-in for the declared multi-word hook installer."""
    path = root / "bin" / "uv"
    path.parent.mkdir(parents=True)
    path.write_text(
        "#!/bin/sh\n"
        'test "$1" = run\n'
        'test "$2" = python\n'
        'test "$3" = -m\n'
        'test "$4" = livespec_dev_tooling.install_commit_refuse_hooks\n'
        "for hook in pre-commit pre-push commit-msg; do\n"
        "    printf '%s\\n' canonical > .git/hooks/$hook\n"
        f"done\nexit {exit_status}\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path.parent


def _rendered_installer_sites() -> list[str]:
    """Read all nine shipped refresh-time installer sites from their sources."""
    return [
        site
        for workflow in _WORKFLOWS
        for site in re.findall(
            re.escape(_INSTALLER_FORM) + "(?:" + re.escape(_FAIL_CLOSED_SUFFIX) + ")?",
            workflow.read_text(encoding="utf-8"),
        )
    ]


def test_every_refresh_installer_executes_the_shell_quoted_multi_word_command(
    *, tmp_path: Path
) -> None:
    """Every site executes the installer and propagates a failed install's status."""
    forms = _rendered_installer_sites()

    assert len(forms) == 9
    assert all(form.endswith(_FAIL_CLOSED_SUFFIX) for form in forms)

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    bin_dir = _installer(root=tmp_path, exit_status=0)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}

    for form in forms:
        rendered = form.replace(r"\"", '"').replace(_TOKEN, shlex.quote(_INSTALLER))
        result = subprocess.run(
            ["sh", "-c", rendered],
            check=False,
            cwd=repo,
            env=env,
            text=True,
            capture_output=True,
        )

        assert result.returncode == 0, result.stderr
        for hook in ("pre-commit", "pre-push", "commit-msg"):
            assert (repo / ".git" / "hooks" / hook).read_text(encoding="utf-8") == "canonical\n"

    failing_bin_dir = _installer(root=tmp_path / "failing", exit_status=41)
    failing_env = {**os.environ, "PATH": f"{failing_bin_dir}:{os.environ['PATH']}"}
    for form in forms:
        rendered = form.replace(r"\"", '"').replace(_TOKEN, shlex.quote(_INSTALLER))
        result = subprocess.run(
            ["sh", "-c", rendered],
            check=False,
            cwd=repo,
            env=failing_env,
            text=True,
            capture_output=True,
        )

        assert result.returncode == 41, result.stderr
        assert "LIVESPEC_CONFORMANCE_HOOK_INSTALL_FAILED" in result.stderr
        assert "exit status 41" in result.stderr
