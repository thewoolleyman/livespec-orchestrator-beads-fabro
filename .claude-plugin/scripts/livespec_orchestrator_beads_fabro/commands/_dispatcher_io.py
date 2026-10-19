"""Side-effect seams for the Dispatcher: subprocess runner + journal.

`ShellCommandRunner` is the production `CommandRunner` and now lives in
`_dispatcher_shell_runner`, re-exported here because almost every caller
reaches for it through this facade. It moved to break an import cycle the
whole-run wall budget's export chain closed back onto this module: this
module is both a DEFINITION site and a FACADE, so anything
`WatchedFabroLauncher` below reaches that needed the runner imported this
facade back while it was still initializing. A module INSIDE the
launcher's own import reach must therefore import the LEAF directly —
`_dispatcher_preserve_reference` is the one that does — and that module's
docstring carries the mechanism. The hermetic test tier exercises the
runner with `sys.executable -c` stubs, mirroring how `test_orchestrator`
drives the injected reference CLIs.

`WatchedFabroLauncher` is the production `FabroLauncher`: it runs `fabro
run` in a BACKGROUND thread (through the injected `CommandRunner`, which
blocks in the thread) while the FOREGROUND samples the run's liveness via
`fabro ps`/`fabro events` and `fabro rm -f`-es a confirmed sustained
stall (the coarse wall-clock progress watchdog, work-item
livespec-impl-beads-oyg — the 7us.6 silent-deadlock backstop). Like
`ShellCommandRunner` it is a production seam the hermetic unit tier does
NOT execute: the engine's stall branch is driven by injecting a fake
`FabroLauncher`, and the watchdog DECISION logic is unit-tested directly
in `_dispatcher_watchdog`. No test launches a real fabro run.

`JournalFile` is the structured iteration journal the Dispatcher
guidance requires (livespec non-functional-requirements.md):
append-only JSONL, one
record per engine stage / loop event, machine-readable for post-hoc
audit. Appends are lock-serialized so parallel dispatch threads cannot
interleave lines.

It is also THE APPEND LAYER of the journal invoker attribution contract in
`SPECIFICATION/contracts.md`: every record it writes is stamped with `invoker`
and `invoker_source` ONCE, here, and a record whose caller already supplied
either field is refused as a programming error. Stamping in one place is
what makes the attribution unforgeable — a writer that could stamp its own
identity could assert any identity, one caller at a time. The refusal is
the enforcement of that: it fails loudly at the seam rather than silently
preferring one of two disagreeing values. EVERY journal write MUST route
through `append`; opening the journal path directly is forbidden, and
`tests/test_journal_append_chokepoint.py` is the mechanical control that
proves no code does.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from livespec_runtime.github_auth.errors import GithubAppAuthError

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    InvokerIdentity,
    default_invoker_identity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io_fabro_launcher import (
    WatchedFabroLauncher,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import (
    ShellCommandRunner,
    child_env,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "GITHUB_TOKEN_ENV_VAR",
    "GithubTokenEnvRunner",
    "JournalFile",
    "ShellCommandRunner",
    "WatchedFabroLauncher",
    "child_env",
    "utc_now_iso",
]

# The env var name `gh` (and the `gh auth git-credential` helper raw `git`
# uses) reads its token from; the run-config overlay projects the SAME name
# into the sandbox env table. A NAME, never a secret value.
GITHUB_TOKEN_ENV_VAR = "GH_TOKEN"  # noqa: S105 - env-var NAME, not a secret value

# The two envelope fields the append layer stamps, and which therefore no
# caller may supply. Named once so the stamp and the refusal cannot drift.
_STAMPED_INVOKER_FIELDS: tuple[str, ...] = (
    "invoker",
    "invoker_source",
)


@dataclass(frozen=True, kw_only=True)
class GithubTokenEnvRunner:
    """CommandRunner decorator: refresh GH_TOKEN before EVERY command."""

    inner: CommandRunner
    token: Callable[[], str]

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        token = attempt(action=self.token, exceptions=(GithubAppAuthError,))
        if isinstance(token, AttemptFailure):
            exc = cast("GithubAppAuthError", token.error)
            return CommandResult(
                exit_code=1,
                stdout="",
                stderr=f"GitHub App token refresh failed (fail-closed): {exc.detail}",
            )
        os.environ[GITHUB_TOKEN_ENV_VAR] = token
        merged_env: dict[str, str | None] = {
            **(env or {}),
            GITHUB_TOKEN_ENV_VAR: os.environ[GITHUB_TOKEN_ENV_VAR],
        }
        if stdin is None:
            return self.inner.run(
                argv=argv,
                cwd=cwd,
                timeout_seconds=timeout_seconds,
                env=merged_env,
            )
        return self.inner.run(
            argv=argv,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            env=merged_env,
            stdin=stdin,
        )


@dataclass(frozen=True, kw_only=True)
class JournalFile:
    """Append-only JSONL journal; thread-safe across parallel dispatches."""

    path: Path
    identity: InvokerIdentity = field(default_factory=default_invoker_identity)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def append(self, *, record: dict[str, object]) -> None:
        """Stamp `at` + the resolved invoker onto `record` and append it.

        A caller that supplies `invoker` or `invoker_source` itself is a BUG,
        not an expected error: the stamped-once guarantee is exactly what makes
        the attribution unforgeable, so the append refuses rather than letting
        one writer assert an identity of its own choosing.
        """
        forged = [name for name in _STAMPED_INVOKER_FIELDS if name in record]
        if forged:
            msg = (
                "journal record supplied stamped invoker field(s) "
                f"{', '.join(forged)}; the append layer stamps them once and "
                "no writer may supply them"
            )
            raise ValueError(msg)
        stamped: dict[str, object] = {
            "at": utc_now_iso(),
            "invoker": self.identity.invoker,
            "invoker_source": self.identity.invoker_source,
            **record,
        }
        line = json.dumps(stamped, sort_keys=True) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                _ = handle.write(line)


def utc_now_iso() -> str:
    """Current UTC time in ISO-8601 with seconds precision."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
