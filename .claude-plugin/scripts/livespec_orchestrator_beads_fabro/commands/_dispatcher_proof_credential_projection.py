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
    MINTED_PROVISIONING,
    parse_proof_credentials,
    proof_credential_provisioning,
)

__all__: list[str] = [
    "proof_credentials_env_lines",
    "proof_credentials_overlay_env",
]


def proof_credentials_env_lines(*, block: Mapping[str, object], environ: Mapping[str, str]) -> str:
    """The overlay env lines projecting this repository's declared proof credentials."""
    parsed = parse_proof_credentials(block=block)
    if isinstance(parsed, str):
        return ""
    rendered: list[str] = []
    for credential in parsed:
        # A minted name is already projected by the overlay's own credential
        # table; a second TOML line under the same key would make the whole
        # overlay unparseable.
        if proof_credential_provisioning(credential=credential) == MINTED_PROVISIONING:
            continue
        value = environ.get(credential.name, "")
        if not value:
            continue
        rendered.append(f"{credential.name} = {json.dumps(value)}\n")
    return "".join(rendered)


def proof_credentials_overlay_env(*, repo: Path, environ: Mapping[str, str]) -> str:
    """One repository's declared proof credentials as overlay env lines.

    The entry point the overlay materializer calls. It exists so the
    repository-to-block resolution lives HERE, beside the parse that consumes it,
    rather than being a second thing the materializer has to know how to do -- the
    same shape `proof_store_env_lines` takes for the sibling projection.
    """
    return proof_credentials_env_lines(block=dispatcher_block(cwd=repo), environ=environ)
