"""Paired coverage for groom draft data shapes."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands.groom import CandidateSlice, CrossRepoSlice


def test_candidate_slice_defaults_to_factory_slice() -> None:
    candidate = CandidateSlice(
        title="slice",
        description="Do one thing.",
        acceptance="Factory can verify it.",
        autonomy_tier="T1",
        repo_target="local-repo",
    )

    assert candidate.depends_on == ()
    assert candidate.is_spec_change is False
    assert candidate.priority == 2


def test_cross_repo_slice_carries_minted_id() -> None:
    candidate = CandidateSlice(
        title="external",
        description="Do one external thing.",
        acceptance="Factory can verify it.",
        autonomy_tier="T1",
        repo_target="other-repo",
    )

    routed = CrossRepoSlice(candidate=candidate, minted_id="bd-x-123")

    assert routed.candidate is candidate
    assert routed.minted_id == "bd-x-123"
