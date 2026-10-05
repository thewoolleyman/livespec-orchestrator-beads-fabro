"""The opt-in leg of `codex-cred-status`, and the option that turns it on.

Ordinary status stays exactly what it was -- a read of the host credential's
lifetime and nothing else. The observation is reached only when an operator
names a state-file path, which is why the option carries the path rather than
defaulting to one: a status command that wrote somewhere by default would stop
being a read.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_identity_claims import (
    read_codex_identity_claims,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_identity_observation import (
    compare_codex_identity,
    identity_observation_payload,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_identity_state import (
    CodexIdentityStateRecord,
    read_prior_identity_state,
    write_identity_state,
)

__all__: list[str] = [
    "IDENTITY_OBSERVATION_OPTION",
    "IDENTITY_OBSERVATION_PAYLOAD_KEY",
    "add_codex_cred_status_arguments",
    "identity_observation_for",
]

IDENTITY_OBSERVATION_OPTION = "--observe-identity-state"
IDENTITY_OBSERVATION_PAYLOAD_KEY = "identity_observation"


def add_codex_cred_status_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Declare `codex-cred-status`'s flags, including the observation opt-in."""
    _ = parser.add_argument("--json", dest="as_json", action="store_true")
    _ = parser.add_argument(
        IDENTITY_OBSERVATION_OPTION,
        dest="observe_identity_state",
        default=None,
        metavar="<path>",
        help=(
            "Record this reading's one-way credential identity fingerprints at "
            "<path> and report how they compare with the preceding reading. "
            "Omitted, status reads the host credential and writes nothing."
        ),
    )


def identity_observation_for(
    *,
    source_auth_json: str | None,
    state_path_argument: str | None,
    now_epoch: int,
) -> dict[str, Any] | None:
    """Observe the credential's identity, or None when the operator did not opt in.

    The option's own module decides what its ABSENCE means, so no caller has to
    remember that an unset option is a read-only status rather than a default
    path somewhere.
    """
    if state_path_argument is None:
        return None
    return _observe_codex_identity(
        source_auth_json=source_auth_json,
        state_path=Path(state_path_argument),
        now_epoch=now_epoch,
    )


def _observe_codex_identity(
    *,
    source_auth_json: str | None,
    state_path: Path,
    now_epoch: int,
) -> dict[str, Any]:
    prior = read_prior_identity_state(path=state_path)
    claims = read_codex_identity_claims(source_auth_json=source_auth_json)
    comparison = compare_codex_identity(claims=claims, prior=prior)
    write_detail = write_identity_state(
        path=state_path,
        record=CodexIdentityStateRecord(
            token_fingerprint=claims.token_fingerprint,
            expires_at_epoch=claims.expires_at_epoch,
            observed_at_epoch=now_epoch,
        ),
    )
    return identity_observation_payload(
        claims=claims,
        comparison=comparison,
        state_path=str(state_path),
        state_write_detail=write_detail,
    )
