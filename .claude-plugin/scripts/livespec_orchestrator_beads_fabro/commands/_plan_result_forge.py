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

WHY BOTH COMPARISONS ARE CASE-FOLDED, AND WHY THE BLOB ONE DID NOT USED TO BE.
The forge renders pull-request state in upper case and an operator writes it
either way, so folding is the forgiving direction on a closed vocabulary. The blob
comparison was deliberately NOT folded, on the reasoning that a hex digest has no
vocabulary to be forgiving about and that the forge and git both render one in
lower case — so a verbatim comparison lost nothing.

That reasoning held only while every answer reaching the comparison shared ONE
rendering, and the object-identity shape check is what ended it. Hex is
case-insensitive, so an upper-case digest IS the same object as its lower-case
spelling, and a shape check has only two coherent options: call that answer
malformed, which asserts the forge named no identity when it plainly named one, or
admit it — in which case a verbatim comparison then reports one object as two. The
second failure is the clause's forbidden direction, a confident negative about an
object that matches, so the shape admits either case and the comparison folds.
Folding cannot conflate two DISTINCT identities, because hex digests differing in
any digit still differ when folded; the genuine-mismatch control asserts that.

WHY EACH OBSERVED VALUE IS VALIDATED BEFORE THE REQUESTED TARGET IS COMPARED, AND
WHY THAT ORDER IS THE WHOLE MECHANISM. The clause requires malformed evidence to be
`unobservable`, never satisfaction or a confident negative. A comparison performed
FIRST has already decided: it converts a value the adapter could not interpret into
a verdict, and the verdict is indistinguishable from one earned against a readable
source. So each adapter asks whether the forge answered IN ITS OWN GRAMMAR before
asking whether the answer is the requested one — a state inside the closed
vocabulary `_PULL_REQUEST_STATES`, a timestamp that is not blank (it is half the
evidence identity this kind reports), and a blob rendered as an object identity
rather than merely as something non-empty. Each arm failed in a DIFFERENT direction
before this ordering existed: a blank timestamp was satisfaction, while an
uninterpretable state and a `null` blob were confident negatives. Both directions
are forbidden, which is why neither a permissive nor a strict default is safe and
the grammar has to be asked explicitly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import cast
from urllib.parse import quote

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    SOURCE_FORGE,
    SOURCE_GIT_OBJECT,
    ResultObservation,
    satisfied,
    unobservable,
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

# The CLOSED vocabulary the forge reports a pull-request state in. A value
# outside it is MALFORMED EVIDENCE: it says nothing about where the pull request
# stands, so comparing it against the requested state would manufacture a
# confident negative out of a reading the adapter could not interpret. Narrowing
# fails CLOSED — an unrecognised state becomes `unobservable`, which leaves the
# obligation outstanding, rather than a verdict nobody can trust.
_PULL_REQUEST_STATES: frozenset[str] = frozenset({"open", "closed", "merged"})

# A Git object identity: hex at either rendering length — 40 for SHA-1, 64 for
# SHA-256 — in either case. The shape separates an IDENTITY from a NON-identity
# (`null`, a truncated digest, an error document), and it must not separate one
# legitimate rendering from another: a check admitting only lowercase SHA-1
# reports "the forge named no identity" about answers that plainly carry one, and
# on a SHA-256 repository that makes the file result PERMANENTLY unobservable
# rather than merely wrong once. Case is excluded from the grammar for the same
# reason, which is why the comparison folds — see the module docstring.
_OBJECT_IDENTITY = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})")


def pull_request_state_argv(*, number: int) -> list[str]:
    """The forge read that answers one pull request's state and its last update."""
    return ["gh", "pr", "view", str(number), "--json", f"{_STATE_FIELD},{_UPDATED_AT_FIELD}"]


