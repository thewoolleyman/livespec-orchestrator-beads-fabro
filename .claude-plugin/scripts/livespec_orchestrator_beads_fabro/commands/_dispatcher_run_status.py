"""Run and pull-request status parsers for the Dispatcher."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, cast

from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "PrView",
    "parse_pr_view",
    "parse_run_id",
    "parse_run_id_for_work_item",
    "parse_run_status",
    "parse_running_run_id",
]


@dataclass(frozen=True, kw_only=True)
class PrView:
    """The slice of `gh pr view --json` the engine routes on."""

    number: int
    state: str
    auto_merge_armed: bool
    merge_state_status: str
    merge_sha: str | None
    terminal_required_check_failures: tuple[str, ...]


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
_RUN_ID_RE = re.compile(r"Run:\s*([0-9A-Za-z-]+)")


def parse_running_run_id(*, ps_json: str, work_item_id: str) -> str | None:
    """Find the RUNNING run id for `work_item_id` from `fabro ps -a --json`.

    `fabro ps -a --json` lists per-run metadata: a `run_id`, a
    serde-tagged `status` (`{"kind": "running", ...}` or a plain string),
    and the full `goal` text (which embeds `Work-item: <id>` per
    `render_goal`). The watchdog matches the run whose goal contains this
    dispatch's work-item id AND whose status is `running` — the in-flight
    run to watch. None when no such run is found yet (the run may not have
    registered; the watchdog treats that as "no signal", never a stall).
    Accepts a top-level array or a `{"runs": [...]}` envelope.
    """
    parsed_raw = parse_json(text=ps_json)
    if isinstance(parsed_raw, JsonParseFailure):
        return None
    runs = _runs_list(parsed_raw=parsed_raw)
    for run_raw in runs:
        run_id = _running_run_id_for(run_raw=run_raw, work_item_id=work_item_id)
        if run_id is not None:
            return run_id
    return None


def _runs_list(*, parsed_raw: object) -> list[object]:
    """Normalize `fabro ps --json` to a list (top-level array or {"runs": [...]})."""
    if isinstance(parsed_raw, list):
        return cast("list[object]", parsed_raw)
    if isinstance(parsed_raw, dict):
        runs_raw: object = cast("dict[str, Any]", parsed_raw).get("runs")
        if isinstance(runs_raw, list):
            return cast("list[object]", runs_raw)
    return []


def parse_run_id_for_work_item(*, ps_json: str, work_item_id: str) -> str | None:
    """Find the run id for `work_item_id` from `fabro ps -a --json`, any status.

    Like `parse_running_run_id` but STATUS-AGNOSTIC: it matches the run
    whose goal embeds `work_item_id` regardless of status, which is what
    the post-dispatch cost gate needs — the run is terminal (succeeded /
    failed) by the time the cost is read, not `running`. The cost source
    (work-item livespec-impl-beads-5v9) is `fabro ps -a --json`'s
    `total_usd_micros`, keyed by this run id. None when no goal embeds the
    id or the JSON is unusable; the cost gate journals `cost-gate-skipped`
    for a None match rather than crashing the wave.
    """
    parsed_raw = parse_json(text=ps_json)
    if isinstance(parsed_raw, JsonParseFailure):
        return None
    for run_raw in _runs_list(parsed_raw=parsed_raw):
        if not isinstance(run_raw, dict):
            continue
        run = cast("dict[str, Any]", run_raw)
        goal_raw: object = run.get("goal")
        if not isinstance(goal_raw, str) or work_item_id not in goal_raw:
            continue
        run_id_raw: object = run.get("run_id")
        if isinstance(run_id_raw, str) and run_id_raw:
            return run_id_raw
    return None


def _running_run_id_for(*, run_raw: object, work_item_id: str) -> str | None:
    """Return the run id IFF this entry is a running run for `work_item_id`."""
    if not isinstance(run_raw, dict):
        return None
    run = cast("dict[str, Any]", run_raw)
    goal_raw: object = run.get("goal")
    if not isinstance(goal_raw, str) or work_item_id not in goal_raw:
        return None
    if _run_status_kind(run=run) != "running":
        return None
    run_id_raw: object = run.get("run_id")
    return run_id_raw if isinstance(run_id_raw, str) and run_id_raw else None


def _run_status_kind(*, run: dict[str, Any]) -> str | None:
    """Read a run entry's status kind (`{"kind": ...}` or a plain string)."""
    status_raw: object = run.get("status")
    if isinstance(status_raw, str):
        return status_raw
    if isinstance(status_raw, dict):
        kind_raw: object = cast("dict[str, Any]", status_raw).get("kind")
        if isinstance(kind_raw, str):
            return kind_raw
    return None


