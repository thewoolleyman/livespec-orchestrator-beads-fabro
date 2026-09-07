"""Dispatcher policy setting reads — the repository-wide global defaults.

This module owns the `.livespec.jsonc` reads for the independent
`dispatcher.*` settings. The per-item-over-global resolution the Dispatcher
valves call sits beside it in `_dispatcher_policy_overrides.py`: a global
default and a per-item label override are two questions with two inputs, and
only the second needs a `WorkItem`.

⛔ AN UNREADABLE CONFIG IS NOT AN UNCONFIGURED ONE. Every read here used to
answer with the setting's safe default in four different situations: the file
is absent, the block or key is absent, the file does not PARSE, and the value
is present but is not something the setting can accept. Only the first two are
ANSWERS. The other two are an operator's config being wrong, reported as
though they had never configured anything.

That is not hypothetical in this repo. Its own `.livespec.jsonc` moves
`auto_approve_ready` and `acceptance_mode` OFF their safe defaults under an
explicit maintainer direction, and that same file carries a comment warning
that the `drive --action set-config` surface round-trips it through
`json.dumps` and strips the block while reporting green (bd-ib-lmi5). A file
that stops parsing is an ANTICIPATED event here, and it silently reverted the
Dispatcher to human-gated admission and acceptance with nothing said anywhere.

So the two are split. An absent file, block or key stays an answer and rides
the SUCCESS track carrying the documented default. A file that will not parse,
a node on the key path that is not an object, and a value the setting cannot
accept become `PolicySettingUnreadable` failures carrying what could not be
read. The fail-open POLICY is unchanged — every call site still falls back to
the same default — but it is now spelled `.value_or(...)` where the choice to
discard the reason is visible, rather than made once for everybody inside the
reader. The write half of this config already worked this way:
`_drive_config` refuses with "Cannot write config until .livespec.jsonc
parses: ..." on exactly the condition the read half swallowed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from returns.io import IOFailure, IOResult, IOSuccess
from returns.result import Failure, Result, Success

from livespec_orchestrator_beads_fabro.commands import _jsonc

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "DEFAULT_ACCEPTANCE_POLICY",
    "DEFAULT_ACCEPTANCE_REWORK_CAP",
    "DEFAULT_ADMISSION_POLICY",
    "DEFAULT_ANSWER_DISPOSITION",
    "DEFAULT_AUTOMATED_REGROOM_CAP",
    "DEFAULT_AUTO_APPROVE_READY",
    "DEFAULT_DRIFT_CAPTURE_MERGE_THRESHOLD",
    "DEFAULT_GROOM_CUT_APPROVAL",
    "DEFAULT_MERGE_ON_REVIEW_CAP",
    "DEFAULT_READY_AGING_THRESHOLD_HOURS",
    "DEFAULT_REQUIRE_INVOKER",
    "DEFAULT_REVIEW_FIX_CAP",
    "DEFAULT_WIP_CAP",
    "PolicySettingUnreadable",
    "read_dispatcher_config_value",
    "resolve_acceptance_mode",
    "resolve_acceptance_rework_cap",
    "resolve_answer_disposition",
    "resolve_auto_approve_ready",
    "resolve_automated_regroom_cap",
    "resolve_drift_capture_merge_threshold",
    "resolve_groom_cut_approval",
    "resolve_merge_on_review_cap",
    "resolve_ready_aging_threshold_hours",
    "resolve_require_invoker",
    "resolve_review_fix_cap",
    "resolve_wip_cap",
]

DEFAULT_WIP_CAP = 5
DEFAULT_AUTO_APPROVE_READY = False
DEFAULT_MERGE_ON_REVIEW_CAP = False
DEFAULT_ADMISSION_POLICY = "manual"
DEFAULT_ACCEPTANCE_POLICY = "ai-then-human"
DEFAULT_REVIEW_FIX_CAP = 3
DEFAULT_ACCEPTANCE_REWORK_CAP = 2
DEFAULT_READY_AGING_THRESHOLD_HOURS = 24
DEFAULT_REQUIRE_INVOKER = False
DEFAULT_DRIFT_CAPTURE_MERGE_THRESHOLD = 1
DEFAULT_GROOM_CUT_APPROVAL = "human"
DEFAULT_AUTOMATED_REGROOM_CAP = 2
DEFAULT_ANSWER_DISPOSITION = "human"

_LIVESPEC_CONFIG = ".livespec.jsonc"
_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_DISPATCHER_KEY = "dispatcher"
_WIP_CAP_KEY = "wip_cap"
_AUTO_APPROVE_READY_KEY = "auto_approve_ready"
_MERGE_ON_REVIEW_CAP_KEY = "merge_on_review_cap"
_ACCEPTANCE_MODE_KEY = "acceptance_mode"
_REVIEW_FIX_CAP_KEY = "review_fix_cap"
_ACCEPTANCE_REWORK_CAP_KEY = "acceptance_rework_cap"
_READY_AGING_THRESHOLD_HOURS_KEY = "ready_aging_threshold_hours"
_REQUIRE_INVOKER_KEY = "require_invoker"
_DRIFT_CAPTURE_MERGE_THRESHOLD_KEY = "drift_capture_merge_threshold"
_GROOM_CUT_APPROVAL_KEY = "groom_cut_approval"
_AUTOMATED_REGROOM_CAP_KEY = "automated_regroom_cap"
_ANSWER_DISPOSITION_KEY = "answer_disposition"
_ACCEPTANCE_POLICIES = frozenset(("ai-only", "ai-then-human", "human-only"))
_GROOM_CUT_APPROVALS = frozenset(("human", "consensus"))
_ANSWER_DISPOSITIONS = frozenset(("human", "consensus"))


@dataclass(frozen=True, kw_only=True)
class PolicySettingUnreadable:
    """A `dispatcher.*` setting that could not be READ, as against not set.

    Deliberately NOT inhabited by "the file, block or key is absent". An
    unconfigured setting has a documented default and that default is the
    ANSWER; being unable to read a setting the operator did configure is a
    different claim, and it is the one that had no way to be made.
    """

    setting: str
    detail: str


def resolve_wip_cap(*, cwd: Path) -> IOResult[int, PolicySettingUnreadable]:
    """Read the per-repo WIP cap from `.livespec.jsonc`, defaulting to 5."""
    return _resolve_int_setting(cwd=cwd, key=_WIP_CAP_KEY, default=DEFAULT_WIP_CAP, minimum=0)


def resolve_auto_approve_ready(*, cwd: Path) -> IOResult[bool, PolicySettingUnreadable]:
    """Read `dispatcher.auto_approve_ready` (default False; bool only)."""
    return _resolve_bool_setting(
        cwd=cwd, key=_AUTO_APPROVE_READY_KEY, default=DEFAULT_AUTO_APPROVE_READY
    )


def resolve_merge_on_review_cap(*, cwd: Path) -> IOResult[bool, PolicySettingUnreadable]:
    """Read `dispatcher.merge_on_review_cap` (default False; bool only)."""
    return _resolve_bool_setting(
        cwd=cwd, key=_MERGE_ON_REVIEW_CAP_KEY, default=DEFAULT_MERGE_ON_REVIEW_CAP
    )


def resolve_acceptance_mode(*, cwd: Path) -> IOResult[str, PolicySettingUnreadable]:
    """Read `dispatcher.acceptance_mode`, defaulting to `ai-then-human`."""
    return _resolve_enum_setting(
        cwd=cwd,
        key=_ACCEPTANCE_MODE_KEY,
        default=DEFAULT_ACCEPTANCE_POLICY,
        allowed=_ACCEPTANCE_POLICIES,
    )


def resolve_groom_cut_approval(*, cwd: Path) -> IOResult[str, PolicySettingUnreadable]:
    """Read `dispatcher.groom_cut_approval`, defaulting to `human`.

    INERT at this slice by design: nothing dispatches, admits or grooms on
    this value yet. Its consumers are the groom door and the registered groom
    workflow variant of the consensus-gated automated groom cut in
    contracts.md, each filed as its own item, so the key is readable
    configuration and nothing else until they land. Note that
    `consensus` behaves as `human` until livespec core ratifies the consensus
    tier — that equivalence belongs to the door, not to this read, which
    reports what the operator wrote.
    """
    return _resolve_enum_setting(
        cwd=cwd,
        key=_GROOM_CUT_APPROVAL_KEY,
        default=DEFAULT_GROOM_CUT_APPROVAL,
        allowed=_GROOM_CUT_APPROVALS,
    )


def resolve_answer_disposition(*, cwd: Path) -> IOResult[str, PolicySettingUnreadable]:
    """Read `dispatcher.answer_disposition`, defaulting to `human`.

    The fifth policy setting: who may answer an ATTENTION ITEM — a work-item
    resting at `blocked` / `blocked_reason: needs-human` — through a
    `resolve-blocked … --answer` press. As with its `groom_cut_approval`
    sibling, `consensus` behaves as `human` until livespec core ratifies the
    consensus tier, and that equivalence belongs to the surfaces that enforce
    and advertise the press rather than to this read, which reports what the
    operator wrote.
    """
    return _resolve_enum_setting(
        cwd=cwd,
        key=_ANSWER_DISPOSITION_KEY,
        default=DEFAULT_ANSWER_DISPOSITION,
        allowed=_ANSWER_DISPOSITIONS,
    )


def resolve_automated_regroom_cap(*, cwd: Path) -> IOResult[int, PolicySettingUnreadable]:
    """Read `dispatcher.automated_regroom_cap`, defaulting to 2.

    The third rework cap, and INERT for the same reason as its sibling above:
    it bounds re-drafting rounds the consensus tier has no way to start yet.
    """
    return _resolve_int_setting(
        cwd=cwd,
        key=_AUTOMATED_REGROOM_CAP_KEY,
        default=DEFAULT_AUTOMATED_REGROOM_CAP,
        minimum=1,
    )


def resolve_review_fix_cap(*, cwd: Path) -> IOResult[int, PolicySettingUnreadable]:
    """Read `dispatcher.review_fix_cap`, defaulting to 3."""
    return _resolve_int_setting(
        cwd=cwd, key=_REVIEW_FIX_CAP_KEY, default=DEFAULT_REVIEW_FIX_CAP, minimum=1
    )


def resolve_acceptance_rework_cap(*, cwd: Path) -> IOResult[int, PolicySettingUnreadable]:
    """Read `dispatcher.acceptance_rework_cap`, defaulting to 2."""
    return _resolve_int_setting(
        cwd=cwd, key=_ACCEPTANCE_REWORK_CAP_KEY, default=DEFAULT_ACCEPTANCE_REWORK_CAP, minimum=1
    )


def resolve_ready_aging_threshold_hours(*, cwd: Path) -> IOResult[int, PolicySettingUnreadable]:
    """Read `dispatcher.ready_aging_threshold_hours`, defaulting to 24."""
    return _resolve_int_setting(
        cwd=cwd,
        key=_READY_AGING_THRESHOLD_HOURS_KEY,
        default=DEFAULT_READY_AGING_THRESHOLD_HOURS,
        minimum=1,
    )


def resolve_drift_capture_merge_threshold(*, cwd: Path) -> IOResult[int, PolicySettingUnreadable]:
    """Read `dispatcher.drift_capture_merge_threshold`, defaulting to 1.

    The merge-count trigger for the drift-staleness fact (the detection
    coverage-record contract in contracts.md). Detection recency is a
    REPOSITORY property, so this dial has no per-item override.
    """
    return _resolve_int_setting(
        cwd=cwd,
        key=_DRIFT_CAPTURE_MERGE_THRESHOLD_KEY,
        default=DEFAULT_DRIFT_CAPTURE_MERGE_THRESHOLD,
        minimum=1,
    )


def resolve_require_invoker(*, cwd: Path) -> IOResult[bool, PolicySettingUnreadable]:
    """Read `dispatcher.require_invoker` (default False; bool only).

    Deliberately NOT a member of the API-configurable key manifest: a dial that
    RELAXES attribution must not be reachable over the surface whose acts it
    attributes, so it is editable only by a committed `.livespec.jsonc` change
    (the journal invoker attribution contract in contracts.md).
    """
    return _resolve_bool_setting(cwd=cwd, key=_REQUIRE_INVOKER_KEY, default=DEFAULT_REQUIRE_INVOKER)


def read_dispatcher_config_value(
    *, cwd: Path, key: str
) -> IOResult[object, PolicySettingUnreadable]:
    """One raw `dispatcher.<key>` value, absent-is-an-answer / unreadable-is-a-failure.

    PUBLIC because a `dispatcher.*` setting whose coercion is cohesive with its
    CONSUMER rather than with this module is read through here rather than by
    hand-rolling the nested lookup — `dispatcher.minimum_release` lives with the
    dispatch-admission currency floor in `_dispatcher_minimum_release_floor.py`,
    which owns the released-version semantics that key is written in.
    """
    return _read_nested_config_value(
        cwd=cwd, keys=(_PLUGIN_BLOCK, _DISPATCHER_KEY, key), setting=key
    )


def _read_nested_config_value(
    *, cwd: Path, keys: tuple[str, ...], setting: str
) -> IOResult[object, PolicySettingUnreadable]:
    """`None` on the success track when the file, block or key is simply ABSENT.

    That `None` is an ANSWER — "nothing is configured here" — and each setting
    turns it into that setting's default. A node on the key path that EXISTS
    and is not an object is a different thing: the operator wrote something the
    key cannot live under, so it fails rather than reading as unset.
    """
    config_path = cwd / _LIVESPEC_CONFIG
    if not config_path.is_file():
        return IOSuccess(None)
    node = _jsonc.parse(text=config_path.read_text(encoding="utf-8"))
    if isinstance(node, _jsonc.JsoncFailure):
        return IOFailure(
            PolicySettingUnreadable(
                setting=setting, detail=f"{_LIVESPEC_CONFIG} does not parse: {node.detail}"
            )
        )
    for index, key in enumerate(keys):
        if node is None:
            return IOSuccess(None)
        if not isinstance(node, dict):
            path = ".".join(keys[:index]) or "root"
            return IOFailure(
                PolicySettingUnreadable(
                    setting=setting, detail=f"{_LIVESPEC_CONFIG} {path} is not an object"
                )
            )
        node = cast("dict[str, Any]", node).get(key)
    return IOSuccess(node)


def _resolve_bool_setting(
    *, cwd: Path, key: str, default: bool
) -> IOResult[bool, PolicySettingUnreadable]:
    return read_dispatcher_config_value(cwd=cwd, key=key).bind_result(
        lambda value: _bool_value(key=key, value=value, default=default)
    )


def _resolve_int_setting(
    *, cwd: Path, key: str, default: int, minimum: int
) -> IOResult[int, PolicySettingUnreadable]:
    return read_dispatcher_config_value(cwd=cwd, key=key).bind_result(
        lambda value: _int_value(key=key, value=value, default=default, minimum=minimum)
    )


def _resolve_enum_setting(
    *, cwd: Path, key: str, default: str, allowed: frozenset[str]
) -> IOResult[str, PolicySettingUnreadable]:
    return read_dispatcher_config_value(cwd=cwd, key=key).bind_result(
        lambda value: _enum_value(key=key, value=value, default=default, allowed=allowed)
    )


def _bool_value(*, key: str, value: object, default: bool) -> Result[bool, PolicySettingUnreadable]:
    if value is None:
        return Success(default)
    if isinstance(value, bool):
        return Success(value)
    return Failure(_rejected(setting=key, value=value, want="a boolean"))


def _int_value(
    *, key: str, value: object, default: int, minimum: int
) -> Result[int, PolicySettingUnreadable]:
    if value is None:
        return Success(default)
    if isinstance(value, int) and not isinstance(value, bool) and value >= minimum:
        return Success(value)
    return Failure(_rejected(setting=key, value=value, want=f"an integer >= {minimum}"))


def _enum_value(
    *, key: str, value: object, default: str, allowed: frozenset[str]
) -> Result[str, PolicySettingUnreadable]:
    if value is None:
        return Success(default)
    if isinstance(value, str) and value in allowed:
        return Success(value)
    want = "one of " + ", ".join(sorted(allowed))
    return Failure(_rejected(setting=key, value=value, want=want))


def _rejected(*, setting: str, value: object, want: str) -> PolicySettingUnreadable:
    return PolicySettingUnreadable(
        setting=setting, detail=f"dispatcher.{setting} must be {want}; got {value!r}"
    )
