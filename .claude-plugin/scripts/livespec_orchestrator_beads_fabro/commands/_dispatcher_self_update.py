"""Staged self-update + canary for the Dispatcher (work-item livespec-impl-beads-ddu).

0jxs operability precondition (the LAST item in the dispatcher-hardening
chain before the W6 dark-factory cutover, epic livespec-4moata). The
hazard this layer closes:

The Dispatcher's `_post_merge` stage runs `git -C <repo> pull --ff-only
origin master` to refresh the target repo's primary after a confirmed
merge (`_dispatcher_engine`). When the target repo IS impl-beads itself
— the dark factory dispatching impl-beads's OWN scripts — that pull
fast-forwards the very working tree the Dispatcher's code is loaded from
(the `bin/dispatcher.py` shebang wrapper resolves the package root out of
the live primary via `Path(__file__)`). A bad self-merge therefore swaps
the running dispatcher's code out from under it: the NEXT loop iteration
— or the next dispatcher invocation — runs whatever the bad self-merge
landed, with NO human watching, BRICKING the loop. Today the only
mitigation is manual orchestrator embargo sequencing (never pull the
impl-beads primary while any dispatcher is alive), which the dark factory
cannot perform.

The fix shape (the work-item's fix direction, narrowed to a correct
increment that does NOT change how the dispatcher is invoked from the CLI
wrapper):

  * **Pinned execution copy.** The active dispatcher runs from a PINNED
    COPY of its own scripts (a snapshot directory keyed by the ref it was
    cut from), NOT the live primary tree. A primary pull mid-loop cannot
    swap the running code because the running code lives in the pinned
    copy, not the primary.
  * **Staged self-update.** When a merged change touches the dispatcher's
    OWN scripts (a self-merge — `is_self_merge`), the new version is
    STAGED into a CANDIDATE pinned copy rather than promoted immediately.
  * **Canary before promote.** Before the candidate becomes the active
    pinned copy, a CANARY validates it (a cheap, side-effect-free
    SELF-CHECK of the candidate dispatcher — never a real fabro run).
    Only a PASSING canary promotes the candidate; a FAILING canary keeps
    the last-known-good pinned copy and ALARMS a human through h1p's
    `notify_terminal` seam. A dark-factory run can therefore never silently
    promote a broken self-update.

This module is the PURE decision + parsing layer (mirroring
`_dispatcher_watchdog` / `_dispatcher_cost`): self-merge detection
(`is_self_merge`), the canary verdict over an injected self-check result
(`canary_verdict`), and the promotion decision over that verdict
(`promotion_decision`). Everything here is a pure function of its inputs
so the hermetic test tier drives every branch — INCLUDING the canary —
WITHOUT launching a real fabro run (the self-machinery hang-guard). The
side-effecting orchestration (copying the staged tree, running the canary
self-check subprocess, firing the alarm) lives in `dispatcher.py`'s
`_self_update_after_merge`, driven by the same injected `CommandRunner` /
`JournalWriter` / `NotifyPoster` seams the cost gate and notifier already
use.

The canary self-check (`canary_self_check_argv`): the candidate
dispatcher's OWN `ledger-check --json` against an EMPTY ledger via a
throwaway `--project-root`. It exercises the candidate's argument parsing,
its module import graph, and the check pipeline end-to-end (so a candidate
that fails to import, crashes on a flag, or regresses the check surface
fails the canary) while touching no real ledger, no fabro, and no network
— exactly the cheap, fully-mockable validation the hang-guard requires.

Credential hygiene (mirrors the notifier / cost gate): the decision
carries only scalar id / class / reason fields and the alarm body ships
ONLY the work-item id + outcome class + run id through `notify_terminal`.
No goal text, env values, stderr blobs, or remote URLs reach the alarm.
"""

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

# The repo-relative path prefixes that constitute the Dispatcher's OWN
# code: a merged change touching ANY of these is a self-merge whose
# promotion must be staged + canaried, because it can swap the running
# dispatcher's code out from under it. The dispatcher package and its
# shebang wrapper both resolve out of the live tree, so both count.
#   * the dispatcher command package (the engine, plan, io, watchdog,
#     notify, cost, reflection, and this module);
#   * the `bin/` shebang wrappers + `_bootstrap` the wrapper imports;
#   * the shared command helpers the dispatcher imports (`_config`,
#     `_cross_repo`, the store, the types) — a regression there breaks the
#     dispatcher just as surely as one in its own command module.
# Matched as path PREFIXES (POSIX `/`-joined, repo-relative) so a nested
# file under any of them counts. Kept deliberately broad: a false POSITIVE
# merely stages + canaries a change that did not need it (safe, cheap); a
# false NEGATIVE would let a bricking self-merge promote unguarded.
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

# The alarm class a failed-canary self-update breach fires through h1p's
# `notify_terminal` seam. NOT a `DispatchOutcome.status`, so (like y0m's
# `spend-cap-breach`) it is built as its own `NotifyEvent` rather than
# flowing through `terminal_events`.
SELF_UPDATE_BREACH_CLASS = "self-update-canary-failed"


@dataclass(frozen=True, kw_only=True, slots=True)
class CanaryVerdictValue:
    """Enum-like verdict value without subclassing."""

    value: str


