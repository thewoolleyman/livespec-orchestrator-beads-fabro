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

The run-config helper (`render_run_config_overlay`) materializes the
RUN-SCOPED credential projection (the family-secrets scoped
transient-materialization rule): the committed config carries NO
secret, and the rendered overlay appends an `[environments.<id>.env]`
table carrying the CLAUDE_CODE_OAUTH_TOKEN value the caller read from
the Dispatcher's process environment, alongside the `graph` path
rewritten absolute so the overlay resolves from outside the workflow
directory. The same overlay provisions the sandbox sibling clones:
per-fleet-member depth-1 `[[run.prepare.steps]]` clone blocks plus the
non-secret `LIVESPEC_SIBLING_CLONES_ROOT` env key (riding in the same
appended env table — TOML allows only one declaration of that table),
so cross-repo checks under `just check` resolve family siblings inside
the sandbox exactly like livespec CI provisions them.

Fabro `{{ env.* }}` interpolation can NOT carry the
credential for server-mediated runs — do not re-attempt it: the
interpolation resolves in the WORKER process, which fabro-server
spawns with a fail-closed env allowlist (fabro-server/src/spawn_env.rs
— PATH/HOME/TMPDIR/USER/RUST_*/FABRO_*/TERM etc. only), so the token
never reaches the resolver and the LITERAL `{{ env.X }}` string flows
into the sandbox (proven empirically 2026-06-12: API 401 with the
token present in both the dispatcher's and the server daemon's env).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from livespec_impl_beads.commands import _jsonc
from livespec_impl_beads.types import WorkItem

if TYPE_CHECKING:
    from livespec_impl_beads.store import WorkItemComment

__all__: list[str] = [
    "SIBLING_CLONES_ROOT_ENV_VAR",
    "DispatchPlan",
    "FleetMembers",
    "PrView",
    "SiblingClones",
    "build_plan",
    "fabro_inspect_argv",
    "fabro_run_argv",
    "item_sizing_warnings",
    "janitor_argv_with_default",
    "janitor_trust_argv",
    "janitor_worktree_add_argv",
    "janitor_worktree_remove_argv",
    "parse_fleet_members",
    "parse_pr_view",
    "parse_run_id",
    "parse_run_status",
    "pr_arm_argv",
    "pr_update_branch_argv",
    "pr_view_argv",
    "pull_primary_argv",
    "render_goal",
    "render_run_config_overlay",
]

# The env-var contract shared with livespec's cross-repo doctor checks
# (e.g. `wiring_completeness_cross_repo`): when set, a sibling repo's
# clone resolves as `<value>/<sibling-slug>` instead of the manifest's
# `local_clone` path. livespec CI provisions it the same way; the
# Dispatcher's overlay projects it into the sandbox env table.
SIBLING_CLONES_ROOT_ENV_VAR = "LIVESPEC_SIBLING_CLONES_ROOT"

_DEFAULT_JANITOR: tuple[str, ...] = ("mise", "exec", "--", "just", "check")

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
_RUN_ID_RE = re.compile(r"Run:\s*([0-9A-Za-z-]+)")

# GitHub owner / repo-name shape. The matched values are spliced into
# prepare-step clone scripts, so anything outside this conservative
# alphabet is refused at parse time (fail-fast over fail-soft: the
# fleet manifest is a tightly-owned committed file on livespec master,
# and a malformed member is a real problem to surface, not skip).
_GITHUB_SLUG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True, kw_only=True)
class DispatchPlan:
    """Everything one work-item dispatch needs, resolved up front.

    `branch` is the PUBLISH branch (`feat/<work-item-id>`) the phase
    graph's pr stage pushes and the engine polls — the Fabro-managed
    run branch inside the sandbox is run-internal and never leaves it.
    `workflow_toml` is the MATERIALIZED run-config overlay path (the
    committed config plus the credential env table), not the committed
    file itself. `janitor_checkout` is the path the engine provisions
    as a FRESH detached worktree of the merged ref and runs the
    post-merge janitor in — never the host primary's working tree,
    whose environment rot (stale `.venv` shebangs, stale `.coverage`,
    ghost `__pycache__` dirs) once false-redded a confirmed-green
    merge (work-item livespec-impl-beads-cgd).
    """

    repo: Path
    work_item_id: str
    branch: str
    workflow_toml: Path
    goal_file: Path
    fabro_bin: str
    janitor: tuple[str, ...]
    janitor_checkout: Path


