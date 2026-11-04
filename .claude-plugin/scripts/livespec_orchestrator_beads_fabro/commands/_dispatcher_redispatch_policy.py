"""The committed repetition limit the across-dispatch progress gate counts against.

`dispatcher.redispatch_no_progress_limit` is a quantitative limit with no
inferred default and no per-item override, so this reading answers either a
positive integer or the configuration diagnostic the refusal carries.  An
unreadable file is a diagnostic too: guessing a count would make the gate refuse
or admit on a number nobody committed.
"""

from __future__ import annotations

from pathlib import Path

from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    read_dispatcher_config_value,
)

__all__: list[str] = ["REDISPATCH_NO_PROGRESS_LIMIT_KEY", "redispatch_no_progress_limit"]

REDISPATCH_NO_PROGRESS_LIMIT_KEY = "redispatch_no_progress_limit"
_SETTING = f"dispatcher.{REDISPATCH_NO_PROGRESS_LIMIT_KEY}"


def redispatch_no_progress_limit(*, repo: Path) -> int | str:
    """The committed positive limit, or the diagnostic naming what is wrong with it."""
    read = read_dispatcher_config_value(cwd=repo, key=REDISPATCH_NO_PROGRESS_LIMIT_KEY)
    if not is_successful(read):
        failure = unsafe_perform_io(read.failure())
        return f"{_SETTING} could not be read: {failure.detail}"
    value = unsafe_perform_io(read.unwrap())
    if value is None:
        return f"{_SETTING} is not committed in .livespec.jsonc; set a positive integer"
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return f"{_SETTING} must be a positive integer (not a boolean), found {value!r}"
    return value
