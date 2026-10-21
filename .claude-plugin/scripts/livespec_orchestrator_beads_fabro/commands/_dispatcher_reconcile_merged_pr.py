"""Merged-PR resolution for the reconcile-merged operator valve.

Split out of `_dispatcher_reconcile_merged` along its cohesion seam: that
module is the command supervisor (preflight, journal, janitor, acceptance,
outcome), while this one answers a single question — WHICH merged pull request
belongs to this stranded work-item — and owns the two `gh` shapes and the
parsing that answer needs.

The answer is deliberately three-valued: a `PrView` when exactly one merged PR
matches, a refusal STRING when none does and the reason can be stated — several
candidates, so reconciling would pick one (reconciling against the wrong merge
is worse than not reconciling), or a factory branch carrying a pull request that
is not a merge — and `None` when the forge said only that it found nothing.
"""

from __future__ import annotations

from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import run_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    parse_pr_view,
)
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "merged_pr_list_argv",
    "parse_merged_pr_list",
    "resolve_merged_pr",
]

_GH_TIMEOUT_SECONDS = 120.0


def resolve_merged_pr(
    *, plan: DispatchPlan, item: WorkItem, runner: CommandRunner, journal: JournalFile
) -> PrView | str | None:
    """Resolve the merged PR for `item`: a view, a refusal string, or `None`."""
    viewed = run_stage(
        runner=runner,
        journal=journal,
        plan=plan,
        stage="reconcile-pr-view-branch",
        command=(_pr_view_branch_argv(plan=plan), plan.repo, _GH_TIMEOUT_SECONDS, None),
    )
    # A branch read that resolves a MERGED pull request IS the answer; every other
    # reading falls through to the item-id search below, including a successful read
    # of a pull request that is open or closed. This arm used to be terminal
    # whenever `gh` exited 0, which made the search unreachable for the one case it
    # exists to serve: an item landed by a host route on a DIFFERENT branch, while
    # its factory branch carries an unmerged pull request of its own. The merge was
    # one search away and the valve reported that none existed.
    unmerged_state: str | None = None
    if viewed.exit_code == 0:
        branch_reading = _branch_pr_view(stdout=viewed.stdout)
        if isinstance(branch_reading, PrView):
            return branch_reading
        unmerged_state = branch_reading
    # The base branch is read off the plan's ONE resolved contract. Pinning the
    # search to a branch name this fleet happens to use searched an adopter's
    # forge for merges onto a branch they do not have -- a clean, plausible,
    # empty result, reported as "no merged PR belongs to this item".
    default_branch = plan.integration.contract.default_branch
    searched = run_stage(
        runner=runner,
        journal=journal,
        plan=plan,
        stage="reconcile-pr-list-merged",
        command=(
            merged_pr_list_argv(item=item, default_branch=default_branch),
            plan.repo,
            _GH_TIMEOUT_SECONDS,
            None,
        ),
    )
    candidates = parse_merged_pr_list(
        stdout=searched.stdout,
        item=item,
        branch=plan.branch,
        default_branch=default_branch,
    )
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        return _ambiguous_pr_detail(candidates=candidates)
    if unmerged_state is not None:
        return _unmerged_branch_detail(
            item=item, branch=plan.branch, state=unmerged_state, default_branch=default_branch
        )
    return None


def merged_pr_list_argv(*, item: WorkItem, default_branch: str) -> list[str]:
    """Build the GitHub search argv used when branch lookup is unavailable.

    `default_branch` is the RESOLVED default branch of the governed repository,
    never a branch name this fleet happens to use: the search pins `--base`, so a
    constant there asks an adopter's forge about merges onto a branch they do not
    have and gets an empty, error-free, wrong answer.
    """
    return [
        "gh",
        "pr",
        "list",
        "--state",
        "merged",
        "--search",
        item.id,
        "--json",
        "number,title,body,headRefName,baseRefName,state,mergeCommit",
        "--base",
        default_branch,
        "--limit",
        "20",
    ]


def parse_merged_pr_list(
    *, stdout: str, item: WorkItem, branch: str, default_branch: str
) -> tuple[PrView, ...]:
    """Parse merged PR search results, tiering body mentions below identity matches.

    A candidate merged onto some OTHER base than `default_branch` is rejected,
    which is what stops a reconcile from disposing an item against a merge into
    someone's long-lived side branch. The branch it compares against is resolved
    for the same reason the search's own `--base` is.

    The two tiers are NOT peers, and the ordering is the resolution rule rather
    than a preference. `--search <id>` matches bodies server-side, so an ordinary
    merge that merely MENTIONS the item — a follow-up, a revert, a sibling slice
    naming its predecessor — comes back beside the pull request that carries it.
    Counting both at once turns a clean title match into an ambiguity refusal:
    measured over this repository's 400 most recent merges onto master, thirteen
    ids fall through to this search and have exactly one title/head match plus at
    least one body-only mention. So a body match is consulted ONLY when no
    candidate identifies itself by the dispatch branch or by its title.
    """
    parsed_raw = parse_json(text=stdout)
    if isinstance(parsed_raw, JsonParseFailure) or not isinstance(parsed_raw, list):
        return ()
    identified: list[PrView] = []
    mentioned: list[PrView] = []
    for entry_raw in cast("list[object]", parsed_raw):
        candidate = _pr_view_from_list_entry(
            entry_raw=entry_raw, item=item, branch=branch, default_branch=default_branch
        )
        if candidate is None:
            continue
        view, body_only = candidate
        if body_only:
            mentioned.append(view)
        else:
            identified.append(view)
    return tuple(identified) if identified else tuple(mentioned)


