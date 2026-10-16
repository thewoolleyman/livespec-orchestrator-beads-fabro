"""The authenticated forge reads the plan release rule makes.

The plan-record clause of `SPECIFICATION/contracts.md` (v148) names the venue in
as many words: "Every repository's release tags — the governed repository's
included — MUST be read by an authenticated read of its remote on the forge that
hosts the governed repository, and MUST NOT be read from any local clone or
worktree." This module is those reads and nothing else: three argvs, three
answers, no decisions. `_plan_release_reader` composes them into the resolution
ladder and `_plan_proof_leg` grades the result.

WHY THE FORGE AND NOT A LOCAL CLONE, WHICH IS WHAT THIS REPLACED. The retired read
was `git tag --list` against the governed repository's own checkout, which cannot
answer the question at all once the release repository may be a sibling: the host
running an archive need hold no clone of the repository whose release the record
names, and where it does, that clone's tags are whatever its last fetch left — an
answer about this host's fetch state reported as a fact about the repository. The
forge's own tag listing removes the local checkout from the question entirely.

WHY EVERY FAILED READ IS A VALUE AND NEVER AN EMPTY ANSWER. The retired read
"returned an empty set on any failure", and an empty tag set MEANS "no release
applies", so an unreachable forge or a rejected credential made every record that
states `release: none` into evidence. The clause reversed that: a failed read
"MUST reject the record, naming the repository it tried to read and the failure,
instead of treating that repository as carrying no release tags". So an empty
`frozenset` is reserved for the forge SAYING the repository carries no tag, and
every other outcome is a `ForgeReadFailure` carrying the line a refusal cites.

WHY THE EXISTENCE PROBE IS GRADED ON THE FORGE'S OWN HTTP STATUS AND NOT ON THE
EXIT CODE. The clause gives "the forge reports this repository does not exist" two
OPPOSITE consequences depending on the form it read — the governed repository for
a bare `<repository>`, a rejection for an explicit `<owner>/<repository>` — and
gives "the read failed" a third. Measured against the live forge on 2026-10-16,
`gh api --include --method HEAD repos/<owner>/<absent>` exits 1 and prints
`HTTP/2.0 404 Not Found` as its first line of stdout, exactly as the existing
repository exits 0 and prints `HTTP/2.0 200 OK`. So the exit code conflates the
forge's own 404 with a transport fault, while the status line distinguishes them —
and getting that wrong rejects a record the clause routes to the governed
repository, which is the fail-WRONG direction rather than a fail-closed one.

WHY THE FINAL STATUS LINE AND NOT THE FIRST. `gh` follows redirects, so a renamed
repository answers `301` and then `200` on one invocation. The final response is
the forge's answer about the repository as it now stands; grading the first would
report a live repository as neither existing nor absent, which is the third
consequence rather than the one earned.

WHY THE REPOSITORY IS NAMED IN EVERY ENDPOINT. `gh`'s `{owner}`/`{repo}`
placeholders resolve against the repository the command runs in, which is always
the governed checkout here — so a placeholder form would answer about the governed
repository for every record, silently, while reporting the repository the record
named.

WHY THE GOVERNED IDENTITY IS ASKED OF THE FORGE RATHER THAN READ OFF THE REMOTE
URL. The identity is needed for two things the clause requires — the owner a bare
`<repository>` is resolved under, and the governed repository's own tag read — and
both are forge facts. A URL parse would also answer when there are no credentials
at all, which is one of the three conditions the clause requires the gate to
REJECT on; asking the forge makes the credential part of the question rather than
something a later read discovers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._plan_release_repository import (
    ExplicitRepository,
)

__all__: list[str] = [
    "ForgeReadFailure",
    "governed_repository_argv",
    "governed_repository_identity",
    "repository_exists",
    "repository_probe_argv",
    "repository_release_tags",
    "repository_tags_argv",
]

# One ceiling for all three reads, sized for the PAGINATED one: this fleet's own
# `livespec-dev-tooling` carries 519 tags across six pages, and a tag listing is
# the only read here whose cost grows with the repository.
_FORGE_TIMEOUT_SECONDS = 120.0

_SEPARATOR = "/"
# The two statuses that ANSWER the existence question. Every other status is a
# read the gate could not take — a credential the forge will not accept for this
# repository says nothing about whether the repository is there.
_STATUS_EXISTS = 200
_STATUS_ABSENT = 404

# A response status line, anchored per line so the header block's other lines
# cannot supply one. `findall` over the whole stdout yields one entry per response
# in a redirect chain, and the LAST is the forge's final answer.
_STATUS_LINE = re.compile(r"^HTTP/[\d.]+\s+(?P<code>\d{3})\b", re.MULTILINE)


@dataclass(frozen=True, kw_only=True)
class ForgeReadFailure:
    """Why one authenticated forge read answered nothing the rule can use.

    `detail` is ONE line naming the repository the read was about and what the
    read did, because the clause requires the rejection to name "the repository it
    tried to read and the failure" — and because the conditions it covers (no
    `origin` remote, an unreachable forge, a credential the forge does not accept,
    a repository that does not exist) have different remedies.
    """

    detail: str


def governed_repository_argv() -> list[str]:
    """The forge read that answers the governed checkout's own owner and repository.

    Published so a caller's own journal and tests can name the exact read rather
    than reconstructing an argv that might differ from the one run.
    """
    return ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]


def repository_tags_argv(*, repository: str) -> list[str]:
    """The forge read that enumerates one named repository's tags.

    PAGINATED, because a repository's tag count is unbounded and one page cannot
    be assumed to carry the tag a record names.

    THE METHOD IS DECLARED BECAUSE THE PAGE SIZE IS A PARAMETER. `gh api`'s own
    help states the rule: "The default HTTP request method is `GET` normally and
    `POST` if any parameters were added." So `-F per_page=100` with no `--method`
    would be sent as `POST repos/<owner>/<repository>/tags`, which cannot return
    tags — the same inversion `_dispatcher_fabro_currency_sources` records against
    the releases endpoint.

    The `--jq` projection is what makes the paginated answer parseable: without it
    `gh api --paginate` emits one JSON array per page, concatenated, so a single
    document parse succeeds on a one-page answer and fails on every multi-page
    one. With it, each tag name arrives on its own line.
    """
    return [
        "gh",
        "api",
        "--method",
        "GET",
        f"repos/{repository}/tags",
        "--paginate",
        "-F",
        "per_page=100",
        "--jq",
        ".[].name",
    ]


def repository_probe_argv(*, repository: str) -> list[str]:
    """The forge read that answers whether one named repository exists.

    `--include` is what makes the answer gradeable: it puts the response's own
    status line on stdout, which is the only thing that separates the forge's 404
    from a transport fault — see the module docstring. `--method HEAD` asks for no
    body, because the question is about the resource and not about its contents.
    """
    return ["gh", "api", "--include", "--method", "HEAD", f"repos/{repository}"]


def governed_repository_identity(
    *, project_root: Path, runner: CommandRunner
) -> ExplicitRepository | ForgeReadFailure:
    """The governed checkout's own forge identity, or why it could not be read.

    An answer outside the forge's own grammar FAILS rather than being passed on:
    `repos//tags` is a well-formed endpoint about nothing, so an empty half would
    read the wrong population and report it as the governed repository's tags. The
    grammar is graded here, on the forge's own answer, rather than by re-using the
    record-word parse of `_plan_release_repository` — that parse grades a word a
    PUBLISHER wrote, and the two inputs have different failure modes.
    """
    result = runner.run(
        argv=governed_repository_argv(),
        cwd=project_root,
        timeout_seconds=_FORGE_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return ForgeReadFailure(
            detail=(
                f"the forge read of the governed checkout's own repository identity,"
                f" taken from {project_root}, exited {result.exit_code}:"
                f" {_first_line(text=result.stderr)}"
            )
        )
    owner, separator, repository = result.stdout.strip().partition(_SEPARATOR)
    if separator == "" or owner == "" or repository == "":
        return ForgeReadFailure(
            detail=(
                f"the forge named no owner and repository for the checkout at"
                f" {project_root} — it answered {result.stdout.strip()!r}"
            )
        )
    return ExplicitRepository(owner=owner, repository=repository)


def repository_release_tags(
    *, repository: str, project_root: Path, runner: CommandRunner
) -> frozenset[str] | ForgeReadFailure:
    """Every release tag one named repository carries, or why it could not be read.

    The empty set is the forge SAYING the repository carries no tag, which is the
    clause's "no release applies" condition. It is never the encoding of a failure
    — that reversal is the whole point of this module.
    """
    result = runner.run(
        argv=repository_tags_argv(repository=repository),
        cwd=project_root,
        timeout_seconds=_FORGE_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return ForgeReadFailure(
            detail=(
                f"the forge read of {repository}'s release tags exited"
                f" {result.exit_code}: {_first_line(text=result.stderr)}"
            )
        )
    return frozenset(line.strip() for line in result.stdout.splitlines() if line.strip())


def repository_exists(
    *, repository: str, project_root: Path, runner: CommandRunner
) -> bool | ForgeReadFailure:
    """Whether the forge reports one named repository, or why it could not say.

    Graded on the forge's final status line and never on the exit code, for the
    reason the module docstring gives: `gh api` exits non-zero for the forge's own
    404, so the exit code cannot tell an absent repository from a failed read, and
    those two have opposite consequences under this clause.
    """
    result = runner.run(
        argv=repository_probe_argv(repository=repository),
        cwd=project_root,
        timeout_seconds=_FORGE_TIMEOUT_SECONDS,
    )
    status = _final_status(text=result.stdout)
    if status is None:
        return ForgeReadFailure(
            detail=(
                f"the forge answered no HTTP status when asked whether {repository}"
                f" exists — the probe exited {result.exit_code}:"
                f" {_first_line(text=result.stderr)}"
            )
        )
    if status == _STATUS_EXISTS:
        return True
    if status == _STATUS_ABSENT:
        return False
    return ForgeReadFailure(
        detail=(
            f"the forge answered HTTP {status} when asked whether {repository}"
            " exists, which reports neither an existing repository nor an absent one"
        )
    )


def _final_status(*, text: str) -> int | None:
    """The status of the LAST response the probe's output carries, or `None`.

    `None` for output carrying no status line at all, which is what a probe that
    never reached the forge prints. It is kept distinct from every real status
    because a reader that defaulted to one would report a transport fault as the
    forge's own answer about the repository.
    """
    codes: list[str] = _STATUS_LINE.findall(text)
    if not codes:
        return None
    return int(codes[-1])


def _first_line(*, text: str) -> str:
    """The first line of a read's stderr, or a stated absence.

    One line, because a diagnostic that pasted a multi-line stderr into a refusal
    would make the refusal unreadable at every surface that renders one. The
    absence is STATED rather than left blank, since a blank tail reads as a
    truncation of the sentence it ends.
    """
    stripped = text.strip()
    if stripped == "":
        return "no diagnostic on stderr"
    return stripped.splitlines()[0]
