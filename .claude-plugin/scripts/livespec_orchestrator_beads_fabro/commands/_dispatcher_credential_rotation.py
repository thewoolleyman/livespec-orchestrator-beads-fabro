"""Re-resolving the projected worker credential, and naming it without printing it.

The loop's bounded credential re-probe used to assess `os.environ` — the value
the credential wrapper injected when the loop was LAUNCHED. That makes the wait
unretirable by the one event it exists to wait for: a rotation lands in the
wrapper, the parked process never reads the wrapper again, and the loop probes a
dead credential until its budget or a human ends it. Measured 2026-10-08 on this
host, four dispatch loops kept journaling `exhausted` from 08:54Z and 11:42Z
through 23:10Z while other repositories' dispatches started running on the same
factory minutes after the maintainer rotated the credential.

This module is the re-resolution, plus the non-secret IDENTITY a refused-probe
record carries so two consecutive rows show whether the value changed at all.

THE CHILD'S INHERITED CREDENTIAL IS EMPTIED, AND THAT IS THE LOAD-BEARING PART.
The wrapper this fleet runs caches, in the invoker's keyring, the DIFF between
its caller's environment and what it injected, and replays that diff to every
caller until the entry times out (`AGENTS.md`, the wrapper-cache entry, measured
2026-10-01). A NESTED invocation that already holds the credential therefore
produces a near-empty diff, which fails in both directions at once: this reading
sees the stale value it started with, and the near-empty diff is stored where
every other caller on the host then reads it. Emptying the name for the child is
what makes the diff genuine, so the re-resolution observes the rotation and
leaves the shared cache carrying real values.

IT NEVER REPORTS AN ABSENT CREDENTIAL. A wrapper that exits non-zero, or exits
zero having injected nothing, yields the LAUNCH-TIME value with `rotatable`
False rather than the empty string. The two have opposite remedies — an absent
credential is a misconfigured wrapper to fix, while a provider-limited one is a
wait to leave running — so reporting a wrapper fault as an absent credential
would retire the wait with a refusal about the wrong thing. What stops a
PERSISTENT fault is the wait's own bound on consecutive unresolvable rounds, not
a verdict manufactured here.

THE IDENTITY IS ONE-WAY BECAUSE THE QUESTION IS ONLY EVER ONE OF EQUALITY. The
journal is asked whether this round's credential differs from the last round's,
which a truncated domain-separated digest answers exactly as well as the value
does, while being useless to anyone who reads the journal. The empty token
fingerprints to None rather than to the digest of the empty string, because
"no credential was resolved" and "this credential was resolved" are different
facts and a reader comparing two rows must not see them as one changed value.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_wrapper import (
    read_dispatch_target_credential_wrapper,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = [
    "CREDENTIAL_ROTATION_TIMEOUT_SECONDS",
    "LAUNCH_ENVIRONMENT_NO_WRAPPER",
    "LAUNCH_ENVIRONMENT_WRAPPER_UNRESOLVABLE",
    "WRAPPER_RESOLVED",
    "RotatedCredential",
    "credential_identity",
    "resolve_rotated_credential",
]

# Domain separation, so a digest recorded here cannot be matched against a
# digest of the same value taken anywhere else.
_IDENTITY_DOMAIN = "livespec-worker-credential/v1"
# 32 hex characters is 128 bits — far past any collision that could make two
# genuinely different credentials read as one unchanged observation.
_IDENTITY_HEX_LENGTH = 32

# The ceiling on one re-resolution. The wrapper re-execs through `sudo` and
# resolves secrets from a remote vault, so it is a network round trip an
# operator does not control; bounded because an unbounded one would hold the
# wait open past its own cadence with nothing to show for it.
CREDENTIAL_ROTATION_TIMEOUT_SECONDS = 60.0

# The command the wrapper is asked to run. `printenv` prints exactly the one
# variable and exits non-zero when it is unset, which is the whole reading — a
# shell would add a parse surface for no answer it could give.
_PRINTENV = "printenv"

# The three non-secret labels a refused-probe record carries, so an operator
# reading two rows can tell a wait that is watching the wrapper from one that
# has nothing to watch.
WRAPPER_RESOLVED = "credential-wrapper"
LAUNCH_ENVIRONMENT_NO_WRAPPER = "launch-environment-no-wrapper-declared"
LAUNCH_ENVIRONMENT_WRAPPER_UNRESOLVABLE = "launch-environment-wrapper-unresolvable"


@dataclass(frozen=True, kw_only=True)
class RotatedCredential:
    """One round's reading of the credential the dispatch would project.

    `rotatable` is the fact the wait acts on: True means this value came from a
    fresh wrapper re-resolution, so a rotation landing in the wrapper will reach
    the next round. False means the reading fell back to the launch-time value,
    which cannot change while the process lives — so a wait held on it can never
    be retired by a rotation, however long it runs.
    """

    token: str
    rotatable: bool
    source: str


def credential_identity(*, token: str) -> str | None:
    """The one-way identity a journal row names this credential by, or None if absent."""
    if token == "":
        return None
    material = f"{_IDENTITY_DOMAIN}:{token}".encode()
    return hashlib.sha256(material).hexdigest()[:_IDENTITY_HEX_LENGTH]


def resolve_rotated_credential(
    *,
    repo: Path,
    env_name: str,
    launch_token: str,
    runner: CommandRunner,
) -> RotatedCredential:
    """Ask the target's declared credential wrapper for `env_name` as it stands now.

    Spawns nothing when the target declares no wrapper: there is no second
    source for the value, so the only honest reading is the launch-time one and
    a subprocess would cost a `sudo` re-exec per round to learn nothing.
    """
    wrapper = read_dispatch_target_credential_wrapper(repo=repo)
    if not wrapper:
        return RotatedCredential(
            token=launch_token,
            rotatable=False,
            source=LAUNCH_ENVIRONMENT_NO_WRAPPER,
        )
    result = runner.run(
        argv=[*wrapper, _PRINTENV, env_name],
        cwd=repo,
        timeout_seconds=CREDENTIAL_ROTATION_TIMEOUT_SECONDS,
        env={env_name: ""},
    )
    resolved = result.stdout.strip()
    if result.exit_code != 0 or resolved == "":
        return RotatedCredential(
            token=launch_token,
            rotatable=False,
            source=LAUNCH_ENVIRONMENT_WRAPPER_UNRESOLVABLE,
        )
    return RotatedCredential(token=resolved, rotatable=True, source=WRAPPER_RESOLVED)
