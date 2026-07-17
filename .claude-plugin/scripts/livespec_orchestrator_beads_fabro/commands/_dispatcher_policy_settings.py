"""Dispatcher policy setting reads and per-item effective-policy resolution.

This module owns the `.livespec.jsonc` reads for the independent
`dispatcher.*` settings and the per-item-over-global policy resolution used by
the Dispatcher valves. Reads are fail-open to safe defaults: a missing file,
missing block/key, parse error, or wrong-typed value returns the setting's
safe default rather than raising.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro.commands import _jsonc

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "ACCEPTANCE_REWORK_CAP_LABEL",
    "DEFAULT_ACCEPTANCE_POLICY",
    "DEFAULT_ACCEPTANCE_REWORK_CAP",
    "DEFAULT_ADMISSION_POLICY",
    "DEFAULT_AUTO_APPROVE_READY",
    "DEFAULT_MERGE_ON_REVIEW_CAP",
    "DEFAULT_REVIEW_FIX_CAP",
    "DEFAULT_WIP_CAP",
    "MERGE_ON_REVIEW_CAP_LABEL",
    "REVIEW_FIX_CAP_LABEL",
    "effective_acceptance_policy",
    "effective_acceptance_rework_cap",
    "effective_admission_policy",
    "effective_merge_on_review_cap",
    "effective_review_fix_cap",
    "resolve_acceptance_mode",
    "resolve_acceptance_rework_cap",
    "resolve_auto_approve_ready",
    "resolve_merge_on_review_cap",
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

_AUTO_ADMISSION = "auto"
_LIVESPEC_CONFIG = ".livespec.jsonc"
_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_DISPATCHER_KEY = "dispatcher"
_WIP_CAP_KEY = "wip_cap"
_AUTO_APPROVE_READY_KEY = "auto_approve_ready"
_MERGE_ON_REVIEW_CAP_KEY = "merge_on_review_cap"
_ACCEPTANCE_MODE_KEY = "acceptance_mode"
_REVIEW_FIX_CAP_KEY = "review_fix_cap"
_ACCEPTANCE_REWORK_CAP_KEY = "acceptance_rework_cap"
MERGE_ON_REVIEW_CAP_LABEL = "merge-on-review-cap:"
REVIEW_FIX_CAP_LABEL = "review-fix-cap:"
ACCEPTANCE_REWORK_CAP_LABEL = "acceptance-rework-cap:"
_ACCEPTANCE_POLICIES = frozenset(("ai-only", "ai-then-human", "human-only"))


def resolve_wip_cap(*, cwd: Path) -> int:
    """Read the per-repo WIP cap from `.livespec.jsonc`, defaulting to 5."""
    return _resolve_positive_int_setting(cwd=cwd, key=_WIP_CAP_KEY, default=DEFAULT_WIP_CAP)


def resolve_auto_approve_ready(*, cwd: Path) -> bool:
    """Read `dispatcher.auto_approve_ready` (default False; bool true only)."""
    return _resolve_bool_setting(
        cwd=cwd, key=_AUTO_APPROVE_READY_KEY, default=DEFAULT_AUTO_APPROVE_READY
    )


def resolve_merge_on_review_cap(*, cwd: Path) -> bool:
    """Read `dispatcher.merge_on_review_cap` (default False; bool true only)."""
    return _resolve_bool_setting(
        cwd=cwd, key=_MERGE_ON_REVIEW_CAP_KEY, default=DEFAULT_MERGE_ON_REVIEW_CAP
    )


def resolve_acceptance_mode(*, cwd: Path) -> str:
    """Read `dispatcher.acceptance_mode`, defaulting to `ai-then-human`."""
    value = _read_dispatcher_config_value(cwd=cwd, key=_ACCEPTANCE_MODE_KEY)
    if isinstance(value, str) and value in _ACCEPTANCE_POLICIES:
        return value
    return DEFAULT_ACCEPTANCE_POLICY


def resolve_review_fix_cap(*, cwd: Path) -> int:
    """Read `dispatcher.review_fix_cap`, defaulting to 3."""
    return _resolve_positive_int_setting(
        cwd=cwd, key=_REVIEW_FIX_CAP_KEY, default=DEFAULT_REVIEW_FIX_CAP
    )


def resolve_acceptance_rework_cap(*, cwd: Path) -> int:
    """Read `dispatcher.acceptance_rework_cap`, defaulting to 2."""
    return _resolve_positive_int_setting(
        cwd=cwd, key=_ACCEPTANCE_REWORK_CAP_KEY, default=DEFAULT_ACCEPTANCE_REWORK_CAP
    )


def effective_admission_policy(*, item: WorkItem, cwd: Path | None = None) -> str:
    """The item's effective admission policy with per-item-over-global precedence."""
    if _is_spec_change_tier(item=item):
        return DEFAULT_ADMISSION_POLICY
    if item.admission_policy is not None:
        return item.admission_policy
    if cwd is not None and resolve_auto_approve_ready(cwd=cwd):
        return _AUTO_ADMISSION
    return DEFAULT_ADMISSION_POLICY


