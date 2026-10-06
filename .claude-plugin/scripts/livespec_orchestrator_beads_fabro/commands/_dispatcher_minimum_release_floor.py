"""The deliberate operator floor — the SOLE blocking currency form at admission.

Per the self-update contract in SPECIFICATION/contracts.md, the
dispatch-admission plugin-currency check MAY refuse fail-closed if and only if
the operator has committed a `dispatcher.minimum_release` floor in this repo's
`.livespec.jsonc` AND the executing release is below it. Absent that key the
check has no blocking authority over currency at all.

This module deliberately reports its verdict as PLAIN STRINGS rather than as the
gate's message dataclasses: the floor is a self-contained question ("is the
executing release below what a human required?") and keeping the gate's result
vocabulary out of it is what stops the two modules from importing each other.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from returns.pipeline import is_successful
from returns.result import Failure, Result, Success
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    executing_payload_root,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    PolicySettingUnreadable,
    read_dispatcher_config_value,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_self_update import (
    released_payload_version,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_self_update_decision import (
    release_below_floor,
)

__all__: list[str] = [
    "MinimumReleaseVerdict",
    "minimum_release_verdict",
    "resolve_minimum_release",
]

_MINIMUM_RELEASE_KEY = "minimum_release"
_UPDATE_REMEDY = (
    "claude plugin update livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"
)


@dataclass(frozen=True, kw_only=True)
class MinimumReleaseVerdict:
    """What a committed floor concluded. At most one detail is ever populated.

    A verdict with BOTH details empty is the floor CLEARED — the executing
    release meets it — which is why the caller must distinguish this from the
    `None` that means no floor is committed at all.
    """

    refusal_detail: str | None = None
    undetermined_detail: str | None = None


def resolve_minimum_release(*, cwd: Path) -> Result[str | None, PolicySettingUnreadable]:
    """Read the OPTIONAL `dispatcher.minimum_release` floor from `.livespec.jsonc`.

    A `None` on the success track is the ANSWER "no floor is committed", and it
    is load-bearing rather than incidental: absent this key the gate has NO
    blocking authority over currency. A present value is a released-version
    identifier such as `0.97.1` — a human-chosen floor for a release known to be
    safety-critical, never an ambient latest-release comparison.

    Deliberately NOT a member of the API-configurable key manifest, for the same
    reason `require_invoker` is not: a safety floor an automated surface could
    lower or delete is not a floor. It is editable only by a committed
    `.livespec.jsonc` change.
    """
    configured = read_dispatcher_config_value(cwd=cwd, key=_MINIMUM_RELEASE_KEY)
    if not is_successful(configured):
        return Failure(unsafe_perform_io(configured.failure()))
    return _minimum_release_value(value=unsafe_perform_io(configured.unwrap()))


def minimum_release_verdict(
    *, plugin_root: Path, cwd: Path, executing_payload: Path | None = None
) -> MinimumReleaseVerdict | None:
    """The floor's verdict, or `None` when the operator committed no floor.

    Every path that cannot COMPLETE the comparison yields an undetermined
    detail rather than a refusal or a silent pass, because the contract forbids
    both of the tempting shortcuts: an unobservable release must never fail open
    into a false refusal, nor be silenced into a satisfied floor.

    TWO ROOTS, two jobs, and they are not interchangeable. `executing_payload`
    is the tree whose release is JUDGED — the bytes actually running, which
    defaults to the retained payload because that is the only tree immutable
    for this invocation's lifetime. `plugin_root` is the INSTALLATION the
    operator must act on, and it is named in the refusal for exactly that.

    Judging through `plugin_root` is what this had to stop doing: the harness
    owns that path and may delete or overwrite it mid-run, so a newer build
    landing there satisfied the floor on the OLD build's behalf — a silent
    pass for exactly the build the operator committed the floor to stop. This
    is the one BLOCKING currency form in the contract, so it judges the bytes
    actually running and tells the operator which installation to update.
    """
    configured = resolve_minimum_release(cwd=cwd)
    if not is_successful(configured):
        return MinimumReleaseVerdict(
            undetermined_detail=(
                "the committed dispatcher.minimum_release floor could not be read "
                f"({configured.failure().detail})"
            )
        )
    floor = configured.unwrap()
    if floor is None:
        return None
    executing = released_payload_version(
        root=executing_payload if executing_payload is not None else executing_payload_root()
    )
    below = None if executing is None else release_below_floor(release=executing, floor=floor)
    if below is None:
        return MinimumReleaseVerdict(
            undetermined_detail=(
                f"the committed dispatcher.minimum_release floor {floor!r} could not be "
                "evaluated because the executing release is unobservable"
            )
        )
    if not below:
        return MinimumReleaseVerdict()
    return MinimumReleaseVerdict(
        refusal_detail=(
            f"ERROR: dispatcher plugin release {executing} is below the committed "
            f"dispatcher.minimum_release floor {floor}. Run `{_UPDATE_REMEDY}` and "
            f"restart before dispatching. The installation to update is {plugin_root}."
        )
    )


def _minimum_release_value(*, value: object) -> Result[str | None, PolicySettingUnreadable]:
    if value is None:
        return Success(None)
    if isinstance(value, str) and value.strip():
        return Success(value.strip())
    return Failure(
        PolicySettingUnreadable(
            setting=_MINIMUM_RELEASE_KEY,
            detail=(
                f"dispatcher.{_MINIMUM_RELEASE_KEY} must be a non-empty released-version "
                f"identifier string; got {value!r}"
            ),
        )
    )
