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
    """Run the wrapped guard command unless the project manifest is conflicted."""
    manifest = Path(os.environ[_PROJECT_DIR_ENV_VAR]) / _MANIFEST_NAME
    wrapped = sys.argv[1:]
    if _carries_conflict_markers(path=manifest):
        _ = sys.stderr.write(_skip_notice(manifest=manifest, wrapped=wrapped) + "\n")
        return 0
    return subprocess.run(args=wrapped, check=False).returncode


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
    """True iff the manifest holds an unresolved merge-conflict marker."""
    text = path.read_text(encoding="utf-8", errors="replace")
    return any(line.startswith(_CONFLICT_MARKER_PREFIXES) for line in text.splitlines())


if __name__ == "__main__":
    raise SystemExit(main())