def effective_acceptance_policy(*, item: WorkItem, cwd: Path | None = None) -> str:
    """The item's effective acceptance policy with per-item-over-global precedence."""
    if item.acceptance_policy is not None:
        return item.acceptance_policy
    if cwd is not None:
        return resolve_acceptance_mode(cwd=cwd)
    return DEFAULT_ACCEPTANCE_POLICY


def effective_merge_on_review_cap(
    *, item: WorkItem, cwd: Path | None = None, raw_labels: Sequence[str] = ()
) -> bool:
    """Resolve `merge_on_review_cap`, with a raw per-item label overriding global."""
    _ = item
    label_value = _raw_label_value(raw_labels=raw_labels, prefix=MERGE_ON_REVIEW_CAP_LABEL)
    parsed = _bool_label_value(value=label_value)
    if parsed is not None:
        return parsed
    if cwd is not None:
        return resolve_merge_on_review_cap(cwd=cwd)
    return DEFAULT_MERGE_ON_REVIEW_CAP


def effective_review_fix_cap(
    *, item: WorkItem, cwd: Path | None = None, raw_labels: Sequence[str] = ()
) -> int:
    """Resolve `review_fix_cap`, with a raw per-item label overriding global."""
    _ = item
    label_value = _raw_label_value(raw_labels=raw_labels, prefix=REVIEW_FIX_CAP_LABEL)
    parsed = _positive_int_label_value(value=label_value)
    if parsed is not None:
        return parsed
    if cwd is not None:
        return resolve_review_fix_cap(cwd=cwd)
    return DEFAULT_REVIEW_FIX_CAP


def effective_acceptance_rework_cap(
    *, item: WorkItem, cwd: Path | None = None, raw_labels: Sequence[str] = ()
) -> int:
    """Resolve `acceptance_rework_cap`, with a raw per-item label overriding global."""
    _ = item
    label_value = _raw_label_value(raw_labels=raw_labels, prefix=ACCEPTANCE_REWORK_CAP_LABEL)
    parsed = _positive_int_label_value(value=label_value)
    if parsed is not None:
        return parsed
    if cwd is not None:
        return resolve_acceptance_rework_cap(cwd=cwd)
    return DEFAULT_ACCEPTANCE_REWORK_CAP


def _read_dispatcher_config_value(*, cwd: Path, key: str) -> object:
    return _read_nested_config_value(cwd=cwd, keys=(_PLUGIN_BLOCK, _DISPATCHER_KEY, key))


def _read_nested_config_value(*, cwd: Path, keys: tuple[str, ...]) -> object:
    config_path = cwd / _LIVESPEC_CONFIG
    if not config_path.is_file():
        return None
    node = _jsonc.parse(text=config_path.read_text(encoding="utf-8"))
    if isinstance(node, _jsonc.JsoncFailure):
        return None
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = cast("dict[str, Any]", node).get(key)
    return node


def _resolve_bool_setting(*, cwd: Path, key: str, default: bool) -> bool:
    value = _read_dispatcher_config_value(cwd=cwd, key=key)
    if value is True:
        return True
    if value is False:
        return False
    return default


def _resolve_positive_int_setting(*, cwd: Path, key: str, default: int) -> int:
    value = _read_dispatcher_config_value(cwd=cwd, key=key)
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return default


def _raw_label_value(*, raw_labels: Sequence[str], prefix: str) -> str | None:
    for label in raw_labels:
        if label.startswith(prefix):
            return label[len(prefix) :]
    return None


def _bool_label_value(*, value: str | None) -> bool | None:
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def _positive_int_label_value(*, value: str | None) -> int | None:
    if value is None or not value.isdecimal():
        return None
    parsed = int(value)
    if parsed > 0:
        return parsed
    return None


def _is_spec_change_tier(*, item: WorkItem) -> bool:
    return item.spec_commitment_hint is not None
