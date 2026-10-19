"""The append-only dispatch journal, and the attribution stamp it owns.

Split out of `_dispatcher_io` for the same reason `_dispatcher_shell_runner` was:
that module aggregates everything the Dispatcher does to the outside world, and
its import closure reaches the watched Fabro launcher — which reaches the
factory-ledger resolution. A module that writes the journal and ALSO resolves a
dispatch factory therefore closes an import cycle, and the overflow-selection
record is exactly such a writer. `_dispatcher_io` still RE-EXPORTS both names,
so every existing caller is untouched; only a module inside the launcher's own
import reach needs to import this leaf directly.

The cut is along a real seam rather than at a convenient line. An append-only
JSONL file with an unforgeable per-record attribution stamp shares nothing with
a subprocess runner but the fact that both leave the process, and keeping the
stamp beside the only append that applies it is what makes the refusal below
checkable in one screen.

WHY THE STAMP REFUSES A CALLER-SUPPLIED IDENTITY. The stamped-once guarantee IS
the attribution: a writer that could supply `invoker` could attribute its own
record to anyone, so a record carrying either field is a BUG rather than an
expected error and the append raises instead of overwriting it.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    InvokerIdentity,
    default_invoker_identity,
)

__all__: list[str] = [
    "JournalFile",
    "utc_now_iso",
]

# The two envelope fields the append layer stamps, and which therefore no
# caller may supply. Named once so the stamp and the refusal cannot drift.
_STAMPED_INVOKER_FIELDS: tuple[str, ...] = (
    "invoker",
    "invoker_source",
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
