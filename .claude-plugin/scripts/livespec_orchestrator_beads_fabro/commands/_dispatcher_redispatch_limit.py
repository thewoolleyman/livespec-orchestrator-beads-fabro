"""Resolve the committed across-dispatch no-progress limit.

`dispatcher.redispatch_no_progress_limit` is one of the quantitative limits of
`SPECIFICATION/contracts.md` section "Quantitative plan-progress limits": a
positive committed integer with NO inferred default and no per-item override.
Every other `dispatcher.*` integer resolves an absent key to its documented
default; this one cannot, because an implicit count would let the admission
guard refuse (or admit) on a number nobody chose.  An absent or invalid value
is therefore a configuration diagnostic that the admission gate reports before
any claim.
"""

from __future__ import annotations

from pathlib import Path

from returns.io import IOResult
from returns.result import Failure, Result, Success

from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    PolicySettingUnreadable,
    read_dispatcher_config_value,
)

__all__: list[str] = ["resolve_redispatch_no_progress_limit"]

_KEY = "redispatch_no_progress_limit"


def resolve_redispatch_no_progress_limit(*, cwd: Path) -> IOResult[int, PolicySettingUnreadable]:
    """Read the committed limit, failing when it is missing or not a positive integer."""
    return read_dispatcher_config_value(cwd=cwd, key=_KEY).bind_result(
        lambda value: _positive_integer(value=value)
    )


def _positive_integer(*, value: object) -> Result[int, PolicySettingUnreadable]:
    if value is None:
        return Failure(_diagnostic(why="is not committed; it has no implicit default"))
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return Success(value)
    return Failure(
        _diagnostic(why=f"must be a positive committed integer, not a boolean; got {value!r}")
    )


def _diagnostic(*, why: str) -> PolicySettingUnreadable:
    return PolicySettingUnreadable(
        setting=_KEY, detail=f"dispatcher.{_KEY} {why} (a committed positive integer)"
    )