class CanaryVerdict:
    """The canary's pass/fail decision over the candidate self-check.

    `PASS` — the candidate dispatcher's self-check ran clean (exit 0): its
    import graph, argument parsing, and check pipeline are intact, so the
    candidate is safe to promote to the active pinned copy.
    `FAIL` — the candidate self-check exited non-zero (a crash, an import
    error, a regressed check surface) OR timed out: the candidate is NOT
    safe; keep the last-known-good pinned copy and ALARM.
    """

    PASS: Final = CanaryVerdictValue(value="pass")
    FAIL: Final = CanaryVerdictValue(value="fail")


@dataclass(frozen=True, kw_only=True)
class PromotionDecision:
    """Whether to promote the staged candidate to the active pinned copy.

    `promote` is True only when the canary PASSED — the load-bearing
    safety property: a broken self-update never becomes the active
    pinned copy. `alarm` is True only when the canary FAILED (promotion
    refused) — the dark-factory operability gate: a refused promotion
    ALARMS a human rather than silently keeping the old copy. `reason` is
    a leak-free scalar string for the journal / alarm body (no paths, no
    stderr blobs).
    """

    promote: bool
    alarm: bool
    reason: str


def pr_files_argv(*, branch: str) -> list[str]:
    """`gh pr view <branch> --json files`: the merged PR's changed file list.

    The host-side source of the merged paths the self-merge detector reads
    (`gh` is authenticated in the Dispatcher's own environment). `--json
    files` returns `{"files": [{"path": "..."}, ...]}` with repo-relative
    POSIX paths — exactly what `is_self_merge` matches against. Read AFTER
    the PR is confirmed merged, so the file list is final.
    """
    return ["gh", "pr", "view", branch, "--json", "files"]


def parse_pr_files(*, stdout: str) -> tuple[str, ...]:
    """Extract repo-relative paths from `gh pr view --json files`; () on no signal.

    Returns the tuple of `path` strings from the `{"files": [...]}`
    payload. An empty tuple is the explicit NO-SIGNAL result for an
    unparseable / unexpectedly-shaped payload — `is_self_merge` treats it
    as "not a self-merge" (the safe default: an unobservable file list
    must never force a stage-and-canary blindly; the caller journals the
    unobservable list as its own degraded path).
    """
    try:
        parsed_raw: object = json.loads(stdout)
    except json.JSONDecodeError:
        return ()
    if not isinstance(parsed_raw, dict):
        return ()
    files_raw: object = cast("dict[str, Any]", parsed_raw).get("files")
    if not isinstance(files_raw, list):
        return ()
    paths: list[str] = []
    for entry in cast("list[object]", files_raw):
        if isinstance(entry, dict):
            path_raw: object = cast("dict[str, Any]", entry).get("path")
            if isinstance(path_raw, str) and path_raw != "":
                paths.append(path_raw)
    return tuple(paths)


def is_self_merge(*, merged_paths: tuple[str, ...]) -> bool:
    """True when any merged path is part of the Dispatcher's OWN code.

    `merged_paths` are repo-relative POSIX paths of the files the
    confirmed merge changed (the engine reads them from the merge commit;
    this layer only decides). A path counts when it falls under any
    `DISPATCHER_SCRIPT_PREFIXES` entry — either nested beneath a directory
    prefix (prefix ends in `/`) or equal to a file prefix. Empty input
    (no changed paths resolved) is NOT a self-merge: an unobservable
    file list must never STAGE-and-canary blindly — the engine routes a
    missing file list as its own degraded path, not as a forced canary.
    """
    return any(_path_is_dispatcher_code(path=path) for path in merged_paths)


def _path_is_dispatcher_code(*, path: str) -> bool:
    """True when one repo-relative path is part of the Dispatcher's own code."""
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
    """The argv for the candidate dispatcher's cheap, side-effect-free canary.

    Runs the CANDIDATE's OWN `dispatcher.py ledger-check --json` against a
    throwaway `--project-root` (`scratch_root`, a freshly-created empty
    directory with no `.livespec.jsonc` / ledger). This exercises the
    candidate end-to-end — its module import graph, its argument parsing,
    and its check pipeline — while touching NO real ledger, NO fabro, and
    NO network. The canary's PASS criterion is a clean exit; a candidate
    that fails to import, crashes on a flag, or regresses the check
    surface exits non-zero and FAILS the canary. `candidate_bin` is the
    path to the staged candidate's `bin/dispatcher.py`; `scratch_root` is
    the empty scratch project root. NEVER a `fabro run` (the
    self-machinery hang-guard): no real, expensive, side-effecting run
    ever participates in promotion.
    """
    return [
        "python3",
        candidate_bin,
        "ledger-check",
        "--project-root",
        scratch_root,
        "--json",
    ]


def canary_verdict(*, exit_code: int) -> CanaryVerdictValue:
    """Map a candidate self-check exit code to the canary verdict.

    Exit 0 -> `PASS` (the candidate ran clean). ANY non-zero exit ->
    `FAIL` — this deliberately covers the timeout exit (the
    `ShellCommandRunner` converts a timed-out self-check into a non-zero
    `CommandResult`), so a candidate that HANGS the canary fails it rather
    than stalling promotion: fail-CLOSED, never silently promoted.
    """
    return CanaryVerdict.PASS if exit_code == 0 else CanaryVerdict.FAIL


def promotion_decision(*, verdict: CanaryVerdictValue) -> PromotionDecision:
    """Decide promotion from the canary verdict. Fail-closed on FAIL.

    `PASS` -> promote the candidate, no alarm (the new version is safe to
    become the active pinned copy). `FAIL` -> do NOT promote, ALARM: keep
    the last-known-good pinned copy and fire h1p's `notify_terminal` so a
    human sees the refused self-update. The reason is a leak-free scalar
    for the journal / alarm body.
    """
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
