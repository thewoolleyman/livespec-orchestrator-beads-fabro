"""Resolving ONE admission evaluation's session-headroom policy.

`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance": "The floor is a committed-only
`dispatcher.session_headroom_floor_percent` (integer from 0 through 100
inclusive, default 20) ... It is NOT declared API-configurable, and is
therefore committed-only", and "One assessment per distinct projected
credential per admission evaluation MUST be reused across nodes and candidates
sharing that credential."

THE MEMO LIVES HERE, IN THE POLICY, AND NOT IN THE FILTER. The filter runs once
per NODE against one `PreflightInputs`, so a memo threaded through it would
have to be a caller-owned dictionary every call site remembered to share. A
policy built once per admission evaluation carries the "at most once" guarantee
as a property of the value instead -- and two concurrent evaluations cannot
share one another's reading, because each built its own policy. That is the
same isolation the probe's explicit memo buys, obtained from the value's
lifetime rather than from a convention.

THE CREDENTIAL IS READ AT READ TIME, NOT AT BUILD TIME. The clause asks for the
"exact credential snapshot that the dispatch would project", and the projection
reads the environment, so taking the snapshot when the first candidate actually
needs it is what keeps the two readings of one variable from diverging. It also
means an evaluation that assesses NO covered candidate issues no request at all.

AN UNREADABLE FLOOR RESOLVES TO THE RATIFIED DEFAULT, exactly as the re-probe
cadence does, and that direction is chosen rather than incidental: the default
IS the specification's value, so a malformed dial falls back onto the behaviour
the clause ratifies rather than onto a disabled filter. The refusal is still
available to a caller that wants to report the malformed dial --
`resolve_session_headroom_floor_percent` returns it -- which is why the two are
separate functions.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from returns.io import IOResult
from returns.result import Failure, Result, Success
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    DEFAULT_SESSION_HEADROOM_FLOOR_PERCENT,
    SessionHeadroomPolicy,
    SessionHeadroomReading,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    PolicySettingUnreadable,
    read_dispatcher_config_value,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_session_headroom_io import (
    read_projected_session_headroom,
)

__all__: list[str] = [
    "SESSION_HEADROOM_FLOOR_PERCENT_KEY",
    "resolve_session_headroom_floor_percent",
    "session_headroom_policy",
]

SESSION_HEADROOM_FLOOR_PERCENT_KEY = "session_headroom_floor_percent"

_FLOOR_MINIMUM = 0
_FLOOR_MAXIMUM = 100


def resolve_session_headroom_floor_percent(*, cwd: Path) -> IOResult[int, PolicySettingUnreadable]:
    """Read the committed floor, bounded to the clause's inclusive 0..100 range.

    The generic integer resolver in `_dispatcher_policy_settings` carries a
    minimum and no maximum, and this dial needs both: a floor above 100 is not
    a strict dial, it is one no reading can ever satisfy, so it would refuse
    every covered candidate in the repository forever.
    """
    return read_dispatcher_config_value(
        cwd=cwd, key=SESSION_HEADROOM_FLOOR_PERCENT_KEY
    ).bind_result(lambda value: _floor_value(value=value))


def session_headroom_policy(
    *,
    repo: Path,
    now_iso: str,
    read: Callable[..., SessionHeadroomReading] = read_projected_session_headroom,
) -> SessionHeadroomPolicy:
    """This evaluation's floor plus its at-most-once reading of the projection."""
    floor = unsafe_perform_io(
        resolve_session_headroom_floor_percent(cwd=repo).value_or(
            DEFAULT_SESSION_HEADROOM_FLOOR_PERCENT
        )
    )
    taken: list[SessionHeadroomReading] = []

    def read_once() -> SessionHeadroomReading:
        if not taken:
            taken.append(read(token=os.environ.get(CLAUDE_OAUTH_TOKEN_ENV), observed_at=now_iso))
        return taken[0]

    return SessionHeadroomPolicy(floor_percent=floor, read=read_once)


def _floor_value(*, value: object) -> Result[int, PolicySettingUnreadable]:
    """The declared floor, or the refusal naming the range it fell outside."""
    if value is None:
        return Success(DEFAULT_SESSION_HEADROOM_FLOOR_PERCENT)
    if (
        isinstance(value, int)
        and not isinstance(value, bool)
        and _FLOOR_MINIMUM <= value <= _FLOOR_MAXIMUM
    ):
        return Success(value)
    return Failure(
        PolicySettingUnreadable(
            setting=SESSION_HEADROOM_FLOOR_PERCENT_KEY,
            detail=(
                f"dispatcher.{SESSION_HEADROOM_FLOOR_PERCENT_KEY} must be an integer from "
                f"{_FLOOR_MINIMUM} through {_FLOOR_MAXIMUM} inclusive; got {value!r}"
            ),
        )
    )
