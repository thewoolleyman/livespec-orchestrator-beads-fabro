"""The two FORGE adapters of the shared result reader: pull-request state and blob.

Both ask the forge, from the named repository's own clone, through the one
`CommandRunner` seam this tree shells every subprocess through.

WHY THE BLOB IS ASKED OF THE FORGE RATHER THAN OF A LOCAL CHECKOUT. The
shared-authoritative-result-reader clause of `SPECIFICATION/contracts.md` requires
a file result to compare "the remote branch's blob identity, not a stale checkout
or mere path existence". A local clone need never have fetched the branch, and
when it has, its object for that path is whatever its last fetch left — so a
`git rev-parse` against a local ref answers a question about this host's fetch
state and reports it as a fact about the branch. The forge's contents endpoint
returns the blob sha for the path AT the named ref, which is the identity the
clause names, and it removes the local checkout from the question entirely.

WHY BOTH ADAPTERS LIVE HERE AND THE PROOF ADAPTER DOES NOT. These two are a
single `gh` call each and nothing else; the typed proof read has to resolve a
subject through the ledger first and then validate a record's semantics, which is
a different concern and a different set of imports. The SOURCE each reports
still differs — a pull-request state is forge state, a blob is a Git object — and
that is a property of the evidence rather than of the transport.

WHY THE STATE COMPARISON IS CASE-FOLDED AND THE BLOB COMPARISON IS NOT. The forge
renders pull-request state in upper case and an operator writes it either way, so
folding is the forgiving direction on a closed vocabulary. A blob id is a hex
digest: it has no vocabulary to be forgiving about, and comparing it case-folded
would be the same comparison with an extra step — the forge and git both render
it lower case, so it is compared verbatim and a mismatch is a mismatch.
"""

from __future__ import annotations

from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    SOURCE_FORGE,
    SOURCE_GIT_OBJECT,
    ResultObservation,
    satisfied,
    unsatisfied,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_repository import ResultRepository
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import (
    FileOnBranchTarget,
    PullRequestStateTarget,
)
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "blob_argv",
    "observe_file_on_branch",
    "observe_pull_request_state",
    "pull_request_state_argv",
]

_FORGE_TIMEOUT_SECONDS = 30.0
_STATE_FIELD = "state"
_UPDATED_AT_FIELD = "updatedAt"


def pull_request_state_argv(*, number: int) -> list[str]:
    """The forge read that answers one pull request's state and its last update."""
    return ["gh", "pr", "view", str(number), "--json", f"{_STATE_FIELD},{_UPDATED_AT_FIELD}"]


def blob_argv(*, branch: str, path: str) -> list[str]:
    """The forge read that answers the blob identity of one path at one ref.

    The `{owner}`/`{repo}` placeholders are `gh`'s own, resolved from the
    repository the command runs in — which is the named repository's clone, so the
    answer is about the requested repository rather than the invoking one.
    """
    return [
        "gh",
        "api",
        f"repos/{{owner}}/{{repo}}/contents/{path}?ref={branch}",
        "--jq",
        ".sha",
    ]


def observe_pull_request_state(
    *, repository: ResultRepository, target: PullRequestStateTarget, runner: CommandRunner, now: str
) -> ResultObservation | None:
    """Observe whether one pull request stands at the expected forge state."""
    result = runner.run(
        argv=pull_request_state_argv(number=target.number),
        cwd=repository.clone,
        timeout_seconds=_FORGE_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return None
    parsed = parse_json(text=result.stdout)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return None
    fields = cast("dict[str, object]", parsed)
    state: object = fields.get(_STATE_FIELD)
    updated: object = fields.get(_UPDATED_AT_FIELD)
    if not isinstance(state, str) or state == "" or not isinstance(updated, str):
        return None
    if state.casefold() != target.state.casefold():
        return unsatisfied(
            repo=repository.name,
            target=target.identity,
            source=SOURCE_FORGE,
            now=now,
            evidence=f"forge pull request #{target.number} state {state} at {updated}",
            detail=(
                f"the forge reports pull request #{target.number} at state {state},"
                f" not the expected {target.state}"
            ),
        )
    return satisfied(
        repo=repository.name,
        target=target.identity,
        source=SOURCE_FORGE,
        now=now,
        evidence=f"forge pull request #{target.number} state {state} at {updated}",
        detail=(
            f"the forge reports pull request #{target.number} at the expected state"
            f" {state}, last updated {updated}"
        ),
    )


def observe_file_on_branch(
    *, repository: ResultRepository, target: FileOnBranchTarget, runner: CommandRunner, now: str
) -> ResultObservation | None:
    """Observe whether a remote branch's path holds the expected Git blob."""
    result = runner.run(
        argv=blob_argv(branch=target.branch, path=target.path),
        cwd=repository.clone,
        timeout_seconds=_FORGE_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return None
    blob = result.stdout.strip()
    if blob == "":
        return None
    if blob != target.blob:
        return unsatisfied(
            repo=repository.name,
            target=target.identity,
            source=SOURCE_GIT_OBJECT,
            now=now,
            evidence=f"git blob {blob} at {target.branch}:{target.path}",
            detail=(
                f"the remote branch {target.branch} holds blob {blob} at"
                f" {target.path}, not the expected {target.blob}; no local checkout"
                " was consulted"
            ),
        )
    return satisfied(
        repo=repository.name,
        target=target.identity,
        source=SOURCE_GIT_OBJECT,
        now=now,
        evidence=f"git blob {blob} at {target.branch}:{target.path}",
        detail=(
            f"the remote branch {target.branch} holds blob {blob} at {target.path};"
            " no local checkout was consulted"
        ),
    )