@dataclass(frozen=True, kw_only=True)
class PrView:
    """The slice of `gh pr view --json` the engine routes on."""

    number: int
    state: str
    auto_merge_armed: bool
    merge_state_status: str
    merge_sha: str | None


@dataclass(frozen=True, kw_only=True)
class FleetMembers:
    """Owner + member repo names parsed from livespec's fleet-manifest.jsonc.

    The fleet manifest (livespec non-functional-requirements.md §"Fleet
    membership contract") is the canonical family member registry; the
    `class` field of each member is irrelevant here — every member gets
    a sandbox sibling clone, so any future cross-repo check resolves.
    """

    owner: str
    repos: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class SiblingClones:
    """The per-dispatch sandbox sibling-clone plan.

    `repos` is the fleet member set MINUS the dispatch target (the
    target is already the sandbox workspace clone); `clones_root` is
    the in-sandbox directory the clones land under — the same path the
    overlay projects as `LIVESPEC_SIBLING_CLONES_ROOT`.
    """

    owner: str
    repos: tuple[str, ...]
    clones_root: str


def parse_fleet_members(*, manifest_text: str) -> FleetMembers | None:
    """Parse fleet-manifest.jsonc text into FleetMembers; None when malformed.

    Accepts the committed shape on livespec master: a JSONC object with
    a string `owner` and a non-empty `members` list of objects each
    carrying a string `repo`. Owner and repo values must be
    GitHub-slug-shaped (they are spliced into clone scripts). Any
    deviation yields None — the caller refuses the dispatch with an
    actionable error rather than cloning from a guessed member list.
    """
    try:
        parsed_raw: object = _jsonc.loads(text=manifest_text)
    except _jsonc.JsoncParseError:
        return None
    if not isinstance(parsed_raw, dict):
        return None
    parsed = cast("dict[str, Any]", parsed_raw)
    owner_raw: object = parsed.get("owner")
    members_raw: object = parsed.get("members")
    if not isinstance(owner_raw, str) or not isinstance(members_raw, list):
        return None
    if _GITHUB_SLUG_PATTERN.match(owner_raw) is None:
        return None
    repos: list[str] = []
    for member_raw in cast("list[object]", members_raw):
        repo_name = _parse_member_repo(member_raw=member_raw)
        if repo_name is None:
            return None
        repos.append(repo_name)
    return FleetMembers(owner=owner_raw, repos=tuple(repos)) if repos else None


def _parse_member_repo(*, member_raw: object) -> str | None:
    """Extract a validated repo name from one fleet-manifest member entry."""
    if not isinstance(member_raw, dict):
        return None
    repo_raw: object = cast("dict[str, Any]", member_raw).get("repo")
    if not isinstance(repo_raw, str) or _GITHUB_SLUG_PATTERN.match(repo_raw) is None:
        return None
    return repo_raw


def build_plan(  # noqa: PLR0913 — kw-only plan resolver; each field is an independent caller input.
    *,
    repo: Path,
    work_item_id: str,
    workflow_toml: Path,
    goal_file: Path,
    fabro_bin: str,
    janitor: tuple[str, ...] | None,
    janitor_checkout: Path,
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
        janitor_checkout=janitor_checkout,
    )


def janitor_argv_with_default(*, janitor: tuple[str, ...] | None) -> tuple[str, ...]:
    """Return the configured janitor argv, defaulting to `mise exec -- just check`."""
    if janitor is None or len(janitor) == 0:
        return _DEFAULT_JANITOR
    return janitor


