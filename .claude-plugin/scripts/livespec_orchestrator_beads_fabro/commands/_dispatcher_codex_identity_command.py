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
    CodexIdentityClaims,
    read_codex_identity_claims,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_identity_observation import (
    IdentityStateWrite,
    compare_codex_identity,
    identity_observation_payload,
    refused_destination_comparison,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_identity_state import (
    CodexIdentityStateRecord,
    identity_state_collision,
    read_prior_identity_state,
    write_identity_state,
)

__all__: list[str] = [
    "IDENTITY_OBSERVATION_OPTION",
    "IDENTITY_OBSERVATION_PAYLOAD_KEY",
    "add_codex_cred_status_arguments",
    "add_credential_selection_arguments",
    "identity_observation_for",
]

IDENTITY_OBSERVATION_OPTION = "--observe-identity-state"
IDENTITY_OBSERVATION_PAYLOAD_KEY = "identity_observation"


def add_credential_selection_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Declare the selection context the credential requirement is resolved FOR.

    Shared by `codex-cred-status` and `codex-cred-refresh` so the two cannot
    offer different ways to name the same selection. Both default to the
    selection an ordinary dispatch makes, so an operator who passes neither flag
    gets the reading they got before these existed.
    """
    _ = parser.add_argument(
        "--workflow",
        dest="workflow",
        default=None,
        metavar="<path>",
        help=(
            "Resolve the credential requirement for the committed workflow at "
            "this explicit path, which outranks --workflow-name exactly as it "
            "does for `dispatch`. Declaring it also removes the argparse prefix "
            "abbreviation that previously read `--workflow <path>` as "
            "`--workflow-name <path>` and refused the path as an unregistered "
            "variant."
        ),
    )
    _ = parser.add_argument(
        "--workflow-name",
        dest="workflow_name",
        default=None,
        metavar="<variant>",
        help=(
            "Resolve the credential requirement for this registered workflow "
            "variant instead of the reserved one, so the figure matches the "
            "dispatch being predicted. An unregistered name is refused rather "
            "than sized off the reserved graph."
        ),
    )
    _ = parser.add_argument(
        "--review-fix-cap",
        dest="review_fix_cap",
        default=None,
        type=int,
        metavar="<n>",
        help=(
            "Resolve against this EFFECTIVE review-fix cap — what a per-item "
            "`review-fix-cap:<n>` label renders — instead of the repository "
            "default, which under-reports the floor for a labelled item."
        ),
    )


def add_codex_cred_status_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Declare `codex-cred-status`'s flags, including the observation opt-in."""
    _ = parser.add_argument("--json", dest="as_json", action="store_true")
    add_credential_selection_arguments(parser=parser)
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
    source_auth_path: Path,
    state_path_argument: str | None,
    now_epoch: int,
) -> dict[str, Any] | None:
    """Observe the credential's identity, or None when the operator did not opt in.

    The option's own module decides what its ABSENCE means, so no caller has to
    remember that an unset option is a read-only status rather than a default
    path somewhere.

    `source_auth_path` is the credential's ACTUAL resolved location, threaded in
    from the read boundary rather than reconstructed here. It is what the
    destination is checked against, and nothing in `source_auth_json` could
    substitute: the credential's own contents do not say where it lives, so a
    path inferred from them would be a guess standing between an operator's typo
    and an unrecoverable credential.
    """
    if state_path_argument is None:
        return None
    return _observe_codex_identity(
        source_auth_json=source_auth_json,
        source_auth_path=source_auth_path,
        state_path=Path(state_path_argument),
        now_epoch=now_epoch,
    )


def _observe_codex_identity(
    *,
    source_auth_json: str | None,
    source_auth_path: Path,
    state_path: Path,
    now_epoch: int,
) -> dict[str, Any]:
    claims = read_codex_identity_claims(source_auth_json=source_auth_json)
    collision = identity_state_collision(
        state_path=state_path,
        protected_path=source_auth_path,
    )
    if collision is not None:
        # BEFORE the prior-state read, not merely before the write. Reading the
        # credential as though it were a prior observation is meaningless, and
        # the refusal must not depend on the write being reached -- that is the
        # path the destroyed-credential defect took.
        return identity_observation_payload(
            claims=claims,
            comparison=refused_destination_comparison(detail=_refusal(collision=collision)),
            state_path=str(state_path),
            write=IdentityStateWrite(outcome="refused", detail=_refusal(collision=collision)),
        )
    prior = read_prior_identity_state(path=state_path)
    comparison = compare_codex_identity(claims=claims, prior=prior)
    return identity_observation_payload(
        claims=claims,
        comparison=comparison,
        state_path=str(state_path),
        write=_record_reading(claims=claims, state_path=state_path, now_epoch=now_epoch),
    )


def _refusal(*, collision: str) -> str:
    return (
        f"No observation was recorded and nothing was read: {collision}. "
        "Recording observation state there would overwrite the credential the "
        "host is the sole owner of. Name a host-private path that is not the "
        "credential file."
    )


def _record_reading(
    *,
    claims: CodexIdentityClaims,
    state_path: Path,
    now_epoch: int,
) -> IdentityStateWrite:
    """Remember this reading, unless remembering it would destroy the series.

    A reading with no identifiers to remember is WITHHELD rather than written.
    Recording it would overwrite the last fingerprints that could be compared,
    so one momentarily unreadable credential -- codex mid-login, the file
    briefly gone -- would leave every later reading comparing against the blip
    and reporting `unknown` from then on. The payload still reports the reading
    itself as unreadable; what is preserved is the question it can be put to.
    """
    if not claims.readable:
        return IdentityStateWrite(
            outcome="withheld",
            detail=(
                "This reading was not recorded: the credential's identity claims "
                "were unreadable, and recording that would discard the preceding "
                "observation this reading is compared against."
            ),
        )
    detail = write_identity_state(
        path=state_path,
        record=CodexIdentityStateRecord(
            session_fingerprint=claims.session_fingerprint,
            token_fingerprint=claims.token_fingerprint,
            expires_at_epoch=claims.expires_at_epoch,
            observed_at_epoch=now_epoch,
        ),
    )
    if detail is None:
        return IdentityStateWrite(outcome="recorded", detail=None)
    return IdentityStateWrite(outcome="failed", detail=detail)
