"""Which check runs a pull request REQUIRES, read from the forge that knows.

`gh pr view --json statusCheckRollup` never says whether an entry is required:
measured on a real pull request, every entry carries exactly `__typename`,
`completedAt`, `conclusion`, `detailsUrl`, `name`, `startedAt`, `status` and
`workflowName`. A fast failure keyed on an `isRequired` key in that output
therefore never fires, and the merge wait polls out its whole budget on a pull
request whose required check is already red.

Required-ness lives on the forge's GraphQL `isRequired(pullRequestNumber:)`
field, which answers from branch protection AND rulesets alike, so this read
needs no knowledge of which of the two a repository uses. An unreadable answer is
`None`, never an empty set: an absent reading must keep the merge wait polling
rather than be mistaken for "nothing is required".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import journal_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_pr_view import GH_TIMEOUT_SECONDS
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandRunner,
        JournalWriter,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan

__all__: list[str] = [
    "parse_required_check_names",
    "required_check_names",
    "required_check_names_argv",
]

_QUERY = (
    "query($owner: String!, $name: String!, $number: Int!) {"
    " repository(owner: $owner, name: $name) {"
    " pullRequest(number: $number) {"
    " commits(last: 1) { nodes { commit { statusCheckRollup {"
    " contexts(first: 100) { nodes {"
    " __typename"
    " ... on CheckRun { name isRequired(pullRequestNumber: $number) }"
    " ... on StatusContext { context isRequired(pullRequestNumber: $number) }"
    " } } } } } } } } }"
)


def required_check_names_argv(*, number: int) -> list[str]:
    """The `gh api graphql` call, repository resolved from the working directory."""
    return [
        "gh",
        "api",
        "graphql",
        "-F",
        "owner=:owner",
        "-F",
        "name=:repo",
        "-F",
        f"number={number}",
        "-f",
        f"query={_QUERY}",
    ]


def required_check_names(
    *,
    plan: DispatchPlan,
    number: int,
    runner: CommandRunner,
    journal: JournalWriter,
) -> frozenset[str] | None:
    """The names of the pull request's required checks; None when they cannot be read."""
    result = runner.run(
        argv=required_check_names_argv(number=number),
        cwd=plan.repo,
        timeout_seconds=GH_TIMEOUT_SECONDS,
    )
    journal_stage(journal=journal, plan=plan, stage="required-checks", result=result)
    if result.exit_code != 0:
        return None
    return parse_required_check_names(stdout=result.stdout)


def parse_required_check_names(*, stdout: str) -> frozenset[str] | None:
    """Parse the GraphQL answer; None when its shape is not the one asked for."""
    parsed = parse_json(text=stdout)
    if isinstance(parsed, JsonParseFailure):
        return None
    contexts: object = parsed
    for key in ("data", "repository", "pullRequest"):
        contexts = _member(value=contexts, key=key)
    commits = _member(value=contexts, key="commits")
    commit_nodes = _member(value=commits, key="nodes")
    if not isinstance(commit_nodes, list) or not commit_nodes:
        return None
    rollup: object = cast("list[object]", commit_nodes)[0]
    for key in ("commit", "statusCheckRollup", "contexts"):
        rollup = _member(value=rollup, key=key)
    nodes = _member(value=rollup, key="nodes")
    if not isinstance(nodes, list):
        return None
    return frozenset(
        name
        for node in cast("list[object]", nodes)
        if _member(value=node, key="isRequired") is True
        for name in [_context_name(node=node)]
        if name is not None
    )


def _member(*, value: object, key: str) -> object:
    if not isinstance(value, dict):
        return None
    return cast("dict[str, Any]", value).get(key)


def _context_name(*, node: object) -> str | None:
    for key in ("name", "context"):
        name = _member(value=node, key=key)
        if isinstance(name, str) and name:
            return name
    return None
