from __future__ import annotations

import json
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any, Final, cast

__all__: list[str] = [
    "DISPATCHER_SCRIPT_PREFIXES",
    "SELF_UPDATE_BREACH_CLASS",
    "CanaryVerdict",
    "PromotionDecision",
    "canary_self_check_argv",
    "canary_verdict",
    "is_self_merge",
    "parse_pr_files",
    "pr_files_argv",
    "promotion_decision",
]

DISPATCHER_SCRIPT_PREFIXES: tuple[str, ...] = (
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/",
    ".claude-plugin/scripts/bin/",
    ".claude-plugin/scripts/_bootstrap.py",
)

_DISPATCHER_SCRIPT_PATTERNS: tuple[str, ...] = (
    "commands/_dispatcher_*.py",
    "commands/dispatcher.py",
    "dispatcher.py",
)

SELF_UPDATE_BREACH_CLASS = "self-update-canary-failed"


@dataclass(frozen=True, kw_only=True, slots=True)
class CanaryVerdictValue:
    value: str


class CanaryVerdict:
    PASS: Final = CanaryVerdictValue(value="pass")
    FAIL: Final = CanaryVerdictValue(value="fail")


@dataclass(frozen=True, kw_only=True)
class PromotionDecision:
    promote: bool
    alarm: bool
    reason: str


def pr_files_argv(*, branch: str) -> list[str]:
    return ["gh", "pr", "view", branch, "--json", "files"]


def parse_pr_files(*, stdout: str) -> tuple[str, ...]:
    try:
        parsed_raw: object = json.loads(stdout)
    except json.JSONDecodeError:
        return ()
    if not isinstance(parsed_raw, dict):
        return ()
    files_raw: object = cast("dict[str, Any]", parsed_raw).get("files")
    if not isinstance(files_raw, list):
        return ()
    return tuple(
        path_raw
        for entry in cast("list[object]", files_raw)
        if isinstance(entry, dict)
        for path_raw in (cast("dict[str, Any]", entry).get("path"),)
        if isinstance(path_raw, str) and path_raw != ""
    )


def is_self_merge(*, merged_paths: tuple[str, ...]) -> bool:
    return any(_path_is_dispatcher_code(path=path) for path in merged_paths)


def _path_is_dispatcher_code(*, path: str) -> bool:
    normalized = path.strip()
    if normalized == "":
        return False
    for prefix in DISPATCHER_SCRIPT_PREFIXES:
        if prefix.endswith("/"):
            if normalized.startswith(prefix):
                return True
        elif normalized == prefix:
            return True
    return any(fnmatchcase(normalized, pattern) for pattern in _DISPATCHER_SCRIPT_PATTERNS)


def canary_self_check_argv(*, candidate_bin: str, scratch_root: str) -> list[str]:
    return [
        "python3",
        candidate_bin,
        "ledger-check",
        "--project-root",
        scratch_root,
        "--json",
    ]


def canary_verdict(*, exit_code: int) -> CanaryVerdictValue:
    return CanaryVerdict.PASS if exit_code == 0 else CanaryVerdict.FAIL


def promotion_decision(*, verdict: CanaryVerdictValue) -> PromotionDecision:
    if verdict is CanaryVerdict.PASS:
        return PromotionDecision(
            promote=True,
            alarm=False,
            reason="canary passed; promoting staged self-update to the active pinned copy",
        )
    return PromotionDecision(
        promote=False,
        alarm=True,
        reason=(
            "canary FAILED; keeping the last-known-good pinned copy and alarming "
            "(the staged self-update is NOT promoted)"
        ),
    )