def parse_run_id(*, output: str) -> str | None:
    """Extract the run id from `fabro run` CLI output.

    The CLI prints `Run: <run-id>` (possibly ANSI-dimmed) when a run
    starts; None when no such line is present (e.g. fabro crashed
    before allocating a run).
    """
    plain = _ANSI_ESCAPE_RE.sub("", output)
    match = _RUN_ID_RE.search(plain)
    if match is None:
        return None
    return match.group(1)


def parse_run_status(*, stdout: str) -> str | None:
    """Parse the status kind out of `fabro inspect <run-id> --json`.

    The status field is a serde-tagged union (`{"kind": "blocked", ...}`
    in fabro v0.254.0); a plain string status is accepted for
    forward-compatibility. None when the shape is unusable.
    """
    parsed_raw = parse_json(text=stdout)
    if isinstance(parsed_raw, JsonParseFailure):
        return None
    if not isinstance(parsed_raw, dict):
        return None
    parsed = cast("dict[str, Any]", parsed_raw)
    status_raw: object = parsed.get("status")
    if isinstance(status_raw, str):
        return status_raw
    if isinstance(status_raw, dict):
        kind_raw: object = cast("dict[str, Any]", status_raw).get("kind")
        if isinstance(kind_raw, str):
            return kind_raw
    return None


_TERMINAL_CHECK_CONCLUSIONS = frozenset(
    {
        "failure",
        "cancelled",
        "timed_out",
        "action_required",
        "startup_failure",
    }
)


def parse_pr_view(*, stdout: str) -> PrView | None:
    """Parse `gh pr view --json` output; None when the shape is unusable."""
    parsed_raw = parse_json(text=stdout)
    if isinstance(parsed_raw, JsonParseFailure):
        return None
    if not isinstance(parsed_raw, dict):
        return None
    parsed = cast("dict[str, Any]", parsed_raw)
    number_raw: object = parsed.get("number")
    if not isinstance(number_raw, int):
        return None
    terminal_failures = tuple(
        name
        for item in _status_check_rollup_items(rollup_raw=parsed.get("statusCheckRollup"))
        if isinstance(item, dict)
        for name in [_terminal_required_check_failure_name(item=cast("dict[str, Any]", item))]
        if name is not None
    )
    state_raw: object = parsed.get("state")
    merge_state_raw: object = parsed.get("mergeStateStatus")
    return PrView(
        number=number_raw,
        state=state_raw if isinstance(state_raw, str) else "UNKNOWN",
        auto_merge_armed=parsed.get("autoMergeRequest") is not None,
        merge_state_status=merge_state_raw if isinstance(merge_state_raw, str) else "UNKNOWN",
        merge_sha=_merge_sha_of(parsed=parsed),
        terminal_required_check_failures=terminal_failures,
    )


def _status_check_rollup_items(*, rollup_raw: object) -> list[object]:
    if isinstance(rollup_raw, list):
        return cast("list[object]", rollup_raw)
    if not isinstance(rollup_raw, dict):
        return []
    rollup = cast("dict[str, Any]", rollup_raw)
    nodes_raw: object = rollup.get("nodes")
    if isinstance(nodes_raw, list):
        return cast("list[object]", nodes_raw)
    contexts_raw: object = rollup.get("contexts")
    if not isinstance(contexts_raw, dict):  # pragma: no cover - defensive malformed gh JSON
        return []
    context_nodes_raw: object = cast("dict[str, Any]", contexts_raw).get("nodes")
    if isinstance(context_nodes_raw, list):
        return cast("list[object]", context_nodes_raw)
    return []  # pragma: no cover - defensive malformed gh JSON


def _terminal_required_check_failure_name(*, item: dict[str, Any]) -> str | None:
    if item.get("required") is not True and item.get("isRequired") is not True:
        return None
    conclusion_raw: object = item.get("conclusion")
    if not isinstance(conclusion_raw, str):
        return None
    if conclusion_raw.lower() not in _TERMINAL_CHECK_CONCLUSIONS:
        return None
    name_raw: object = item.get("name", item.get("context"))
    return name_raw if isinstance(name_raw, str) and name_raw else "unknown"


def _merge_sha_of(*, parsed: dict[str, Any]) -> str | None:
    commit_raw: object = parsed.get("mergeCommit")
    if not isinstance(commit_raw, dict):
        return None
    commit = cast("dict[str, Any]", commit_raw)
    oid_raw: object = commit.get("oid")
    if isinstance(oid_raw, str) and oid_raw:
        return oid_raw
    return None
