"""Tests for the parse that admits a value into the typed result grammar.

The refusal ladder is the whole subject here, and the cases are grouped by what
each refusal PROTECTS rather than by field order: the closed-kind rule that
refuses a shell predicate, the exactly-one-target count, and the per-field shapes
that stop an empty value reaching an adapter that would satisfy it.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._plan_result_reference import (
    parse_result_reference,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import (
    FileOnBranchTarget,
    ItemCommentTarget,
    ItemStatusTarget,
    PullRequestStateTarget,
    ResultReference,
    ResultReferenceRefusal,
    VerifiedProofTarget,
)


def _refusal(*, value: object) -> str:
    parsed = parse_result_reference(value=value)
    assert isinstance(parsed, ResultReferenceRefusal)
    return parsed.detail


def _reference(*, value: object) -> ResultReference:
    parsed = parse_result_reference(value=value)
    assert isinstance(parsed, ResultReference)
    return parsed


def test_each_kind_parses_into_its_own_typed_target() -> None:
    """The positive control for all five rows, with leading whitespace stripped."""
    assert _reference(
        value={"repo": " repo ", "item_status": {"item_id": " bd-ib-1 ", "status": "ready"}}
    ) == ResultReference(repo="repo", target=ItemStatusTarget(item_id="bd-ib-1", status="ready"))
    assert _reference(
        value={"repo": "repo", "item_comment": {"item_id": "bd-ib-1", "marker": "shipped"}}
    ).target == ItemCommentTarget(item_id="bd-ib-1", marker="shipped")
    assert _reference(
        value={"repo": "repo", "pull_request_state": {"number": 9, "state": "MERGED"}}
    ).target == PullRequestStateTarget(number=9, state="MERGED")
    assert _reference(
        value={
            "repo": "repo",
            "verified_proof": {
                "subject_id": "bd-ib-2",
                "build": "v1.0.0",
                "assertions": [" one. ", "two."],
            },
        }
    ).target == VerifiedProofTarget(
        subject_id="bd-ib-2", build="v1.0.0", assertions=("one.", "two.")
    )
    assert _reference(
        value={
            "repo": "repo",
            "file_on_branch": {"branch": "master", "path": "a.md", "blob": "cafe"},
        }
    ).target == FileOnBranchTarget(branch="master", path="a.md", blob="cafe")


def test_a_non_object_is_not_a_reference() -> None:
    assert "exactly one typed target" in _refusal(value="item_status:bd-ib-1=done")


def test_an_arbitrary_shell_predicate_is_refused_by_the_closed_kind_set() -> None:
    """The clause's prohibition, enforced as a property of the grammar.

    The refusal names every accepted kind, because an operator reading it is
    choosing a replacement and the closed set is the whole answer.
    """
    detail = _refusal(value={"repo": "repo", "shell": "test -f a.md"})
    assert "no shell predicate is a result reference" in detail
    assert "item_status" in detail
    assert "shell" in detail


def test_a_reference_must_name_its_repository() -> None:
    """Absent, non-string and blank repository identities are one refusal."""
    for value in (
        {"item_status": {"item_id": "bd-ib-1", "status": "ready"}},
        {"repo": 1, "item_status": {"item_id": "bd-ib-1", "status": "ready"}},
        {"repo": "   ", "item_status": {"item_id": "bd-ib-1", "status": "ready"}},
    ):
        assert "canonical repository identity" in _refusal(value=value)


def test_exactly_one_target_is_counted_in_both_directions() -> None:
    """Two kinds and none are DIFFERENT faults, and each reports its own count.

    The two-kind case is the dangerous one: the object is well-formed, and picking
    the first kind in enumeration order would discharge the obligation on the
    weaker of the two targets while reporting the reference the caller wrote.
    """
    none = _refusal(value={"repo": "repo"})
    assert "carries 0 (none)" in none
    two = _refusal(
        value={
            "repo": "repo",
            "item_status": {"item_id": "bd-ib-1", "status": "ready"},
            "item_comment": {"item_id": "bd-ib-1", "marker": "shipped"},
        }
    )
    assert "carries 2 (item_status, item_comment)" in two


def test_a_target_must_be_an_object_carrying_exactly_its_own_fields() -> None:
    """Every kind is refused the same way, including the two with a non-string field."""
    assert "is an object carrying" in _refusal(value={"repo": "repo", "item_status": "ready"})
    assert "is an object carrying" in _refusal(value={"repo": "repo", "pull_request_state": 9})
    assert "is an object carrying" in _refusal(value={"repo": "repo", "verified_proof": "bd-ib-2"})
    extra = _refusal(
        value={
            "repo": "repo",
            "item_status": {"item_id": "bd-ib-1", "status": "ready", "command": "true"},
        }
    )
    assert "unknown field(s) command" in extra


def test_every_string_field_is_required_non_empty() -> None:
    """An empty value is refused at the parse, never passed to an adapter.

    An empty marker is a substring of every comment and an empty expected status
    compares equal to nothing, so the two would fail in opposite directions — one
    satisfying everything and one satisfying nothing. Neither is an observation.
    """
    assert "item_id as a non-empty string" in _refusal(
        value={"repo": "repo", "item_status": {"item_id": "", "status": "ready"}}
    )
    assert "status as a non-empty string" in _refusal(
        value={"repo": "repo", "item_status": {"item_id": "bd-ib-1", "status": None}}
    )
    assert "marker as a non-empty string" in _refusal(
        value={"repo": "repo", "item_comment": {"item_id": "bd-ib-1", "marker": "  "}}
    )
    assert "branch as a non-empty string" in _refusal(
        value={"repo": "repo", "file_on_branch": {"branch": "", "path": "a", "blob": "b"}}
    )


def test_a_pull_request_number_is_a_positive_integer_and_never_a_boolean() -> None:
    """`True` is an `int` in Python, and pull request 1 exists in every repository."""
    for number in (0, -1, "9", True, None):
        assert "number as a positive integer" in _refusal(
            value={"repo": "repo", "pull_request_state": {"number": number, "state": "MERGED"}}
        )
    assert "state as a non-empty string" in _refusal(
        value={"repo": "repo", "pull_request_state": {"number": 9, "state": ""}}
    )


def test_verified_proof_requires_a_subject_a_build_and_real_assertion_identifiers() -> None:
    """An empty assertion list is refused: a result with no scope proves nothing."""
    assert "subject_id as a non-empty string" in _refusal(
        value={
            "repo": "repo",
            "verified_proof": {"subject_id": "", "build": "v1", "assertions": ["a."]},
        }
    )
    assert "build as a non-empty string" in _refusal(
        value={
            "repo": "repo",
            "verified_proof": {"subject_id": "bd-ib-2", "build": "", "assertions": ["a."]},
        }
    )
    assert "a list of assertion identifiers" in _refusal(
        value={
            "repo": "repo",
            "verified_proof": {"subject_id": "bd-ib-2", "build": "v1", "assertions": "a."},
        }
    )
    for assertions in ([], ["a.", ""], ["a.", 2]):
        assert "non-empty list of non-empty assertion identifiers" in _refusal(
            value={
                "repo": "repo",
                "verified_proof": {
                    "subject_id": "bd-ib-2",
                    "build": "v1",
                    "assertions": assertions,
                },
            }
        )
