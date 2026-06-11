"""Pure planning layer for the Dispatcher: plans, argv builders, parsers.

Everything here is a pure function of its inputs so the hermetic test
tier covers the Dispatcher's decision surface without subprocesses. The
side-effecting execution of these argvs lives in `_dispatcher_engine`
(sequencing) and `_dispatcher_io` (the subprocess seam).

The argv builders encode the Architecture C dispatch discipline
(livespec non-functional-requirements.md §"Orchestrator-internal
Dispatcher guidance" + livespec/tmp/fabro-architecture-c-design.md):
`fabro run` executes from the target repo's PRIMARY checkout and Fabro
clones fresh inside its docker sandbox (the host owns no git working
state — no worktree prep, no reaping), the work publishes under
`feat/<work-item-id>` (never the Fabro-managed run-branch name),
`gh pr view` confirms the merge, and the janitor argv is injected from
configuration (never hardcoded).

The credential-channel helpers (`parse_secrets_file`,
`render_run_config_overlay`) keep the committed run config secret-free:
the Dispatcher materializes an UNCOMMITTED mode-600 overlay at dispatch
time carrying CLAUDE_CODE_OAUTH_TOKEN (Fabro's vault cannot deliver ACP
credentials in v0.254.0), with the `graph` path rewritten absolute so
the overlay resolves from outside the workflow directory.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_impl_beads.types import WorkItem

__all__: list[str] = [
    "DispatchPlan",
    "PrView",
    "build_plan",
    "fabro_inspect_argv",
    "fabro_run_argv",
    "janitor_argv_with_default",
    "parse_pr_view",
    "parse_run_id",
    "parse_run_status",
    "parse_secrets_file",
    "pr_arm_argv",
    "pr_update_branch_argv",
    "pr_view_argv",
    "pull_primary_argv",
    "render_goal",
    "render_run_config_overlay",
]

_DEFAULT_JANITOR: tuple[str, ...] = ("mise", "exec", "--", "just", "check")

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
_RUN_ID_RE = re.compile(r"Run:\s*([0-9A-Za-z-]+)")

# A value shorter than one opening plus one closing quote cannot be
# quote-wrapped.
_MIN_QUOTED_LENGTH = 2


@dataclass(frozen=True, kw_only=True)
class DispatchPlan:
    """Everything one work-item dispatch needs, resolved up front.

    `branch` is the PUBLISH branch (`feat/<work-item-id>`) the phase
    graph's pr stage pushes and the engine polls — the Fabro-managed
    run branch inside the sandbox is run-internal and never leaves it.
    `workflow_toml` is the MATERIALIZED run-config overlay path (the
    committed config plus the credential env table), not the committed
    file itself.
    """

    repo: Path
    work_item_id: str
    branch: str
    workflow_toml: Path
    goal_file: Path
    fabro_bin: str
    janitor: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class PrView:
    """The slice of `gh pr view --json` the engine routes on."""

    number: int
    state: str
    auto_merge_armed: bool
    merge_state_status: str
    merge_sha: str | None


def build_plan(
    *,
    repo: Path,
    work_item_id: str,
    workflow_toml: Path,
    goal_file: Path,
    fabro_bin: str,
    janitor: tuple[str, ...] | None,
) -> DispatchPlan:
    """Resolve the per-item dispatch plan (publish branch, argv config)."""
    return DispatchPlan(
        repo=repo,
        work_item_id=work_item_id,
        branch=f"feat/{work_item_id}",
        workflow_toml=workflow_toml,
        goal_file=goal_file,
        fabro_bin=fabro_bin,
        janitor=janitor_argv_with_default(janitor=janitor),
    )


def janitor_argv_with_default(*, janitor: tuple[str, ...] | None) -> tuple[str, ...]:
    """Return the configured janitor argv, defaulting to `mise exec -- just check`."""
    if janitor is None or len(janitor) == 0:
        return _DEFAULT_JANITOR
    return janitor


def render_goal(*, item: WorkItem, repo: Path, branch: str) -> str:
    """Render the per-item brief delivered to the phase graph as the run goal.

    Item specifics ONLY: the durable family discipline (Red-Green-Replay,
    hook rules, PR/merge protocol) lives in the versioned prompt files of
    the phase graph, not here.
    """
    gap_line = f"Gap id: {item.gap_id}\n" if item.gap_id is not None else ""
    return (
        f"Work-item: {item.id}\n"
        f"Repo: {repo}\n"
        f"Publish branch (push HEAD to this exact ref at the PR stage): {branch}\n"
        f"Priority: P{item.priority}  Type: {item.type}\n"
        f"{gap_line}"
        f"Title: {item.title}\n"
        "\n"
        "Description:\n"
        f"{item.description}\n"
    )


def render_run_config_overlay(
    *,
    committed_text: str,
    workflow_dir: Path,
    token: str,
) -> str | None:
    """Render the dispatch-time run-config overlay (pure string transform).

    The overlay is the committed config with (a) the `[workflow]` graph
    path rewritten to an absolute path (the materialized file lives
    outside the workflow directory, so a relative graph would not
    resolve) and (b) an appended `[environments.<id>.env]` table
    carrying CLAUDE_CODE_OAUTH_TOKEN. Returns None when the committed
    shape is unusable (no graph value or no run-environment id).
    """
    graph_value = _toml_section_string(text=committed_text, section="workflow", key="graph")
    environment_id = _toml_section_string(text=committed_text, section="run.environment", key="id")
    if graph_value is None or environment_id is None:
        return None
    graph_path = Path(graph_value)
    resolved_graph = graph_path if graph_path.is_absolute() else workflow_dir / graph_path
    needle = f'graph = "{graph_value}"'
    if needle not in committed_text:
        return None
    rewritten = committed_text.replace(needle, f'graph = "{resolved_graph}"', 1)
    token_literal = json.dumps(token)
    return (
        rewritten
        + "\n# --- Dispatcher-materialized credential overlay (UNCOMMITTED;"
        + "\n# --- mode 600; deleted when the run returns) ---\n"
        + f"[environments.{environment_id}.env]\n"
        + f"CLAUDE_CODE_OAUTH_TOKEN = {token_literal}\n"
    )


def parse_secrets_file(*, text: str) -> dict[str, str]:
    """Parse a mode-600 env-format secrets file (KEY=value lines).

    Comments, blank lines, and lines without `=` are skipped; a leading
    `export ` and one level of matching quotes around the value are
    stripped. Values are never logged by any caller.
    """
    secrets: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, separator, raw_value = line.partition("=")
        key = key.strip()
        if not separator or not key or " " in key:
            continue
        value = raw_value.strip()
        if len(value) >= _MIN_QUOTED_LENGTH and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        secrets[key] = value
    return secrets


def fabro_run_argv(*, plan: DispatchPlan) -> list[str]:
    return [
        plan.fabro_bin,
        "run",
        str(plan.workflow_toml),
        "--goal-file",
        str(plan.goal_file),
        "--no-upgrade-check",
    ]


def fabro_inspect_argv(*, plan: DispatchPlan, run_id: str) -> list[str]:
    return [plan.fabro_bin, "inspect", run_id, "--json"]


def pr_view_argv(*, plan: DispatchPlan) -> list[str]:
    return [
        "gh",
        "pr",
        "view",
        plan.branch,
        "--json",
        "number,state,autoMergeRequest,mergeStateStatus,mergeCommit",
    ]


def pr_arm_argv(*, plan: DispatchPlan, number: int) -> list[str]:
    _ = plan
    return ["gh", "pr", "merge", str(number), "--rebase", "--auto", "--delete-branch"]


def pr_update_branch_argv(*, plan: DispatchPlan, number: int) -> list[str]:
    _ = plan
    return ["gh", "pr", "update-branch", str(number)]


def pull_primary_argv(*, plan: DispatchPlan) -> list[str]:
    return [
        "mise",
        "exec",
        "--",
        "git",
        "-C",
        str(plan.repo),
        "pull",
        "--ff-only",
        "origin",
        "master",
    ]


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
    try:
        parsed_raw: object = json.loads(stdout)
    except json.JSONDecodeError:
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


def parse_pr_view(*, stdout: str) -> PrView | None:
    """Parse `gh pr view --json` output; None when the shape is unusable."""
    try:
        parsed_raw: object = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed_raw, dict):
        return None
    parsed = cast("dict[str, Any]", parsed_raw)
    number_raw: object = parsed.get("number")
    if not isinstance(number_raw, int):
        return None
    state_raw: object = parsed.get("state")
    state = state_raw if isinstance(state_raw, str) else "UNKNOWN"
    merge_state_raw: object = parsed.get("mergeStateStatus")
    merge_state = merge_state_raw if isinstance(merge_state_raw, str) else "UNKNOWN"
    return PrView(
        number=number_raw,
        state=state,
        auto_merge_armed=parsed.get("autoMergeRequest") is not None,
        merge_state_status=merge_state,
        merge_sha=_merge_sha_of(parsed=parsed),
    )


def _merge_sha_of(*, parsed: dict[str, Any]) -> str | None:
    commit_raw: object = parsed.get("mergeCommit")
    if not isinstance(commit_raw, dict):
        return None
    commit = cast("dict[str, Any]", commit_raw)
    oid_raw: object = commit.get("oid")
    if isinstance(oid_raw, str) and oid_raw:
        return oid_raw
    return None


def _toml_section_string(*, text: str, section: str, key: str) -> str | None:
    """Read one basic-string value from one TOML table, regex-scoped.

    A full TOML parser is unavailable on the pinned Python (tomllib is
    3.11+; the family vendors no TOML library), and the committed run
    config is repo-owned with a stable shape, so a section-scoped regex
    is sufficient and dependency-free.
    """
    section_pattern = re.compile(
        r"(?ms)^\[" + re.escape(section) + r"\][ \t]*\r?$(?P<body>.*?)(?=^\[|\Z)"
    )
    section_match = section_pattern.search(text)
    if section_match is None:
        return None
    key_pattern = re.compile(
        r"(?m)^" + re.escape(key) + r'[ \t]*=[ \t]*"(?P<value>[^"]*)"[ \t]*\r?$'
    )
    key_match = key_pattern.search(section_match.group("body"))
    if key_match is None:
        return None
    return key_match.group("value")
