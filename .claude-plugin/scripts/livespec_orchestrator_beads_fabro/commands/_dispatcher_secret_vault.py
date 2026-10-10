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

WHY ONE FACTORY LAUNCH IS A TRANSACTION. Vault names must stay stable so an
immutable workflow version survives credential rotation, but the server's vault
is global and each `secret set` writes only one name. A per-factory advisory
lock therefore begins before the first write and remains held until the worker
reports `running`. On the candidate engine that transition is recorded only
after the worker has loaded its vault and built the run's `VaultSecrets`
snapshot, so another local dispatch cannot interleave a mixed batch or replace
the first run's values before its snapshot exists. The lock is host-global, not
checkout-local: independent dispatcher clones on the operator host address the
same lock file when they address the same server.

The sink is separate from the ordinary `FabroPort` verbs because it is the only
one that handles a credential value and it is injected into the pure routing
layer.  Its direct CLI transport nevertheless belongs to the `_fabro_port*`
facade family, in `_fabro_port_secret`, so this module owns dispatch policy and
scrubbing without becoming a second route around the engine boundary.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

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
# WHY THE STORE IS RECORDED AT ALL. A stable reference proves which vault
# ENTRY the worker will read, but the bundle cannot prove whether this launch
# successfully put a value there. Only the dispatch-time store result can, so a
# names-only row records that operation without copying the credential onto a
# persisted surface.
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

# All dispatcher clones owned by this operator share this root. It deliberately
# does not live under a repository: the vault it protects is server-global, so a
# checkout-local lock would reproduce the race across two repositories or
# plugin sandboxes. The file is never unlinked -- unlinking while another caller
# waits on its inode can create two independently locked inodes for one factory.
_LAUNCH_LOCK_ROOT = Path.home() / ".cache" / "livespec" / "factory-vault-launch-locks"
_LOCK_FAILURE_EXIT_CODE = 1


@dataclass(kw_only=True)
class _FactoryVaultLaunchGuard:
    """One operator-host mutex spanning vault writes through worker snapshot."""

    server_url: str | None
    _handle: BinaryIO | None = field(default=None, init=False, repr=False)

    def acquire(self) -> str | None:
        """Take the factory lock once; a names-only failure, or None."""
        if self._handle is not None:
            return None
        descriptor: int | None = None
        handle: BinaryIO | None = None
        try:
            _LAUNCH_LOCK_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
            _LAUNCH_LOCK_ROOT.chmod(0o700)
            descriptor = os.open(str(self._path()), os.O_RDWR | os.O_CREAT, 0o600)
            os.fchmod(descriptor, 0o600)
            handle = os.fdopen(descriptor, "r+b")
            descriptor = None
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except OSError as exc:
            if handle is not None:
                handle.close()
            if descriptor is not None:
                os.close(descriptor)
            return f"factory vault launch lock could not be acquired ({type(exc).__name__}: {exc})"
        self._handle = handle
        return None

    def release(self) -> None:
        """Release the held transaction, idempotently."""
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def _path(self) -> Path:
        """A value-free stable filename for the factory server target."""
        target = "local" if self.server_url is None else self.server_url.rstrip("/")
        digest = hashlib.sha256(target.encode("utf-8")).hexdigest()
        return _LAUNCH_LOCK_ROOT / f"{digest}.lock"


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
    _launch_guard: _FactoryVaultLaunchGuard = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_launch_guard",
            _FactoryVaultLaunchGuard(server_url=self.server_url),
        )

    def set(self, *, secret: VaultSecret) -> str | None:
        """Store `secret`; a scrubbed message when the server would not take it."""
        lock_failure = self._launch_guard.acquire()
        if lock_failure is not None:
            self._record(
                secret=secret,
                outcome="refused",
                exit_code=_LOCK_FAILURE_EXIT_CODE,
            )
            return lock_failure
        result = self._store(secret=secret)
        if result.exit_code == 0:
            self._record(secret=secret, outcome="stored", exit_code=0)
            return None
        # Recorded as REFUSED rather than omitted. An absent row reads as "this
        # launch never tried", which is the wrong conclusion when the worker's
        # stable reference resolves an entry this store never refreshed.
        self._record(secret=secret, outcome="refused", exit_code=result.exit_code)
        self.release_launch_guard()
        return f"`fabro secret set {secret.secret_name}` exited {result.exit_code}: " + _excerpt(
            text=_scrubbed(text=result.stderr or result.stdout, value=secret.value)
        )

    def release_launch_guard(self) -> None:
        """Let the next same-factory dispatch refresh stable vault names."""
        self._launch_guard.release()

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
    """At most `_REJECTION_EXCERPT_CHARS` of an already-scrubbed message."""
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