def _ambiguous_pr_detail(*, candidates: tuple[PrView, ...]) -> str:
    listed = ", ".join(f"#{candidate.number} {candidate.merge_sha}" for candidate in candidates)
    return f"ERROR: ambiguous merged PR candidates for reconcile-merged: {listed}\n"


def _pr_view_branch_argv(*, plan: DispatchPlan) -> list[str]:
    return [
        "gh",
        "pr",
        "view",
        plan.branch,
        "--json",
        "number,state,autoMergeRequest,mergeStateStatus,mergeCommit,statusCheckRollup",
    ]


def _branch_pr_view(*, stdout: str) -> PrView | str:
    """The branch read's merged pull request, or the STATE that is not one.

    Every string arm is a REACHABLE reading rather than a defensive one -- a
    factory branch routinely carries an open or closed pull request -- and the
    whole set carried a single `no cover` pragma until `bd-ib-sz2eal`, which
    labelled the live path as unreachable and hid the fall-through it now takes.

    The four readings are NAMED rather than collapsed into one word, because the
    refusal downstream is the only thing that tells an operator which situation
    they are in and the four have different remedies. `gh` output nobody can
    parse is a diagnostic about the forge CALL rather than about the pull
    request, and a `MERGED` pull request carrying no merge commit is a reading no
    acceptance may be keyed on -- so neither may read as a plain state word, and
    neither may read as the other.
    """
    view = parse_pr_view(stdout=stdout)
    if view is None:
        return "unreadable JSON"
    if view.state != "MERGED":
        return view.state
    if view.merge_sha is None:
        return "MERGED with no merge commit"
    return view


def _unmerged_branch_detail(*, item: WorkItem, branch: str, state: str, default_branch: str) -> str:
    """Refuse an item whose branch pull request is not a merge and whose id matches none.

    The SEARCH is named by the argv that was actually run rather than by a
    sentence claiming one happened: an absence asserted over an unstated
    population is a claim no reader can re-run, and this valve exists to
    establish a merge from the forge rather than to be told about one.
    """
    searched = " ".join(merged_pr_list_argv(item=item, default_branch=default_branch))
    return (
        f"ERROR: no merged PR found for work-item {item.id}: the pull request on "
        f"{branch} reads {state}, and the item-id search over merges onto "
        f"{default_branch} named none. Searched: {searched}\n"
    )


def _pr_view_from_list_entry(
    *, entry_raw: object, item: WorkItem, branch: str, default_branch: str
) -> tuple[PrView, bool] | None:
    """Return one candidate view plus whether ONLY its body named the item."""
    if not isinstance(entry_raw, dict):
        return None
    entry = cast("dict[str, Any]", entry_raw)
    number_raw: object = entry.get("number")
    state_raw: object = entry.get("state")
    if not isinstance(number_raw, int) or state_raw != "MERGED":
        return None
    base_raw: object = entry.get("baseRefName")
    if isinstance(base_raw, str) and base_raw != default_branch:
        return None
    identified = _identifies_item(entry=entry, item=item, branch=branch)
    if not identified and not _body_names_item(entry=entry, item=item):
        return None
    merge_sha = _list_entry_merge_sha(entry=entry)
    if merge_sha is None:
        return None
    return (
        PrView(
            number=number_raw,
            state="MERGED",
            auto_merge_armed=False,
            merge_state_status="UNKNOWN",
            merge_sha=merge_sha,
            terminal_required_check_failures=(),
        ),
        not identified,
    )


def _identifies_item(*, entry: dict[str, Any], item: WorkItem, branch: str) -> bool:
    """Whether the entry names the item where a dispatch or an author puts it."""
    title_raw: object = entry.get("title")
    return entry.get("headRefName") == branch or (
        isinstance(title_raw, str) and item.id in title_raw
    )


def _body_names_item(*, entry: dict[str, Any], item: WorkItem) -> bool:
    body_raw: object = entry.get("body")
    return isinstance(body_raw, str) and item.id in body_raw


def _list_entry_merge_sha(*, entry: dict[str, Any]) -> str | None:
    commit_raw: object = entry.get("mergeCommit")
    if not isinstance(commit_raw, dict):
        return None  # pragma: no cover - defensive malformed gh JSON
    oid_raw: object = cast("dict[str, Any]", commit_raw).get("oid")
    return oid_raw if isinstance(oid_raw, str) and oid_raw else None