def blob_argv(*, branch: str, path: str) -> list[str]:
    """The forge read that answers the blob identity of one path at one ref.

    The `{owner}`/`{repo}` placeholders are `gh`'s own, resolved from the
    repository the command runs in — which is the named repository's clone, so the
    answer is about the requested repository rather than the invoking one.

    BOTH COMPONENTS ARE PERCENT-ENCODED, AND EACH BY ITS OWN RULE, because this
    endpoint is a URL and neither a branch nor a path is URL text. The branch is a
    QUERY-STRING VALUE, so `safe=""` encodes everything including `/` — a
    `release/1.0` must arrive as one value rather than as a path segment. The path
    is a SEQUENCE OF PATH SEGMENTS, so `safe="/"` keeps the separators that
    structure it and encodes everything else.

    WHAT RAW INTERPOLATION COST, since the correct form looks like mere hygiene. A
    `#` is legal in a Git branch (`git check-ref-format --branch proof#variant`
    succeeds) and legal in a path, but in a URL it opens a FRAGMENT, which RFC
    3986 says is never transmitted. So `?ref=proof#variant` reached the forge as
    `ref=proof`: a request for a DIFFERENT, shorter target, whose answer was then
    reported as the answer about the requested one — satisfaction earned against a
    branch nobody asked about. A `#` in the path took the whole query with it, and
    a space produced a URL no client would send at all.
    """
    segments = quote(path, safe="/")
    ref = quote(branch, safe="")
    endpoint = f"repos/{{owner}}/{{repo}}/contents/{segments}?ref={ref}"
    return ["gh", "api", endpoint, "--jq", ".sha"]


@dataclass(frozen=True, kw_only=True)
class _ForgeState:
    """One pull-request state reading that IS evidence: a known state and its time."""

    state: str
    updated: str


@dataclass(frozen=True, kw_only=True)
class _StateRefusal:
    """Why a pull-request state reading is not evidence of anything.

    A VALUE rather than a bare `None`, for the reason `_plan_result_proof`'s
    `_SubjectRefusal` is one: the five ways this read fails have different
    remedies, and the clause requires the failed source named with a detail an
    operator can act on. The source is not carried because every arm here rests on
    the same one — this is the forge answering about its own pull request.
    """

    detail: str


def observe_pull_request_state(
    *, repository: ResultRepository, target: PullRequestStateTarget, runner: CommandRunner, now: str
) -> ResultObservation:
    """Observe whether one pull request stands at the expected forge state.

    TWO STEPS, AND THEY ARE SPLIT RATHER THAN INTERLEAVED: read the forge into a
    state that IS evidence, then compare that state against the requested one.
    Interleaving them is what let a value the reader could not interpret reach the
    comparison and come back out as a verdict.
    """
    reading = _read_pull_request_state(repository=repository, target=target, runner=runner)
    if isinstance(reading, _StateRefusal):
        return _unreadable(
            repository=repository,
            target=target,
            source=SOURCE_FORGE,
            now=now,
            detail=reading.detail,
        )
    state = reading.state
    updated = reading.updated
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


