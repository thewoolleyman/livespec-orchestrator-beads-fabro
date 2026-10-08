"""The pull request one publish branch carries, as the forge reports it.

A resume's first question is about the forge: does the item's publish branch
still carry a pull request, which one, at which head, and in which state.
`SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" spends three of its eight refusals on that one answer — no
open pull request, a moved head, a closed or merged one — so the read has to
distinguish all three, and a fourth thing besides: whether the forge answered at
all.

WHY THE LISTING IS `--state all` RATHER THAN THE DEFAULT. This is the arm nothing
downstream can repair. `gh pr list` defaults to OPEN, so a closed or merged pull
request comes back as an EMPTY listing — and an empty listing is a legitimate,
error-free answer meaning "this branch carries no pull request", whose remedy is a
plain dispatch. For a MERGED pull request that remedy is wrong and expensive: the
clause requires `reconcile-merged --item`, "which requires a real merge and stays
the only valve for one", so the plain-dispatch advice would send an operator to
cut an empty branch against work that has already landed.

WHY AN UNUSABLE PAYLOAD IS `observed=False` AND NOT AN EMPTY ANSWER. A forge that
cannot be asked and a branch that carries nothing support opposite decisions, and
the clause is explicit that the resume "MUST NOT proceed on an unobservable
answer". Exit code and payload shape are two ways for the same read to fail, so
both land on the same side: a zero exit carrying something that is not a JSON
array is a read that did not happen, not a branch with no pull request.

WHY THE NEWEST NUMBER WINS when the listing names several. One branch can carry
more than one pull request over its life — a closed one plus a reopened one, or
one against a second base — and the pull request a resume finishes is the one the
dead run last published to, which is the newest. Forge numbering is monotonic, so
the maximum number IS the newest; taking the listing's first entry would depend on
an ordering `gh pr list` does not promise.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "BranchPullRequest",
    "BranchPullRequestRead",
    "branch_pull_request",
    "branch_pull_request_argv",
    "branch_pull_request_from_stdout",
]

_LIST_TIMEOUT_SECONDS = 120.0
_LIST_LIMIT = "20"


@dataclass(frozen=True, kw_only=True)
class BranchPullRequest:
    """One pull request of a publish branch: its number, its state and its head.

    `head` is `None` when the forge named the pull request but no head oid for it,
    which is a degraded read of ONE field rather than a different kind of pull
    request. The head-moved refusal reports that as the measurement it could not
    take rather than as a mismatch, because a comparison against an absent head
    would name a sha nobody published.
    """

    number: int
    state: str
    head: str | None


@dataclass(frozen=True, kw_only=True)
class BranchPullRequestRead:
    """What one forge read established, with "could not ask" kept separate.

    `observed` false means the listing did not happen. `pull_request` `None` with
    `observed` true is the forge's own answer that the branch carries none. The
    two carry the same `None` and must not produce the same refusal.
    """

    observed: bool
    pull_request: BranchPullRequest | None


def branch_pull_request_argv(*, branch: str) -> list[str]:
    """The listing one publish branch's pull requests are read from."""
    return [
        "gh",
        "pr",
        "list",
        "--head",
        branch,
        "--state",
        "all",
        "--json",
        "number,state,headRefOid",
        "--limit",
        _LIST_LIMIT,
    ]


def branch_pull_request_from_stdout(*, stdout: str) -> BranchPullRequestRead:
    """Parse the listing: the newest pull request it names, or why there is none."""
    parsed = parse_json(text=stdout)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, list):
        return BranchPullRequestRead(observed=False, pull_request=None)
    found = [
        one
        for entry in cast("list[object]", parsed)
        if (one := _pull_request(entry_raw=entry)) is not None
    ]
    if not found:
        return BranchPullRequestRead(observed=True, pull_request=None)
    # Keyed by NUMBER so the newest is `max` over plain integers: a `key=`
    # callable would be a positional-argument function, which this tree's
    # keyword-only rule forbids, and a comparison fold would add a branch that
    # only a second ordering of the same listing could cover.
    by_number = {one.number: one for one in found}
    return BranchPullRequestRead(observed=True, pull_request=by_number[max(by_number)])


def branch_pull_request(*, repo: Path, branch: str, runner: CommandRunner) -> BranchPullRequestRead:
    """Ask the forge which pull request this publish branch carries."""
    result = runner.run(
        argv=branch_pull_request_argv(branch=branch),
        cwd=repo,
        timeout_seconds=_LIST_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return BranchPullRequestRead(observed=False, pull_request=None)
    return branch_pull_request_from_stdout(stdout=result.stdout)


def _pull_request(*, entry_raw: object) -> BranchPullRequest | None:
    """One listing entry as a pull request, or `None` for any unusable shape.

    A row missing its number or its state is DROPPED rather than defaulted: the
    number is what every refusal names and the state is what two of them decide
    on, so a row carrying neither cannot be refused about — and inventing an
    `UNKNOWN` state for it would let a resume proceed against a pull request
    whose state nobody read.
    """
    if not isinstance(entry_raw, dict):
        return None
    entry = cast("dict[str, Any]", entry_raw)
    number_raw: object = entry.get("number")
    state_raw: object = entry.get("state")
    if not isinstance(number_raw, int) or not isinstance(state_raw, str) or not state_raw:
        return None
    head_raw: object = entry.get("headRefOid")
    return BranchPullRequest(
        number=number_raw,
        state=state_raw,
        head=head_raw if isinstance(head_raw, str) and head_raw else None,
    )
