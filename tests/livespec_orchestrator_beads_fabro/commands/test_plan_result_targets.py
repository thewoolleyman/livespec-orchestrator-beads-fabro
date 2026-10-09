"""Tests for the typed result grammar: the five targets and their identities.

`test_plan_result_reference.py` covers the PARSE that admits a value into this
grammar. This module covers what the grammar itself promises: that every kind is
in the closed set, and that each renders the target identity every observation of
it reports.
"""

from __future__ import annotations

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
    VerifiedProofTarget,
)


def test_the_kind_set_is_exactly_the_five_the_clause_enumerates() -> None:
    assert RESULT_KINDS == (
        ITEM_STATUS_KIND,
        ITEM_COMMENT_KIND,
        PULL_REQUEST_STATE_KIND,
        VERIFIED_PROOF_KIND,
        FILE_ON_BRANCH_KIND,
    )


def test_each_target_renders_its_kind_and_its_discriminating_fields() -> None:
    """Every identity names the kind plus the fields that distinguish two targets.

    The kind is load-bearing in the rendering as well as in the dispatch: two
    kinds can name the same item, and an identity that omitted the kind would make
    a status result and a marker result on one item indistinguishable in a report.
    """
    assert ItemStatusTarget(item_id="bd-ib-1", status="done").identity == (
        "item_status bd-ib-1 status done"
    )
    assert ItemCommentTarget(item_id="bd-ib-1", marker="shipped").identity == (
        "item_comment bd-ib-1 marker 'shipped'"
    )
    assert PullRequestStateTarget(number=7, state="MERGED").identity == (
        "pull_request_state #7 state MERGED"
    )
    assert (
        VerifiedProofTarget(subject_id="bd-ib-2", build="v1.2.3", assertions=("a.", "b.")).identity
        == "verified_proof bd-ib-2 build v1.2.3 assertions 2"
    )
    assert FileOnBranchTarget(branch="master", path="a/b.md", blob="cafe").identity == (
        "file_on_branch master:a/b.md blob cafe"
    )


def test_a_reference_identity_names_the_repository_before_the_target() -> None:
    """The repository leads, because one target identity exists in many repositories."""
    reference = ResultReference(
        repo="livespec-overseer", target=ItemStatusTarget(item_id="ov-1", status="ready")
    )
    assert reference.identity == "livespec-overseer item_status ov-1 status ready"


def test_a_refusal_carries_its_own_detail() -> None:
    """The refusal is a VALUE, so the reader can turn it into an observation."""
    assert ResultReferenceRefusal(detail="not an object").detail == "not an object"