def _read_pull_request_state(
    *, repository: ResultRepository, target: PullRequestStateTarget, runner: CommandRunner
) -> _ForgeState | _StateRefusal:
    """The forge's answer about one pull request, admitted only if it IS evidence.

    FIVE WAYS THE FORGE ANSWERS WITHOUT ANSWERING, and the last two are the ones
    that reach a well-formed payload. A non-zero exit, output that is not the
    requested object, and a payload missing either field all fail on SHAPE. The
    remaining two carry the right shape and a value that is not evidence:

    - A BLANK `updatedAt`. The timestamp is HALF the evidence identity this kind
      reports — the clause names "forge state/timestamp" as one identity — so a
      blank one cannot be satisfaction. It previously was, publishing an evidence
      line that trails off after `at ` and names no observation anyone can look up.
    - A STATE OUTSIDE `_PULL_REQUEST_STATES`. It says nothing about where the pull
      request stands, so comparing it against the requested state manufactures a
      confident negative from a reading that was never interpreted.

    Both of those are REFUSED HERE rather than in the caller, which is the whole
    reason this function exists: a validation living next to the comparison can be
    reordered after it by an edit that looks harmless, and the comparison is what
    converts an uninterpretable value into a verdict.
    """
    result = runner.run(
        argv=pull_request_state_argv(number=target.number),
        cwd=repository.clone,
        timeout_seconds=_FORGE_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return _StateRefusal(
            detail=(
                f"the forge read of pull request #{target.number} exited"
                f" {result.exit_code}: {_first_line(text=result.stderr)}"
            )
        )
    parsed = parse_json(text=result.stdout)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return _StateRefusal(
            detail=(
                f"the forge answered for pull request #{target.number} with a payload"
                " that is not the requested object"
            )
        )
    fields = cast("dict[str, object]", parsed)
    state: object = fields.get(_STATE_FIELD)
    updated: object = fields.get(_UPDATED_AT_FIELD)
    if not isinstance(state, str) or state == "" or not isinstance(updated, str):
        return _StateRefusal(
            detail=(
                f"the forge payload for pull request #{target.number} carries no"
                f" readable {_STATE_FIELD} and {_UPDATED_AT_FIELD} pair"
            )
        )
    if updated.strip() == "":
        return _StateRefusal(
            detail=(
                f"the forge reported pull request #{target.number} at state {state}"
                f" with a blank {_UPDATED_AT_FIELD}, so the reading carries no forge"
                " observation time to cite as its evidence"
            )
        )
    if state.casefold() not in _PULL_REQUEST_STATES:
        return _StateRefusal(
            detail=(
                f"the forge answered for pull request #{target.number} with state"
                f" {state!r}, which is not a state the forge reports, so where the"
                " pull request stands was not observed"
            )
        )
    return _ForgeState(state=state, updated=updated)


def observe_file_on_branch(
    *, repository: ResultRepository, target: FileOnBranchTarget, runner: CommandRunner, now: str
) -> ResultObservation:
    """Observe whether a remote branch's path holds the expected Git blob."""
    result = runner.run(
        argv=blob_argv(branch=target.branch, path=target.path),
        cwd=repository.clone,
        timeout_seconds=_FORGE_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return _unreadable(
            repository=repository,
            target=target,
            source=SOURCE_GIT_OBJECT,
            now=now,
            detail=(
                f"the remote read of {target.branch}:{target.path} exited"
                f" {result.exit_code}: {_first_line(text=result.stderr)}"
            ),
        )
    blob = result.stdout.strip()
    if _OBJECT_IDENTITY.fullmatch(blob) is None:
        # AN ANSWER THAT IS NOT AN OBJECT IDENTITY IS UNOBSERVABLE AND NEVER A
        # MISMATCH. The forge returns an empty body for a path it cannot resolve
        # at that ref, and `gh api --jq .sha` prints the literal `null` for a
        # payload carrying no `sha` — four characters rather than none, so a
        # blank-only guard cleared it and the mismatch arm published a confident
        # negative about an object identity the read never obtained. Validating
        # the RENDERING rather than merely its emptiness is what closes both.
        return _unreadable(
            repository=repository,
            target=target,
            source=SOURCE_GIT_OBJECT,
            now=now,
            detail=(
                f"the remote named no object identity for {target.path} at"
                f" {target.branch} — it answered {blob!r} — which is an unresolved"
                " read rather than a differing object"
            ),
        )
    if blob.casefold() != target.blob.casefold():
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


def _unreadable(
    *,
    repository: ResultRepository,
    target: PullRequestStateTarget | FileOnBranchTarget,
    source: str,
    now: str,
    detail: str,
) -> ResultObservation:
    """One unobservable forge reading, carrying the source its own kind names.

    `source` is a parameter rather than a constant here because the two kinds
    this module answers for rest on different evidence — a pull-request state is
    forge state, a blob is a Git object — and the clause requires the FAILED
    source named, not the transport that failed to reach it.
    """
    return unobservable(
        repo=repository.name,
        target=target.identity,
        source=source,
        now=now,
        detail=detail,
    )


def _first_line(*, text: str) -> str:
    """The first line of a command's stderr, or a stated absence.

    One line, because a diagnostic that pasted a multi-line stderr into an
    observation would make the observation unreadable at every surface that
    renders one. The absence is STATED rather than left blank, since a blank tail
    reads as a truncation of the sentence it ends.
    """
    stripped = text.strip()
    if stripped == "":
        return "no diagnostic on stderr"
    return stripped.splitlines()[0]
