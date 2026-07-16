"""Argv builders for the Dispatcher planning layer."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro.commands import _jsonc

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import DispatchPlan

__all__: list[str] = [
    "CODEX_IMPLEMENTER_ADAPTER",
    "FleetMembers",
    "fabro_events_argv",
    "fabro_inspect_argv",
    "fabro_ps_argv",
    "fabro_rm_argv",
    "fabro_run_argv",
    "janitor_argv_with_default",
    "janitor_bootstrap_argv",
    "janitor_checkout_path",
    "janitor_core_checkout_path",
    "janitor_core_clone_argv",
    "janitor_core_ref_from_config",
    "janitor_trust_argv",
    "janitor_worktree_add_argv",
    "janitor_worktree_remove_argv",
    "parse_fleet_members",
    "pr_arm_argv",
    "pr_update_branch_argv",
    "pr_view_argv",
    "pull_primary_argv",
]

_DEFAULT_JANITOR: tuple[str, ...] = ("mise", "exec", "--", "just", "check")
_DEFAULT_JANITOR_CORE_REPO_URL = "https://github.com/thewoolleyman/livespec.git"
_DEFAULT_JANITOR_CORE_REF = "master"


# The Codex ACP adapter the implementer nodes (implement/fix/pr/review_fix)
# run on. VERSION-FREE + fetch-free: `--no-install` runs the codex-acp
# GLOBAL baked into the sandbox image (livespec-dev-tooling's base
# Dockerfile `ARG CODEX_ACP_VERSION`) with NO npm registry round-trip — it
# runs even under `--network none`, so the baked image's CODEX_ACP_VERSION
# is the SINGLE source of truth for the adapter version (no orchestrator-side
# pin to keep in sync). The non-rotatable refresh sentinel's
# load-but-cannot-refresh behavior (project_codex_auth_snapshot; tracked by
# bd-ib-ss7rkr) is RE-VERIFIED on every version change by the Codex-mode
# golden-master at orchestrator-image/acceptance-live-golden-master.sh, which
# dispatches via `dispatcher.py loop` and always routes implementer nodes to
# THIS adapter — so a factory-gated CODEX_ACP_VERSION bump exercises the
# credential projection end-to-end instead of relying on a manual TODO.
CODEX_IMPLEMENTER_ADAPTER = "npx --no-install @zed-industries/codex-acp"

# GitHub owner / repo-name shape. The matched values are spliced into
# prepare-step clone scripts, so anything outside this conservative
# alphabet is refused at parse time (fail-fast over fail-soft: the
# fleet manifest is a tightly-owned committed file on livespec master,
# and a malformed member is a real problem to surface, not skip).
_GITHUB_SLUG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True, kw_only=True)
class FleetMembers:
    """Owner + member repo names parsed from livespec's .livespec-fleet-manifest.jsonc.

    The fleet manifest (livespec non-functional-requirements.md) is the
    canonical family member registry; the
    `class` field of each member is irrelevant here — every member gets
    a sandbox sibling clone, so any future cross-repo check resolves.
    """

    owner: str
    repos: tuple[str, ...]


def parse_fleet_members(*, manifest_text: str) -> FleetMembers | None:
    """Parse .livespec-fleet-manifest.jsonc text into FleetMembers; None when malformed.

    Accepts the committed shape on livespec master: a JSONC object with
    a string `owner` and a non-empty `fleet` list of objects each
    carrying a string `repo`. The livespec v148 rename made `fleet` the
    canonical key; the pre-rename `members` key is accepted as a fallback
    (matching livespec-dev-tooling's `(.fleet // .members)` parser) so a
    not-yet-migrated manifest copy keeps resolving. Owner and repo values
    must be GitHub-slug-shaped (they are spliced into clone scripts). Any
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
    fleet_raw: object = parsed.get("fleet")
    members_raw: object = fleet_raw if fleet_raw is not None else parsed.get("members")
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


def janitor_argv_with_default(*, janitor: tuple[str, ...] | None) -> tuple[str, ...]:
    """Return the configured janitor argv, defaulting to `mise exec -- just check`."""
    if janitor is None or len(janitor) == 0:
        return _DEFAULT_JANITOR
    return janitor


def janitor_checkout_path(*, repo: Path, work_item_id: str) -> Path:
    """The post-merge janitor's fresh-checkout venue under the family worktree root.

    The checkout must stay outside the target repo so a stray `git add -A`
    cannot stage it. It also stays out of the system temp dir: the family
    pyproject's `[tool.coverage.run]` omit carries `/tmp/*` (a guard
    against measured tempfile artifacts that must stay), so a /tmp venue
    omits every source file inside the checkout — coverage measures zero
    files and check-per-file-coverage dies with NoDataError, false-redding
    a merged-green change (work-item livespec-impl-beads-1l6; reproduced
    in the preserved tpu checkout). `git worktree add` creates the missing
    parent dirs itself.
    """
    return Path.home() / ".worktrees" / repo.name / f"janitor-{work_item_id}"


def janitor_core_checkout_path(*, janitor_checkout: Path) -> Path:
    """Livespec core clone provisioned inside the fresh janitor checkout."""
    return janitor_checkout / ".livespec-core"


def janitor_core_ref_from_config(*, config_text: str) -> str:
    """Resolve the livespec core ref pinned by the target repo config."""
    try:
        parsed_raw: object = _jsonc.loads(text=config_text)
    except _jsonc.JsoncParseError:
        return _DEFAULT_JANITOR_CORE_REF
    if not isinstance(parsed_raw, dict):
        return _DEFAULT_JANITOR_CORE_REF
    parsed = cast("dict[str, object]", parsed_raw)
    plugin_raw: object = parsed.get("livespec-orchestrator-beads-fabro")
    if not isinstance(plugin_raw, dict):
        return _DEFAULT_JANITOR_CORE_REF
    compat_raw: object = cast("dict[str, object]", plugin_raw).get("compat")
    if not isinstance(compat_raw, dict):
        return _DEFAULT_JANITOR_CORE_REF
    pinned_raw: object = cast("dict[str, object]", compat_raw).get("pinned")
    if not isinstance(pinned_raw, str) or pinned_raw.strip() == "":
        return _DEFAULT_JANITOR_CORE_REF
    return pinned_raw.strip()


def fabro_run_argv(*, plan: DispatchPlan) -> list[str]:
    # `--input acp_adapter=...` statically routes the implementer nodes
    # (implement/fix/pr/review_fix) to the Codex ACP adapter; the review
    # node uses its own `review_adapter` default (Slice A) and is
    # unaffected. The dual-credential overlay projects the matching
    # auth.json so the adapter authenticates from the host snapshot.
    return [
        plan.fabro_bin,
        "run",
        str(plan.workflow_toml),
        "--goal-file",
        str(plan.goal_file),
        "--input",
        f"acp_adapter={CODEX_IMPLEMENTER_ADAPTER}",
        "--input",
        f"review_fix_visit_cap={plan.review_fix_visit_cap}",
        "--input",
        f"merge_on_review_cap_outcome={plan.merge_on_review_cap_outcome}",
        "--no-upgrade-check",
    ]


def fabro_inspect_argv(*, plan: DispatchPlan, run_id: str) -> list[str]:
    return [plan.fabro_bin, "inspect", run_id, "--json"]


def fabro_events_argv(*, plan: DispatchPlan, run_id: str) -> list[str]:
    """`fabro events <run-id> --json`: the per-run event log (liveness source).

    The watchdog reads the maximum event timestamp here as its coarse
    liveness signal (work-item livespec-impl-beads-oyg); a stream that
    flatlines for the full stall window is the confirmed-stall signal.
    """
    return [plan.fabro_bin, "events", run_id, "--json"]


def fabro_ps_argv(*, plan: DispatchPlan) -> list[str]:
    """`fabro ps -a --json`: per-run metadata used to discover the run id.

    The watchdog cannot read the run id from the still-blocking `fabro
    run` output, so it discovers the in-flight run for this dispatch from
    `fabro ps` (matched on the work-item id embedded in the run's goal
    text plus a `running` status — see `parse_running_run_id`).
    """
    return [plan.fabro_bin, "ps", "-a", "--json"]


def fabro_rm_argv(*, plan: DispatchPlan, run_id: str) -> list[str]:
    """`fabro rm -f <run-id>`: force-cancel a confirmed-stalled run.

    The watchdog calls this on a confirmed sustained-no-progress stall to
    free the slot + stop the spend (the manual `fabro rm` a human had to
    do at 152min in the 7us.6 incident, now mechanized).
    """
    return [plan.fabro_bin, "rm", "-f", run_id]


def pr_view_argv(*, plan: DispatchPlan) -> list[str]:
    return [
        "gh",
        "pr",
        "view",
        plan.branch,
        "--json",
        "number,state,autoMergeRequest,mergeStateStatus,mergeCommit,statusCheckRollup",
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
        "sh",
        "-lc",
        (
            'branch="$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null '
            '|| printf master)"; branch="${branch#origin/}"; '
            'git -C "$1" pull --ff-only origin "$branch"'
        ),
        "pull-primary",
        str(plan.repo),
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


def janitor_core_clone_argv(*, plan: DispatchPlan) -> list[str]:
    """Clone livespec core inside the fresh janitor checkout."""
    return [
        "git",
        "clone",
        "--quiet",
        "--depth",
        "1",
        "--branch",
        plan.janitor_core_ref,
        plan.janitor_core_repo_url,
        str(plan.janitor_core_checkout),
    ]


def janitor_trust_argv() -> list[str]:
    """Trust the janitor checkout's mise config (run with cwd=checkout).

    mise trust is per-PATH, so a freshly provisioned checkout is never
    pre-trusted and the default janitor's `mise exec` would refuse to
    run there. With no config file present, `mise trust` warns and
    exits 0, so this is safe to run unconditionally.
    """
    return ["mise", "trust"]


def janitor_bootstrap_argv() -> list[str]:
    """Install canonical commit-refuse hooks in the primary checkout (run with cwd=plan.repo).

    Runs the hooks-only bootstrap recipe in the primary checkout so
    the canonical pre-commit and pre-push hooks are present at
    `.git/hooks/` before `just check` runs in the janitor worktree - the shared
    `check-primary-checkout-commit-refuse-hook-installed` gate reads
    the same hooks_dir and fails when the bootstrap step was never run.
    Idempotent: safe to run on every dispatch.
    """
    return ["mise", "exec", "--", "just", "install-commit-refuse-hooks"]
