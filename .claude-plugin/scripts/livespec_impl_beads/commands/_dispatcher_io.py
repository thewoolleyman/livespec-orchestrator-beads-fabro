"""Side-effect seams for the Dispatcher: subprocess runner + journal.

`ShellCommandRunner` is the production `CommandRunner`: it executes the
engine's argvs via `subprocess.run` with captured output and converts
timeouts into non-zero `CommandResult`s (the engine treats every failure
as routable data, so the runner never lets an expected failure escape as
an exception). The hermetic test tier exercises it with
`sys.executable -c` stubs, mirroring how `test_orchestrator` drives the
injected reference CLIs.

`JournalFile` is the structured iteration journal the Dispatcher
guidance requires (livespec non-functional-requirements.md
§"Orchestrator-internal Dispatcher guidance"): append-only JSONL, one
record per engine stage / loop event, machine-readable for post-hoc
audit. Appends are lock-serialized so parallel dispatch threads cannot
interleave lines.
"""

from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from livespec_impl_beads.commands._dispatcher_engine import CommandResult

__all__: list[str] = [
    "JournalFile",
    "ShellCommandRunner",
    "utc_now_iso",
]


@dataclass(frozen=True, kw_only=True)
class ShellCommandRunner:
    """Production CommandRunner: subprocess.run with captured output."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
    ) -> CommandResult:
        try:
            completed = subprocess.run(  # noqa: S603 - argvs are Dispatcher-built, never shell
                argv,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                exit_code=124,
                stdout=_decode(raw=exc.stdout),
                stderr=_decode(raw=exc.stderr) + f"\ntimeout after {timeout_seconds}s",
            )
        return CommandResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


@dataclass(frozen=True, kw_only=True)
class JournalFile:
    """Append-only JSONL journal; thread-safe across parallel dispatches."""

    path: Path
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def append(self, *, record: dict[str, object]) -> None:
        stamped: dict[str, object] = {"at": utc_now_iso(), **record}
        line = json.dumps(stamped, sort_keys=True) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                _ = handle.write(line)


def utc_now_iso() -> str:
    """Current UTC time in ISO-8601 with seconds precision."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _decode(*, raw: object) -> str:
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        return raw
    return ""
