"""The stable host identity a dispatch claim is stamped with.

Only the host named on a claim's stamp may recover that claim, because no
reconciler can observe another host's processes — so this value is the fence
the whole recovery sits inside, and it has to be STABLE across the processes
of one host rather than merely unique per process. The kernel's hostname is
that value: every dispatcher process on one machine reads the same string,
and two machines in this fleet never read the same one.

IT IS OVERRIDABLE BY ENVIRONMENT, and the override exists for the container
case rather than for convenience. A dispatcher running inside the
orchestrator image reads the CONTAINER's hostname, which changes per
container, so two dispatches from the same physical host would stamp two
identities and neither could recover the other's claim. `LIVESPEC_DISPATCHING_
HOST` is how such a deployment declares the one identity its dispatchers
share. It is read here and nowhere else, so there is exactly one answer per
process.

AN UNREADABLE HOSTNAME IS NAMED RATHER THAN GUESSED. `_UNKNOWN_HOST` compares
EQUAL to itself, so two processes that both failed to read a hostname would
each recover the other's claims — which is why the grading treats a stamp
carrying it as naming no dispatching host at all, and holds the claim as
`owner-elsewhere`. The constant is public for exactly that reading.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Mapping

from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "DISPATCHING_HOST_ENV_VAR",
    "UNKNOWN_DISPATCHING_HOST",
    "dispatching_host",
]

DISPATCHING_HOST_ENV_VAR = "LIVESPEC_DISPATCHING_HOST"

# What a host whose own name could not be read is stamped with. NOT a usable
# identity: the grading reads it as naming no host, so such a claim is held.
UNKNOWN_DISPATCHING_HOST = "unknown-dispatching-host"


def dispatching_host(*, env: Mapping[str, str] | None = None) -> str:
    """This process's stable host identity, for stamping onto a dispatch claim."""
    environment = os.environ if env is None else env
    declared = environment.get(DISPATCHING_HOST_ENV_VAR)
    if declared is not None and declared.strip() != "":
        return declared.strip()
    read = attempt(action=socket.gethostname, exceptions=(OSError,))
    if isinstance(read, AttemptFailure) or read.strip() == "":
        return UNKNOWN_DISPATCHING_HOST
    return read.strip()
