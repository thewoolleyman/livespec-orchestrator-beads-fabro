"""Fail-open SessionStart warning when a registered plugin install lags release."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

__all__: list[str] = ["main", "registered_build_warning"]

_CHECK_TIMEOUT_SECONDS = 10.0


def registered_build_warning(*, plugin_root: Path, project: Path) -> str:
    """Run the bundled warning command and return its optional warning text."""
    completed = subprocess.run(
        [
            sys.executable,
            str(plugin_root / "scripts" / "bin" / "registered_plugin_currency.py"),
            "--repo",
            str(project),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=_CHECK_TIMEOUT_SECONDS,
    )
    return completed.stdout.strip()


def main() -> int:
    """Print a non-blocking currency warning when Claude starts the session."""
    if os.environ.get("CODEX_THREAD_ID"):
        return 0
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    if not plugin_root or not project:
        return 0
    try:
        warning = registered_build_warning(plugin_root=Path(plugin_root), project=Path(project))
    except (OSError, subprocess.TimeoutExpired):
        return 0
    if warning:
        _ = sys.stderr.write(warning + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
