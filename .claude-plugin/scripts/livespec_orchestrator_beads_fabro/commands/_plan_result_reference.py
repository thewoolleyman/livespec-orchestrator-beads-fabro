"""Admitting a value into the typed result grammar, or refusing it by name.

The parse half of `_plan_result_targets`. One function matters —
`parse_result_reference` — and everything else here is the refusal ladder it
walks.

THE CLOSED SET IS THE WHOLE MECHANISM FOR ONE OF THE CLAUSE'S PROHIBITIONS.
The shared-authoritative-result-reader clause of `SPECIFICATION/contracts.md`
says arbitrary shell predicates MUST NOT be accepted as result references, and
this parse implements that by admitting ONLY the five named kinds and refusing
every other top-level field. That is a stronger guarantee than a scan for
shell-looking strings, which would have to anticipate what a predicate looks
like; here a predicate is refused for the same reason a typo is, and a kind
nobody has ratified cannot arrive through a field name.

EXACTLY ONE TARGET IS COUNTED, NOT ASSUMED. A reference carrying two kinds and
one carrying none are DIFFERENT faults with different remedies, so each is
refused with its own count rather than collapsed into one "malformed reference".
Counting also closes the direction that would otherwise pass silently: a
reference carrying a valid `item_comment` beside a valid `verified_proof` reads
as a perfectly well-formed object, and picking the first kind in enumeration
order would discharge the obligation on the weakest of the two targets while
reporting the reference the caller wrote.

EVERY STRING IS REQUIRED NON-EMPTY AND IS STRIPPED. An empty expected status, an
empty marker or an empty blob id would each compare TRUE against something — an
empty marker is a substring of every comment — so an absent value must be refused
at the parse rather than reach an adapter that would satisfy it.

THE PULL-REQUEST NUMBER IS THE ONE NON-STRING FIELD, and `bool` is excluded
explicitly: `True` is an `int` in Python and would otherwise parse as pull request
number 1, which is a real pull request in every repository in this fleet.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._plan_result_targets import (
    FILE_ON_BRANCH_KIND,
    ITEM_COMMENT_KIND,
    ITEM_STATUS_KIND,
    PULL_REQUEST_STATE_KIND,
    RESULT_KINDS,
    VERIFIED_PROOF_KIND,
    FileOnBranchTarget,
    ItemCommentTarget,
    ItemStatusTarget,
    PullRequestStateTarget,
    ResultReference,
    ResultReferenceRefusal,
    ResultTarget,
    VerifiedProofTarget,
)

__all__: list[str] = [
    "REPO_FIELD",
    "parse_result_reference",
]

REPO_FIELD = "repo"

_ITEM_ID_FIELD = "item_id"
_STATUS_FIELD = "status"
_MARKER_FIELD = "marker"
_NUMBER_FIELD = "number"
_STATE_FIELD = "state"
_SUBJECT_FIELD = "subject_id"
_BUILD_FIELD = "build"
_ASSERTIONS_FIELD = "assertions"
_BRANCH_FIELD = "branch"
_PATH_FIELD = "path"
_BLOB_FIELD = "blob"


def parse_result_reference(*, value: object) -> ResultReference | ResultReferenceRefusal:
    """Read one required-result value as a typed reference, or say why it is not one."""
    if not isinstance(value, dict):
        return ResultReferenceRefusal(
            detail=(
                "a result reference is an object carrying a repository identity and"
                " exactly one typed target"
            )
        )
    fields = cast("dict[str, Any]", value)
    # THE REPOSITORY IS READ FIRST, before any other field is judged, so that
    # every later refusal can carry the identity the reference did name. The
    # reader turns a refusal into an UNOBSERVABLE observation, and the clause
    # requires every observation to report its repository — an unobservable
    # reading with no repository is unattributable to the obligation that
    # produced it, which is the one thing it is read for.
    repo = _repo(fields=fields)
    if isinstance(repo, ResultReferenceRefusal):
        return repo
    unknown = sorted(one for one in fields if one != REPO_FIELD and one not in RESULT_KINDS)
    if unknown:
        return ResultReferenceRefusal(
            repo=repo,
            detail=(
                f"unknown result reference field(s) {', '.join(unknown)};"
                f" only {REPO_FIELD} and the typed kinds {', '.join(RESULT_KINDS)}"
                " are accepted, and no shell predicate is a result reference"
            ),
        )
    present = tuple(one for one in RESULT_KINDS if one in fields)
    if len(present) != 1:
        return ResultReferenceRefusal(
            repo=repo,
            detail=(
                "a result reference carries exactly one typed target; this one carries"
                f" {len(present)} ({', '.join(present) if present else 'none'})"
            ),
        )
    kind = present[0]
    target = _target(kind=kind, value=fields[kind])
    if isinstance(target, ResultReferenceRefusal):
        # The repository identity is attached HERE rather than inside each per-kind
        # parser: those parsers see only their own field set, and threading the
        # repository into all five would be five chances to forget it on the arm
        # whose refusal an operator actually reads.
        return replace(target, repo=repo)
    return ResultReference(repo=repo, target=target)


def _repo(*, fields: dict[str, Any]) -> str | ResultReferenceRefusal:
    raw: object = fields.get(REPO_FIELD)
    if not isinstance(raw, str) or raw.strip() == "":
        return ResultReferenceRefusal(
            detail=(
                f"a result reference names its canonical repository identity in a"
                f" non-empty {REPO_FIELD} field"
            )
        )
    return raw.strip()


def _target(*, kind: str, value: object) -> ResultTarget | ResultReferenceRefusal:
    """Dispatch one kind's own field set.

    A ladder rather than a `match`, because the subject is the raw `str` the
    reference carried: a `match` over it could not end in the `assert_never` arm
    this tree requires, since `str` is not a closed union and the final arm is
    genuinely reachable by any field name the caller invents. The enumeration is
    exhaustive against `RESULT_KINDS`, which `parse_result_reference` has already
    narrowed the subject to.
    """
    if kind == ITEM_STATUS_KIND:
        return _item_status(value=value)
    if kind == ITEM_COMMENT_KIND:
        return _item_comment(value=value)
    if kind == PULL_REQUEST_STATE_KIND:
        return _pull_request_state(value=value)
    if kind == VERIFIED_PROOF_KIND:
        return _verified_proof(value=value)
    return _file_on_branch(value=value)


def _item_status(*, value: object) -> ItemStatusTarget | ResultReferenceRefusal:
    names = (_ITEM_ID_FIELD, _STATUS_FIELD)
    read = _strings(kind=ITEM_STATUS_KIND, value=value, names=names)
    if isinstance(read, ResultReferenceRefusal):
        return read
    return ItemStatusTarget(item_id=read[_ITEM_ID_FIELD], status=read[_STATUS_FIELD])


def _item_comment(*, value: object) -> ItemCommentTarget | ResultReferenceRefusal:
    names = (_ITEM_ID_FIELD, _MARKER_FIELD)
    read = _strings(kind=ITEM_COMMENT_KIND, value=value, names=names)
    if isinstance(read, ResultReferenceRefusal):
        return read
    return ItemCommentTarget(item_id=read[_ITEM_ID_FIELD], marker=read[_MARKER_FIELD])


def _pull_request_state(*, value: object) -> PullRequestStateTarget | ResultReferenceRefusal:
    fields = _fields(kind=PULL_REQUEST_STATE_KIND, value=value, names=(_NUMBER_FIELD, _STATE_FIELD))
    if isinstance(fields, ResultReferenceRefusal):
        return fields
    number: object = fields.get(_NUMBER_FIELD)
    if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
        return _missing(
            kind=PULL_REQUEST_STATE_KIND, name=_NUMBER_FIELD, shape="a positive integer"
        )
    state = _string(kind=PULL_REQUEST_STATE_KIND, fields=fields, name=_STATE_FIELD)
    if isinstance(state, ResultReferenceRefusal):
        return state
    return PullRequestStateTarget(number=number, state=state)


def _verified_proof(*, value: object) -> VerifiedProofTarget | ResultReferenceRefusal:
    names = (_SUBJECT_FIELD, _BUILD_FIELD, _ASSERTIONS_FIELD)
    fields = _fields(kind=VERIFIED_PROOF_KIND, value=value, names=names)
    if isinstance(fields, ResultReferenceRefusal):
        return fields
    subject = _string(kind=VERIFIED_PROOF_KIND, fields=fields, name=_SUBJECT_FIELD)
    if isinstance(subject, ResultReferenceRefusal):
        return subject
    build = _string(kind=VERIFIED_PROOF_KIND, fields=fields, name=_BUILD_FIELD)
    if isinstance(build, ResultReferenceRefusal):
        return build
    raw: object = fields.get(_ASSERTIONS_FIELD)
    if not isinstance(raw, list):
        return _missing(
            kind=VERIFIED_PROOF_KIND,
            name=_ASSERTIONS_FIELD,
            shape="a list of assertion identifiers",
        )
    entries = cast("list[object]", raw)
    if not entries or any(not isinstance(one, str) or one.strip() == "" for one in entries):
        return _missing(
            kind=VERIFIED_PROOF_KIND,
            name=_ASSERTIONS_FIELD,
            shape="a non-empty list of non-empty assertion identifiers",
        )
    assertions = tuple(cast("str", one).strip() for one in entries)
    return VerifiedProofTarget(subject_id=subject, build=build, assertions=assertions)


def _file_on_branch(*, value: object) -> FileOnBranchTarget | ResultReferenceRefusal:
    names = (_BRANCH_FIELD, _PATH_FIELD, _BLOB_FIELD)
    read = _strings(kind=FILE_ON_BRANCH_KIND, value=value, names=names)
    if isinstance(read, ResultReferenceRefusal):
        return read
    return FileOnBranchTarget(
        branch=read[_BRANCH_FIELD], path=read[_PATH_FIELD], blob=read[_BLOB_FIELD]
    )


def _strings(
    *, kind: str, value: object, names: tuple[str, ...]
) -> dict[str, str] | ResultReferenceRefusal:
    """One kind's field set when every field of it is a non-empty string."""
    fields = _fields(kind=kind, value=value, names=names)
    if isinstance(fields, ResultReferenceRefusal):
        return fields
    read: dict[str, str] = {}
    for name in names:
        one = _string(kind=kind, fields=fields, name=name)
        if isinstance(one, ResultReferenceRefusal):
            return one
        read[name] = one
    return read


def _fields(
    *, kind: str, value: object, names: tuple[str, ...]
) -> dict[str, Any] | ResultReferenceRefusal:
    if not isinstance(value, dict):
        return ResultReferenceRefusal(
            detail=f"the {kind} target is an object carrying {', '.join(names)}"
        )
    fields = cast("dict[str, Any]", value)
    extra = sorted(one for one in fields if one not in names)
    if extra:
        return ResultReferenceRefusal(
            detail=(
                f"the {kind} target carries unknown field(s) {', '.join(extra)};"
                f" it carries exactly {', '.join(names)}"
            )
        )
    return fields


def _string(*, kind: str, fields: dict[str, Any], name: str) -> str | ResultReferenceRefusal:
    raw: object = fields.get(name)
    if not isinstance(raw, str) or raw.strip() == "":
        return _missing(kind=kind, name=name, shape="a non-empty string")
    return raw.strip()


def _missing(*, kind: str, name: str, shape: str) -> ResultReferenceRefusal:
    return ResultReferenceRefusal(detail=f"the {kind} target names its {name} as {shape}")
