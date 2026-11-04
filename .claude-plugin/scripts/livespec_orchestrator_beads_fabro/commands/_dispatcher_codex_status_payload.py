"""The ONE projection of a graded host Codex credential both surfaces render.

WHY THIS IS A MODULE AND NOT A HELPER IN EITHER COMMAND. `codex-cred-status`
and `codex-cred-refresh` both report the same graded credential -- the refresh
command reports it twice, before and after its bounded renewal request -- and
until this module existed each carried its own BYTE-IDENTICAL copy of the
projection and of the two small human formatters beside it. Two copies of one
renderer is the shape that drifts invisibly: both surfaces keep emitting a
well-formed payload, and only an operator comparing a status reading against a
renewal reading discovers they describe the same credential differently.

The duplication was retired when the requirement projection was added beside it
(the worker-credential-projection clause requires the two surfaces to report
the same figure), because a THIRD pair of copies would have been the point at
which the convention stopped being maintainable.

PURE, with no argparse and no credential read: both commands resolve the graded
status themselves and hand it here, so every field is assertable without a
filesystem.

WHY `expires_at_iso` IS DERIVED HERE RATHER THAN CARRIED. The grade carries the
epoch, which is what every comparison uses; the ISO rendering exists for the
human reading the payload. Deriving it beside the epoch is what keeps the two
from disagreeing about which instant they describe.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_refresh import (
    HostCodexCredentialStatus,
)

__all__: list[str] = [
    "codex_cred_status_payload",
    "human_bool",
    "human_optional",
]

_SECONDS_PER_DAY = 86_400


def codex_cred_status_payload(*, status: HostCodexCredentialStatus) -> dict[str, Any]:
    """Project one graded host Codex credential for an operator surface's payload."""
    expires_at_iso = (
        None
        if status.expires_at_epoch is None
        else datetime.fromtimestamp(status.expires_at_epoch, tz=timezone.utc).isoformat()
    )
    remaining_days = (
        None if status.remaining_seconds is None else status.remaining_seconds / _SECONDS_PER_DAY
    )
    return {
        "alarm": status.alarm,
        "expires_at_epoch": status.expires_at_epoch,
        "expires_at_iso": expires_at_iso,
        "malformed": status.malformed,
        "message": status.message,
        "present": status.present,
        "refresh_due": status.refresh_due,
        "remaining_days": remaining_days,
        "remaining_seconds": status.remaining_seconds,
    }


def human_bool(*, value: object) -> str:
    """`true` only for the boolean itself, so a truthy non-boolean reads false.

    `is True` rather than a truthiness test, because these payloads carry
    tri-state fields whose absent arm is `None`: a truthiness test renders both
    `False` and `None` as `false`, which is right, and would render any
    non-empty placeholder as `true`, which is not.
    """
    return "true" if value is True else "false"


def human_optional(*, value: object) -> str:
    """`null` for an absent reading, so an unmeasured field is not rendered as one."""
    return "null" if value is None else str(value)
