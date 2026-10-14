"""What the configured credential wrapper injects RIGHT NOW, and its identity.

Split from `_dispatcher_credential_env` by cohesion. That module asks whether
THIS PROCESS's environment carries a usable credential -- a question whose
answer was settled when the process started, because the wrapper injected the
value once and nothing has re-read it since. This one asks the question a
PARKED loop actually needs answered: what does the dispatch target's committed
`credential_wrapper` inject today, and is that the same value as last round.

The distinction is the whole defect. Measured 2026-10-08 on this host, four
dispatch loops parked on `credential-reprobe-refused` from 08:54Z and 11:42Z
re-probed every 300 seconds and were still journaling `exhausted` at 23:10Z,
after the Claude credential had been rotated at roughly 23:00Z and other
repositories' dispatches had resumed on the same factory within minutes. Every
one of those probes re-read the launch-time environment, so the rotation could
not reach them and all four had to be stopped and re-dispatched by hand.

THE CREDENTIAL NAME IS REMOVED FROM THE CHILD'S ENVIRONMENT, and that is a
correctness requirement rather than hygiene. The wrapper this fleet uses
computes the DIFF between its caller's environment and the environment it
injects; a caller that already holds the credential therefore produces a
near-empty diff and reads its own stale value straight back. That is the
nested-caller shape `AGENTS.md` records under the wrapper's cache trap, and
removing the selected name is what makes the wrapper's own value the one that
arrives.

NO VALUE EVER LEAVES THIS PROCESS. The token rides one bounded child's standard
output and is handed to the probe; what the journal records is
`credential_identity`, a one-way truncated domain-separated digest, because the
only question anyone asks of it is whether two consecutive readings are EQUAL
-- which a digest answers exactly as well as the value does while being useless
to a reader of the audit journal. The value is never an argv element, never a
log line and never a journal field.

THE INVOCATION IS BOUNDED BY A FINITE TIMEOUT. A wrapper that never returns
would otherwise convert a bounded wait into the hang this module exists to
retire, so the one process boundary carries its own deadline and reports an
unreadable wrapper as no value rather than waiting on it.

A WRAPPER THAT SUPPLIES NOTHING FALLS BACK TO THE LAUNCH-TIME VALUE, and that
direction is deliberate. The value this process already holds is the one a
dispatch would project, so carrying it forward leaves a target that declares no
wrapper at all — and a target whose wrapper is momentarily unavailable —
behaving exactly as it did before any of this existed. Treating an unreadable
wrapper as an ABSENT credential instead would end a legitimate wait on one
transient hiccup, and `_dispatcher_credential_reprobe` is what keeps the
fallback from becoming a hang: the wait is bounded by the budget it was handed,
so a wrapper that never recovers runs that budget out and returns.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_wrapper import (
    read_dispatch_target_credential_wrapper,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    select_factory_credential,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "ENVIRONMENT_SOURCE",
    "WRAPPER_READ_TIMEOUT_SECONDS",
    "WRAPPER_SOURCE",
    "CredentialReading",
    "credential_identity",
    "read_wrapper_credential",
    "resolve_credential_reading",
    "selected_credential_env_name",
]

# Domain separation, so a digest recorded here cannot be matched against a
# digest of the same value taken anywhere else in the fleet.
_IDENTITY_DOMAIN = "livespec-dispatch-credential/v1"
# 16 hex characters is 64 bits, far past any collision that could make two
# genuinely different credentials read as one unchanged value across a round.
_IDENTITY_HEX_LENGTH = 16

# The deadline on the ONE wrapper invocation a round makes. Generous enough for
# a real secret-manager round trip, finite because an unbounded one would hand
# a misconfigured wrapper the power to hang the wait.
WRAPPER_READ_TIMEOUT_SECONDS = 30

# Where a reading's value came from. Named rather than inlined because the
# journal records it: an operator comparing two consecutive rows needs to know
# whether the identity they hold is the wrapper's current answer or the
# launch-time value carried forward, and those two have different remedies.
WRAPPER_SOURCE: Literal["wrapper"] = "wrapper"
ENVIRONMENT_SOURCE: Literal["environment"] = "environment"

_CredentialSource = Literal["wrapper", "environment"]


@dataclass(frozen=True, kw_only=True)
class CredentialReading:
    """The credential value this round will probe, with its non-secret identity.

    `token` is the VALUE and never leaves the process. `identity` is the
    one-way fingerprint the journal records; it is a digest unconditionally,
    including for an absent credential, because the comparison across two rows
    has to stay meaningful in every state and the row's own `condition` is what
    says whether there was a credential there at all.
    """

    token: str
    source: _CredentialSource
    identity: str


def credential_identity(*, token: str) -> str:
    """Return the one-way fingerprint two consecutive readings are compared by."""
    material = f"{_IDENTITY_DOMAIN}:{token}".encode()
    return hashlib.sha256(material).hexdigest()[:_IDENTITY_HEX_LENGTH]


def selected_credential_env_name() -> str:
    """The env-var NAME this host's dispatch credential currently lives under.

    The same selection the dispatch path's own assessment makes, through the
    same published-profile record, so the value re-read here is the value a
    dispatch would project rather than a neighbouring pool slot.
    """
    return select_factory_credential(
        environ=os.environ,
        home=Path.home(),
        warn=lambda message: sys.stderr.write(f"livespec-dispatch: {message}\n"),
    ).env_name


def read_wrapper_credential(  # pragma: no cover - the one process boundary
    *,
    wrapper: tuple[str, ...],
    env_name: str,
    environ: Mapping[str, str],
) -> str:
    """Invoke the configured wrapper once and read the named value back.

    Returns the empty string for every reading that did not arrive -- an
    undeclared wrapper (there is no command to invoke), one that could not be
    executed, one that exceeded `WRAPPER_READ_TIMEOUT_SECONDS`, and one that
    exited non-zero. The four are deliberately one answer here: each of them
    means this round has no wrapper-supplied value, and the remedy for all of
    them is the same declaration to fix.
    """
    if not wrapper:
        return ""
    completed = attempt(
        action=lambda: subprocess.run(  # noqa: S603 - committed declaration, never a shell
            [*wrapper, "printenv", env_name],
            capture_output=True,
            text=True,
            check=False,
            timeout=WRAPPER_READ_TIMEOUT_SECONDS,
            # The selected name is REMOVED so the wrapper's own injected value
            # is what arrives; see this module's docstring.
            env={name: value for name, value in environ.items() if name != env_name},
        ),
        exceptions=(OSError, subprocess.SubprocessError),
    )
    if isinstance(completed, AttemptFailure) or completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def resolve_credential_reading(
    *,
    repo: Path,
    env_name: str,
    environ: Mapping[str, str],
) -> CredentialReading:
    """Re-resolve the dispatch credential through the target's committed wrapper.

    `read_wrapper_credential` is resolved through THIS module's namespace, so a
    caller standing the invocation in stands in the one every round uses. A
    wrapper that supplied nothing yields the launch-time value instead, under
    the environment source, for the reason this module's docstring gives.
    """
    injected = read_wrapper_credential(
        wrapper=read_dispatch_target_credential_wrapper(repo=repo),
        env_name=env_name,
        environ=environ,
    )
    if injected == "":
        return _reading(token=environ.get(env_name, ""), source=ENVIRONMENT_SOURCE)
    return _reading(token=injected, source=WRAPPER_SOURCE)


def _reading(*, token: str, source: _CredentialSource) -> CredentialReading:
    return CredentialReading(
        token=token,
        source=source,
        identity=credential_identity(token=token),
    )