def render_goal(
    *,
    item: WorkItem,
    repo: Path,
    branch: str,
    comments: tuple[WorkItemComment, ...] = (),
) -> str:
    """Render the per-item brief delivered to the phase graph as the run goal.

    Item specifics ONLY: the durable family discipline (Red-Green-Replay,
    hook rules, PR/merge protocol) lives in the versioned prompt files of
    the phase graph, not here. `comments` are the item's ledger comments
    (operator riders appended after filing — e.g. pre-authorizations);
    they render under a labeled section so they reach the sandbox brief
    (bn4 finding (c): the description-only brief silently dropped them).
    """
    gap_line = f"Gap id: {item.gap_id}\n" if item.gap_id is not None else ""
    base = (
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
    if not comments:
        return base
    lines = [
        "",
        "Ledger comments (operator riders appended after filing; treat them as part of the brief):",
    ]
    for index, comment in enumerate(comments, start=1):
        lines.append(f"[{index}] {_comment_entry(comment=comment)}")
    return base + "\n".join(lines) + "\n"


def _comment_entry(*, comment: WorkItemComment) -> str:
    """Format one rider as `(author, created_at) text`, dropping absent parts."""
    provenance = ", ".join(
        part for part in (comment.author, comment.created_at) if part is not None
    )
    if provenance == "":
        return comment.text
    return f"({provenance}) {comment.text}"


# Sizing heuristics (warn-only; see `item_sizing_warnings`). Calibrated on
# the 2026-06-12 shakedown evidence: the two ACP-turn-timeout casualties
# (dev-tooling p60, git-jsonl tenpup) were both heavy multi-part /
# multi-RGR items with long enumerated descriptions, and both succeeded
# immediately once split out to host sub-agents.
_SIZING_DESCRIPTION_CHAR_LIMIT = 1500
_SIZING_PART_MARKER_RE = re.compile(r"multi[-\s]?(?:part|rgr)", re.IGNORECASE)
_SIZING_ENUMERATED_RE = re.compile(r"\(\d+\)|^\s*\d+[.)]\s", re.MULTILINE)
_SIZING_ENUMERATED_LIMIT = 3


def item_sizing_warnings(*, item: WorkItem) -> tuple[str, ...]:
    """Warn-only sizing heuristics applied at dispatch/loop-feed time.

    Pure function of the item; the Dispatcher journals + stderr-WARNs the
    hits and proceeds regardless (never blocking). Three heuristics:
    description length, explicit multi-part/multi-RGR markers, and
    enumerated part counts.
    """
    warnings: list[str] = []
    if len(item.description) > _SIZING_DESCRIPTION_CHAR_LIMIT:
        length_warning = (
            f"description is {len(item.description)} chars "
            f"(> {_SIZING_DESCRIPTION_CHAR_LIMIT}): heavy items have exceeded one "
            "unattended ACP turn; consider splitting before loop-feeding"
        )
        warnings.append(length_warning)
    if _SIZING_PART_MARKER_RE.search(f"{item.title}\n{item.description}") is not None:
        marker_warning = (
            "title/description carries a multi-part/multi-RGR marker: such items "
            "have exceeded one unattended ACP turn; consider splitting"
        )
        warnings.append(marker_warning)
    enumerated = len(_SIZING_ENUMERATED_RE.findall(item.description))
    if enumerated >= _SIZING_ENUMERATED_LIMIT:
        enumerated_warning = (
            f"description carries {enumerated} enumerated parts: consider one "
            "work-item per part before loop-feeding"
        )
        warnings.append(enumerated_warning)
    return tuple(warnings)


def render_run_config_overlay(
    *,
    committed_text: str,
    workflow_dir: Path,
    token: str,
    siblings: SiblingClones | None,
) -> str | None:
    """Render the dispatch-time run-config overlay (pure string transform).

    The overlay is the RUN-SCOPED credential projection (per the
    family-secrets scoped transient-materialization rule): the committed
    config with (a) the `[workflow]` graph path rewritten to an absolute
    path (the materialized file lives outside the workflow directory, so
    a relative graph would not resolve), (b) appended sibling-clone
    `[[run.prepare.steps]]` blocks (when `siblings` is not None) so
    cross-repo checks resolve family siblings inside the sandbox, and
    (c) an appended `[environments.<id>.env]` table carrying the
    CLAUDE_CODE_OAUTH_TOKEN value read from the Dispatcher's process
    environment plus the NON-secret `LIVESPEC_SIBLING_CLONES_ROOT` key.
    The non-secret key rides in the credential table because TOML
    forbids a second declaration of the same table and this appended
    table is the single `[environments.<id>.env]` declaration point —
    the committed file deliberately carries none; the table maps to
    docker container-level env (fabro-sandbox), so the value reaches
    every node's `just check` subprocesses.

    The committed file itself carries NO secret and NO `{{ env }}`
    interpolation — interpolation cannot deliver the credential to
    server-mediated runs, because the server spawns the resolving
    worker with a fail-closed env allowlist
    (fabro-server/src/spawn_env.rs); see the module docstring. The
    caller writes the rendered text mode-600 and deletes it when the
    run returns. Returns None when the committed shape is unusable (no
    canonical graph value or no run-environment id).
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
    sibling_steps = "" if siblings is None else _sibling_clone_steps_block(siblings=siblings)
    sibling_env_line = (
        ""
        if siblings is None
        else f"{SIBLING_CLONES_ROOT_ENV_VAR} = {json.dumps(siblings.clones_root)}\n"
    )
    return (
        rewritten
        + sibling_steps
        + "\n# --- Dispatcher-materialized run-scoped credential projection"
        + "\n# --- (UNCOMMITTED; mode 600; deleted when the run returns) ---\n"
        + f"[environments.{environment_id}.env]\n"
        + f"CLAUDE_CODE_OAUTH_TOKEN = {token_literal}\n"
        + sibling_env_line
    )


def _sibling_clone_steps_block(*, siblings: SiblingClones) -> str:
    """Render the appended sibling-clone `[[run.prepare.steps]]` blocks.

    One step per fleet member (the dispatch target is excluded
    upstream): a depth-1 default-branch `git clone` into
    `<clones_root>/<repo>` — mirroring how livespec CI provisions the
    `LIVESPEC_SIBLING_CLONES_ROOT` siblings-root for the cross-repo
    wiring check. Plain `git clone` over https is used (NOT `gh`): the
    sandbox clones its own workspace repo the same way, while `gh api`
    is unauthenticated there.
    """
    lines: list[str] = [
        "",
        "# --- Dispatcher-materialized sibling clones (from livespec master's",
        "# --- fleet-manifest.jsonc): depth-1 default-branch clones so",
        "# --- cross-repo checks resolve every family sibling under",
        f"# --- {siblings.clones_root} inside the sandbox ---",
    ]
    for repo_name in siblings.repos:
        script = (
            f"mkdir -p {siblings.clones_root} && git clone --quiet --depth 1"
            f" https://github.com/{siblings.owner}/{repo_name}.git"
            f" {siblings.clones_root}/{repo_name}"
        )
        lines.append("[[run.prepare.steps]]")
        lines.append(f"script = {json.dumps(script)}")
    return "\n".join(lines) + "\n"


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


def janitor_worktree_add_argv(*, plan: DispatchPlan, ref: str) -> list[str]:
    """Provision the fresh detached janitor checkout at the merged ref.

    Plain `git` (no `mise exec`): worktree commands fire no hooks and
    need no pinned toolchain, and the checkout path is not yet
    mise-trusted at this point anyway.
    """
    return [
        "git",
        "-C",
        str(plan.repo),
        "worktree",
        "add",
        "--detach",
        str(plan.janitor_checkout),
        ref,
    ]


def janitor_worktree_remove_argv(*, plan: DispatchPlan) -> list[str]:
    """Remove the janitor checkout (both pre-clean and post-green cleanup).

    `--force` covers the untracked state a janitor run leaves behind
    (the self-provisioned `.venv`), and as the pre-clean it also clears
    a stale registration left by a crashed earlier dispatch of the same
    item.
    """
    return [
        "git",
        "-C",
        str(plan.repo),
        "worktree",
        "remove",
        "--force",
        str(plan.janitor_checkout),
    ]


def janitor_trust_argv() -> list[str]:
    """Trust the janitor checkout's mise config (run with cwd=checkout).

    mise trust is per-PATH, so a freshly provisioned checkout is never
    pre-trusted and the default janitor's `mise exec` would refuse to
    run there. With no config file present, `mise trust` warns and
    exits 0, so this is safe to run unconditionally.
    """
    return ["mise", "trust"]


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
