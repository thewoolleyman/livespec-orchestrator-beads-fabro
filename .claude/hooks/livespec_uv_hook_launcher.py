"""livespec uv hook launcher — the manifest-safe front door for a uv-started hook.

Claude Code treats a PreToolUse hook's exit status 2 as a blocking refusal, and
`uv run` exits 2 BEFORE the interpreter starts when it cannot parse the
project's `pyproject.toml`. A manifest left carrying unresolved merge-conflict
markers therefore turns every uv-launched guard registered in
`.claude/settings.json` into a blanket refusal of `Write`, `Edit`, `MultiEdit`
and `Bash` — including the calls that would repair the conflict. Measured on
run 01M50Y9V7G55 (work-item `bd-ib-sufca7`): a `pr_refresh` rebase left markers
in `pyproject.toml` and the refresh-repair turn could not run a single tool, so
it could not touch the one file that was disabling it.

The refusal is the LAUNCHER's, not any guard's decision — the guard's own
fail-open boundary never runs, because `uv` refuses before Python starts. So
the remedy belongs in FRONT of `uv`: this module is spliced ahead of each
uv-started PreToolUse hook command, and stands that guard down for the one call
rather than letting `uv` refuse it.

WHY MERGE-CONFLICT MARKERS RATHER THAN A TOML PARSE. `tomllib` is standard
library only from 3.11 and this repository's floor is
`requires-python = ">=3.10.16"`, so the interpreter its own suite runs on
cannot import it; `tomli` is a dev dependency inside the project virtualenv,
which is exactly what is unreachable while the manifest is broken. The
condition that was measured, and the one the ratified scenario names in its
Given, is an unresolved merge-conflict marker — and no valid TOML document
carries one at the start of a line, so the markers themselves are the detector.

Exits 0 whenever it stands a guard down, and otherwise exits with the wrapped
command's own status, so a guard that refuses still refuses.

THE TWO FAIL DIRECTIONS ARE ASYMMETRIC, as they are in the guards themselves.
A manifest this module cannot READ fails toward the GUARD: it is launched and
decides as usual, because standing a guard down on every unrelated filesystem
fault would trade a loud wedge for a silent loss of enforcement. The hook
BOUNDARY fails open, because trouble inside this module must never reach
Claude Code as the one status it reads as a deny.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

__all__: list[str] = ["main"]

_PROJECT_DIR_ENV_VAR = "CLAUDE_PROJECT_DIR"
_MANIFEST_NAME = "pyproject.toml"
_CONFLICT_MARKER_PREFIXES = ("<<<<<<<", ">>>>>>>")


def main() -> int:
    """Read the wrapped guard command off argv and run it, or stand it down."""
    try:
        return _launch(wrapped=sys.argv[1:], environ=dict(os.environ))
    # The BOUNDARY is fail-open: an exit status 2 out of this module would be
    # read as a deny, which is the very failure it exists to remove.
    except Exception:  # noqa: BLE001 — sole fail-open hook boundary: silent pass-through, exit 0
        return 0


def _launch(*, wrapped: list[str], environ: dict[str, str]) -> int:
    """Delegate to the wrapped guard unless the project manifest is conflicted."""
    manifest = _manifest_path(environ=environ)
    if _carries_conflict_markers(path=manifest):
        _ = sys.stderr.write(_skip_notice(manifest=manifest, wrapped=wrapped) + "\n")
        return 0
    return subprocess.run(args=wrapped, check=False).returncode


def _manifest_path(*, environ: dict[str, str]) -> Path:
    """Resolve the governed repository's manifest.

    Claude Code exports the project directory to every hook; the working
    directory is the fallback rather than a refusal, because a launcher that
    cannot locate the manifest must still let the guard decide.
    """
    declared = environ.get(_PROJECT_DIR_ENV_VAR, "").strip()
    root = Path(declared) if declared else Path.cwd()
    return root / _MANIFEST_NAME


def _skip_notice(*, manifest: Path, wrapped: list[str]) -> str:
    """Render the one-line stand-down notice.

    One line, because this is written on a tool call an agent did not ask to
    be narrated; and it names BOTH the manifest and the guard, because the
    agent's remedy is to repair the one and its exposure is the loss of the
    other.
    """
    return (
        f"livespec uv hook launcher: {manifest} is unparseable — it carries unresolved "
        f"merge-conflict markers — so the guard `{shlex.join(wrapped)}` was skipped for "
        "this tool call."
    )


def _carries_conflict_markers(*, path: Path) -> bool:
    """True iff the manifest holds an unresolved merge-conflict marker.

    A manifest that cannot be read is NOT reported as conflicted: that arm
    fails toward the guard, which is launched and decides as it always did.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return any(line.startswith(_CONFLICT_MARKER_PREFIXES) for line in text.splitlines())


if __name__ == "__main__":
    raise SystemExit(main())
