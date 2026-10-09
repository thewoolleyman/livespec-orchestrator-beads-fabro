"""Dispatch policy for handing a projected credential to a factory vault.

`_dispatcher_secret_channel` decides WHICH credentials travel as references and
rewrites the bundle; this module performs the other half of that transport --
storing each displaced value in the factory's own vault, so the reference the
worker resolves names an entry that exists.

WHY STANDARD INPUT RATHER THAN AN ARGUMENT. A `fabro secret set` call is a host
subprocess, and an argument is the most widely observable thing about one: it is
visible in the host process table to every user on the box for the life of the
call, it is what a command runner echoes into a log or a journal, and it is what
a timeout or file-not-found diagnostic quotes back verbatim. `--value-stdin`
exists precisely so the value need not be an argument, and the descriptor handed
to the child belongs to an UNLINKED temporary file -- it has no name in the
filesystem at any point, so there is no path for anything else to read, and no
cleanup that can be skipped.

WHY THE SERVER'S OWN MESSAGE IS SCRUBBED. A rejection text is untrusted here: it
may quote what it was sent. The dispatch that receives this refusal JOURNALS it,
so an echoing message would put the credential into the one record written
specifically to say the credential could not be stored. `contracts.md` section
"Proof credential projection" states the rule -- journals and records carry
names, never values -- and the scrub is how this surface keeps it even when the
server does not.

The sink is separate from the ordinary `FabroPort` verbs because it is the only
one that handles a credential value and it is injected into the pure routing
layer.  Its direct CLI transport nevertheless belongs to the `_fabro_port*`
facade family, in `_fabro_port_secret`, so this module owns dispatch policy and
scrubbing without becoming a second route around the engine boundary.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_channel import VaultSecret
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroPort,
    FabroTarget,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import (
    FabroCommand,
    FabroRunner,
)

__all__: list[str] = [
    "SECRET_SET_TIMEOUT_SECONDS",
    "VAULT_STORE_JOURNAL_STAGE",
    "FabroVaultSink",
    "fabro_vault_sink_for_plan",
]

# The dispatch-journal stage each store is recorded under.
#
# WHY THE STORE IS RECORDED AT ALL. The vault key is derived from the
# environment-variable name alone, so a rotated credential takes effect against
# the bundle already on the server and two launches render BYTE-IDENTICAL
# bundles. That invariance is the point -- a Petri-era server stores each
# workflow version immutably, so a transport needing a new bundle per rotation
# would make every credential refresh a redeploy -- but it also means the bundle
# cannot answer whether THIS launch re-wrote the vault. Only a record can, and
# without one a dispatch running on a stale credential looks exactly like one
# running on a fresh credential.
VAULT_STORE_JOURNAL_STAGE = "secret-channel-store"

# One `fabro secret set` round trip. Generous enough for a loopback-or-tailnet
# server under load, and short enough that an unreachable one refuses the
# dispatch rather than holding it: the store runs before the launch, so a hang
# here is a dispatch that never starts, not a run that never finishes.
SECRET_SET_TIMEOUT_SECONDS = 120.0

# How much of a rejection message is carried into the refusal. Bounded because
# the text is the SERVER's, not ours, and an unbounded body would put an
# arbitrary remote payload into a dispatch journal row.
_REJECTION_EXCERPT_CHARS = 400


@dataclass(frozen=True, kw_only=True)
class FabroVaultSink:
    """Stores one routed credential in a named factory's server-side vault."""

    fabro_bin: str
    server_url: str | None
    runner: FabroRunner
    cwd: Path
    timeout_seconds: float = SECRET_SET_TIMEOUT_SECONDS
    # Where each store is recorded. OPTIONAL because the sink is constructed in
    # places that have no journal to write to -- a hermetic test, a direct
    # caller -- and a record is evidence about a dispatch rather than part of
    # the store itself. The production dispatch path always supplies one.
    journal: JournalWriter | None = None

    def set(self, *, secret: VaultSecret) -> str | None:
        """Store `secret`; a scrubbed message when the server would not take it."""
        result = self._store(secret=secret)
        if result.exit_code == 0:
            self._record(secret=secret, outcome="stored", exit_code=0)
            return None
        # Recorded as REFUSED rather than omitted. An absent row reads as "this
        # launch never tried", which is the wrong conclusion in exactly the case
        # that matters: the vault still holds the previous launch's credential,
        # and the bundle gives no sign of it.
        self._record(secret=secret, outcome="refused", exit_code=result.exit_code)
        return f"`fabro secret set {secret.secret_name}` exited {result.exit_code}: " + _scrubbed(
            text=_excerpt(text=result.stderr or result.stdout), value=secret.value
        )

    def _record(self, *, secret: VaultSecret, outcome: str, exit_code: int) -> None:
        """Journal one store by NAME: the vault key, the env name, the outcome.

        No value and no server message: the contract requires journals to carry
        names only, and a journal row cannot be edited after it is appended.
        """
        if self.journal is None:
            return
        self.journal.append(
            record={
                "stage": VAULT_STORE_JOURNAL_STAGE,
                "secret": secret.secret_name,
                "env": secret.env_name,
                "outcome": outcome,
                "exit_code": exit_code,
            }
        )

    def _store(self, *, secret: VaultSecret) -> FabroCommand:
        """Run the store with the value on an unlinked temporary file's descriptor."""
        with tempfile.TemporaryFile() as handle:
            _ = handle.write(secret.value.encode("utf-8"))
            _ = handle.seek(0)
            port = FabroPort(
                fabro_bin=self.fabro_bin,
                target=FabroTarget(server_url=self.server_url),
                runner=self.runner,
                cwd=self.cwd,
            )
            return port.secret_set(
                secret_name=secret.secret_name,
                stdin=handle.fileno(),
                timeout_seconds=self.timeout_seconds,
            )


def fabro_vault_sink_for_plan(
    *, plan: Any, runner: FabroRunner, journal: JournalWriter | None = None
) -> FabroVaultSink:
    """Build the sink from a dispatch plan's ALREADY-RESOLVED factory target.

    Read off the plan rather than re-resolved from configuration, for the same
    reason every other factory-addressed seam is: the plan's factory is what the
    dispatch record journaled and what `fabro run` is pointed at, and a second
    resolution here could store a credential in one server's vault while the run
    launched against another's.
    """
    return FabroVaultSink(
        fabro_bin=plan.fabro_bin,
        server_url=plan.fabro_factory_server,
        runner=runner,
        cwd=plan.repo,
        journal=journal,
    )


def _excerpt(*, text: str) -> str:
    """At most `_REJECTION_EXCERPT_CHARS` of the server's own message."""
    stripped = text.strip()
    return stripped[:_REJECTION_EXCERPT_CHARS]


def _scrubbed(*, text: str, value: str) -> str:
    """The message with every occurrence of the value replaced by a marker.

    An EMPTY value is left alone rather than replaced: `str.replace` with an
    empty needle inserts the marker between every character, which would turn a
    readable server message into noise while protecting nothing.
    """
    if value == "":
        return text
    return text.replace(value, "<value withheld>")
