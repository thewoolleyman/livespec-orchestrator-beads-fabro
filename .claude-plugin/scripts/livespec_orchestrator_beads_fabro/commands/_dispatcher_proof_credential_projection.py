"""How an admitted proof-credential declaration reaches the sandbox.

The PROJECTION half of `SPECIFICATION/contracts.md`'s proof-credential-projection
clause (ratified v114), split from `_dispatcher_proof_credentials` by cohesion:
that module answers what a repository DECLARED and what refuses it, and this one
answers what an admitted declaration renders into the run-configuration overlay.

Rendered as inline values in the uncommitted, mode-600 run-configuration
overlay — the SAME channel that already carries the dispatch credential set,
rather than a second one. That transport is implementation-owned: the pinned
engine offers no secret-reference syntax, so a by-name reference the worker
could resolve does not exist yet, and a change of transport must not change the
declaration this reads.

FAIL-CLOSED ON EVERY DOUBT. A declaration the parse refuses renders NOTHING,
and a name whose value is absent is skipped rather than projected empty. The
pre-dispatch gate runs before this on every dispatch path, so neither arm should
be reachable in production; they are written this way because the opposite shape
— render whatever parses — would project a credential nobody admitted, and that
is the expensive direction to be wrong in.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credentials import (
    MINTED_PER_RUN_CREDENTIALS,
    resolved_proof_credentials,
)

__all__: list[str] = [
    "proof_credentials_env_lines",
    "proof_credentials_overlay_env",
]


def proof_credentials_env_lines(
    *,
    block: Mapping[str, object],
    environ: Mapping[str, str],
    minted: Mapping[str, str] | None = None,
) -> str:
    """The overlay env lines projecting this repository's declared proof credentials.

    WHERE EACH VALUE COMES FROM, which is the whole decision this function makes.
    A declaration whose provider exposes a management interface takes the value
    MINTED for this run, out of `minted`; every other declaration takes the
    wrapper-supplied value out of `environ`. A managed name therefore never
    projects the host's own credential even when the host happens to hold one
    under the same spelling, which is the point of minting per run.

    `minted` defaults to None rather than being required so a caller that cannot
    mint — a hermetic test, a repository declaring no provider — renders the
    copied projection unchanged.
    """
    resolved = resolved_proof_credentials(block=block)
    if isinstance(resolved, str):
        return ""
    minted_values: Mapping[str, str] = {} if minted is None else minted
    rendered: list[str] = []
    for credential in resolved.declared:
        # A name the DISPATCHER mints for itself is already projected by the
        # overlay's own credential table; a second TOML line under the same key
        # would make the whole overlay unparseable. Keyed on that set rather than
        # on the derived `minted` verdict, because a PROVIDER-minted name is
        # minted too and that one MUST render.
        if credential.name in MINTED_PER_RUN_CREDENTIALS:
            continue
        source = minted_values if credential.name in resolved.management else environ
        value = source.get(credential.name, "")
        if not value:
            continue
        rendered.append(f"{credential.name} = {json.dumps(value)}\n")
    return "".join(rendered)


def proof_credentials_overlay_env(
    *, repo: Path, environ: Mapping[str, str], minted: Mapping[str, str] | None = None
) -> str:
    """One repository's declared proof credentials as overlay env lines.

    The entry point the overlay materializer calls. It exists so the
    repository-to-block resolution lives HERE, beside the parse that consumes it,
    rather than being a second thing the materializer has to know how to do -- the
    same shape `proof_store_env_lines` takes for the sibling projection.
    """
    return proof_credentials_env_lines(
        block=dispatcher_block(cwd=repo), environ=environ, minted=minted
    )
