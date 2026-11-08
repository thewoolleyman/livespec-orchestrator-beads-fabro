"""Materialize the non-mutating commit-gate preview used by Red and Green turns."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import (
    PAYLOAD_ENV_VAR,
    PrepareStep,
    payload_write_command,
    render_prepare_step,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)

__all__: list[str] = [
    "GATE_PREVIEW_PROGRAM_FILENAME",
    "gate_preview_prepare_steps_block",
    "gate_preview_program_path_expansion",
    "gate_preview_program_source",
]

GATE_PREVIEW_PROGRAM_FILENAME = "livespec-implement-gate-preview.py"

_PROGRAM_SOURCE = r'''#!/usr/bin/env python3
"""Preview a Red or Green command-node commit without touching its repository state."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FAILED_TARGETS_HEADER = re.compile(r"^Failed targets \(\d+\):\s*$", re.MULTILINE)
FAILED_TARGET_LINE = re.compile(r"^\s+-\s+(\S+)\s*$")
SKIP_VARIABLE = re.compile(r"^LIVESPEC_.*(?:_SKIP|_RELAX|_DISABLE)(?:_|$)")


def command(*argv, cwd, env=None, check=True):
    result = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    if check and result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return result


def git(*argv, cwd):
    return command("git", *argv, cwd=cwd)


def changed_paths(root):
    tracked = git("diff", "--name-only", "--no-renames", "HEAD", cwd=root).stdout.splitlines()
    untracked = git("ls-files", "--others", "--exclude-standard", cwd=root).stdout.splitlines()
    return sorted(set(tracked + untracked))


def selected_paths(stage, root, test_file):
    if stage == "red":
        return [test_file]
    return changed_paths(root)


def copy_path(path, root, preview):
    source, target = root / path, preview / path
    if source.exists() or source.is_symlink():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target, follow_symlinks=False)
    elif target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
    else:
        target.unlink(missing_ok=True)


def failed_targets(output):
    header = FAILED_TARGETS_HEADER.search(output)
    if header is None:
        return []
    targets = []
    for line in output[header.end() :].splitlines()[1:]:
        match = FAILED_TARGET_LINE.match(line)
        if match is None:
            break
        targets.append(match.group(1))
    return targets


def skipped_environment():
    names = sorted(
        name
        for name in os.environ
        if name == "LIVESPEC_CHECK_SKIP" or SKIP_VARIABLE.match(name)
    )
    environment = os.environ.copy()
    for name in names:
        environment.pop(name, None)
    return environment, names


def preview(stage, test_file):
    root = Path(git("rev-parse", "--show-toplevel", cwd=Path.cwd()).stdout.strip())
    paths = selected_paths(stage, root, test_file)
    if not paths:
        return 2, [], []
    preview_root = Path(tempfile.mkdtemp(prefix="livespec-gate-preview-"))
    try:
        git("worktree", "add", "--detach", "--quiet", str(preview_root), "HEAD", cwd=root)
        for path in paths:
            copy_path(path, root, preview_root)
        git("add", "--all", "--", *paths, cwd=preview_root)
        hook_path = git(
            "rev-parse", "--git-path", "hooks/pre-commit", cwd=preview_root
        ).stdout.strip()
        hook = Path(hook_path)
        if not hook.is_file():
            return 0, [], []
        environment, unset = skipped_environment()
        result = command(str(hook), cwd=preview_root, env=environment, check=False)
        output = result.stdout + result.stderr
        sys.stdout.write(output)
        return result.returncode, failed_targets(output), unset
    finally:
        command("git", "worktree", "remove", "--force", str(preview_root), cwd=root, check=False)
        shutil.rmtree(preview_root, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("red", "green"))
    parser.add_argument("test_file", nargs="?")
    args = parser.parse_args()
    if (args.stage == "red") != (args.test_file is not None):
        parser.error("red requires the test file path commit_red will stage; green takes none")
    status, targets, unset = preview(args.stage, args.test_file)
    print(
        json.dumps(
            {"status": status, "failed_targets": targets, "unset_variables": unset},
            sort_keys=True,
        )
    )
    return status


if __name__ == "__main__":
    raise SystemExit(main())
'''


def gate_preview_program_source() -> str:
    """Return the exact stdlib-only program the sandbox executes."""
    return _PROGRAM_SOURCE


def gate_preview_program_path_expansion() -> str:
    """Return the sandbox-local preview path shared by the overlay and prompts."""
    return f"{sandbox_plugins_root_expansion()}/{GATE_PREVIEW_PROGRAM_FILENAME}"


def gate_preview_prepare_steps_block() -> str:
    """Render the prepare step that writes the preview beside the commit runner."""
    root = sandbox_plugins_root_expansion()
    path = gate_preview_program_path_expansion()
    step = PrepareStep(
        script=(
            f'set -eu\nmkdir -p "{root}"\n'
            + payload_write_command(path_word=f'"{path}"')
            + f'\nchmod 755 "{path}"'
        ),
        env={PAYLOAD_ENV_VAR: gate_preview_program_source()},
    )
    return (
        "\n# --- Dispatcher-materialized implement gate preview (bd-ib-cwnt3b) ---\n"
        + render_prepare_step(step=step)
    )
