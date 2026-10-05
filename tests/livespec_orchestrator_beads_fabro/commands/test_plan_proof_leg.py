"""The proof leg's decision, across every state the ratified clause distinguishes.

Covers `_plan_proof_leg`. The leg is pure, so each case is one timeline graded
against one parsed Definition of Done — which is what makes the states the clause
separates reachable at all: a verified record that precedes a later capture, a
`not_reproduced` latest replay sitting over an earlier `verified` one, a replay
published by the capturing identity, and the two release-identity rejections.

EVERY CASE CARRIES THE PASSING CONTROL IT IS THE NEGATION OF, because "the leg
reported this assertion unproved" is otherwise equally consistent with a leg that
reports every assertion unproved. The controls are the same timelines with the
one offending property removed.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_HOST_CAPTURED,
    PROOF_MODE_HUMAN_ATTESTED,
    DefinitionOfDoneAssertion,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    BuildIdentity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_render import (
    RecordAssertion,
    render_proof_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_CAPTURED,
    VERDICT_HUMAN_ATTESTED,
    VERDICT_NOT_REPRODUCED,
    VERDICT_VERIFIED,
)
from livespec_orchestrator_beads_fabro.commands._plan_carrier_map import (
    CARRIERS_BLOCK_PREFIX,
    last_carrier_map_position,
)
from livespec_orchestrator_beads_fabro.commands._plan_proof_leg import (
    NOT_EVIDENCE_NO_RELEASE,
    NOT_EVIDENCE_SELF_VERIFIED,
    NOT_EVIDENCE_UNKNOWN_RELEASE,
    plan_proof_leg,
)
from livespec_orchestrator_beads_fabro.commands._plan_proof_record import (
    PLAN_PROOF_RECORD_TITLE,
    plan_proof_entries,
)

_HOST = "The released build runs in a real operator session."
_HUMAN = "The maintainer agrees the console reads well."
_TAG = "v0.167.0"
_TAGS = frozenset({_TAG, "v0.166.0"})

_ASSERTIONS = (
    DefinitionOfDoneAssertion(text=_HOST, proof_mode=PROOF_MODE_HOST_CAPTURED),
    DefinitionOfDoneAssertion(text=_HUMAN, proof_mode=PROOF_MODE_HUMAN_ATTESTED),
)


def _record(
    *,
    verdict: str,
    identity: str,
    assertion: str = _HOST,
    reproduced: bool | None = True,
    release: str | None = _TAG,
) -> dict[str, object]:
    """One plan record comment, rendered through the production renderer."""
    return {
        "text": render_proof_record(
            title=PLAN_PROOF_RECORD_TITLE,
            verdict=verdict,
            identity=f"session {identity}",
            timestamp="2026-10-05T00:00:00Z",
            build=BuildIdentity(release_tag=release, installed_build=None, commit="c0ffee1"),
            assertions=(
                RecordAssertion(
                    text=assertion,
                    proof_mode=PROOF_MODE_HOST_CAPTURED,
                    governing_scenario=None,
                    steps=("Run the released build on the operator host.",),
                    proof="$ delivered --version\n0.167.0",
                    reproduced=reproduced,
                ),
            ),
        )
    }


def _leg(
    *,
    comments: list[dict[str, object]],
    tags: frozenset[str] = _TAGS,
    assertions: tuple[DefinitionOfDoneAssertion, ...] = _ASSERTIONS,
) -> object:
    return plan_proof_leg(
        assertions=assertions,
        entries=plan_proof_entries(comments=comments),
        carrier_map_position=last_carrier_map_position(comments=comments),
        release_tags=tags,
    )


def _proved() -> list[dict[str, object]]:
    """The timeline that proves BOTH assertions — every case's own control."""
    return [
        {
            "text": f"plan-scope-event\nauthor: console\ntimestamp: x\n\n{CARRIERS_BLOCK_PREFIX}\n- 1: plan-level proof\n- 2: plan-level proof"
        },
        _record(verdict=VERDICT_CAPTURED, identity="capturing", reproduced=None),
        _record(verdict=VERDICT_VERIFIED, identity="replaying"),
        _record(verdict=VERDICT_HUMAN_ATTESTED, identity="maintainer", assertion=_HUMAN),
    ]


def test_an_independent_verified_replay_and_an_attestation_prove_both_legs() -> None:
    leg = _leg(comments=_proved())

    assert leg.unproved == ()
    assert leg.rejected == ()
    assert leg.met is True
    # The cited record is the verified replay, so an archive record never
    # advertises proof the gate refused.
    assert leg.verified_record is not None
    assert leg.verified_record.run_id == "replaying"


def test_the_two_legs_do_not_substitute_for_each_other() -> None:
    # The verified replay lists the HUMAN assertion as reproduced, and the
    # attestation lists the HOST one. Each leg must still report its own
    # assertion unproved: a machine replay cannot discharge a human attestation
    # and an attestation cannot discharge the host leg.
    crossed = [
        _record(verdict=VERDICT_VERIFIED, identity="replaying", assertion=_HUMAN),
        _record(verdict=VERDICT_HUMAN_ATTESTED, identity="maintainer", assertion=_HOST),
    ]

    leg = _leg(comments=crossed)

    assert leg.unproved == (_HOST, _HUMAN)
    assert leg.verified_record is None


def test_a_capture_published_after_the_replay_voids_it() -> None:
    timeline = _proved()
    timeline.append(_record(verdict=VERDICT_CAPTURED, identity="capturing", reproduced=None))

    leg = _leg(comments=timeline)

    # The host leg falls back to unproved: the newest capture states proof steps
    # the standing replay never ran. The human leg is untouched, because an
    # attestation is not a replay of a capture.
    assert leg.unproved == (_HOST,)


def test_a_not_reproduced_latest_replay_does_not_fall_back_to_an_earlier_verified_one() -> None:
    timeline = _proved()
    timeline.append(
        _record(verdict=VERDICT_NOT_REPRODUCED, identity="second-replayer", reproduced=False)
    )

    leg = _leg(comments=timeline)

    assert leg.unproved == (_HOST,)
    assert leg.rejected == ()


def test_a_later_human_attested_record_does_not_unseat_the_verified_record() -> None:
    timeline = _proved()
    timeline.append(
        _record(verdict=VERDICT_HUMAN_ATTESTED, identity="maintainer", assertion=_HUMAN)
    )

    assert _leg(comments=timeline).unproved == ()


def test_a_replay_published_by_the_capturing_identity_is_not_evidence() -> None:
    timeline = _proved()
    timeline[2] = _record(verdict=VERDICT_VERIFIED, identity="capturing")

    leg = _leg(comments=timeline)

    assert leg.unproved == (_HOST,)
    assert len(leg.rejected) == 1
    assert NOT_EVIDENCE_SELF_VERIFIED in leg.rejected[0]
    # The rejected line names the publisher, so two records of one verdict on a
    # timeline are told apart.
    assert "capturing" in leg.rejected[0]


def test_a_record_stating_release_none_is_rejected_where_a_release_applies() -> None:
    timeline = _proved()
    timeline[2] = _record(verdict=VERDICT_VERIFIED, identity="replaying", release=None)

    leg = _leg(comments=timeline)

    assert leg.unproved == (_HOST,)
    assert [NOT_EVIDENCE_NO_RELEASE in one for one in leg.rejected] == [True]
    # The control: the SAME record against a repository carrying no release tag
    # at all is admitted, because the clause attaches the whole rule to that
    # condition.
    assert _leg(comments=timeline, tags=frozenset()).unproved == ()


def test_a_record_naming_an_unknown_tag_is_rejected() -> None:
    timeline = _proved()
    timeline[2] = _record(verdict=VERDICT_VERIFIED, identity="replaying", release="v9.9.9")

    leg = _leg(comments=timeline)

    assert leg.unproved == (_HOST,)
    assert [NOT_EVIDENCE_UNKNOWN_RELEASE in one for one in leg.rejected] == [True]


def test_a_record_predating_the_last_carrier_map_event_does_not_prove_anything() -> None:
    timeline = _proved()
    timeline.append(
        {
            "text": (
                "plan-scope-event\nauthor: console\ntimestamp: x\n\n"
                f"{CARRIERS_BLOCK_PREFIX}\n- 1: bd-ib-child\n- 2: plan-level proof"
            )
        }
    )

    leg = _leg(comments=timeline)

    # Both legs fall back: every record now predates the restated map.
    assert leg.unproved == (_HOST, _HUMAN)
    # A ruling with NO `carriers:` line sets no floor, which is the control that
    # separates a carrier-map event from the ordinary scope event whose body also
    # ENDS in the word `carriers:`.
    ruling = _proved()
    ruling.append(
        {"text": "plan-scope-event\nauthor: console\ntimestamp: x\n\nRequirement carriers:\n- one"}
    )
    assert _leg(comments=ruling).unproved == ()


def test_an_epic_with_no_carrier_map_event_imposes_no_recency_floor() -> None:
    bare = _proved()[1:]

    assert last_carrier_map_position(comments=bare) is None
    assert _leg(comments=bare).unproved == ()


def test_an_assertion_no_record_mentions_at_all_is_unproved() -> None:
    orphan = DefinitionOfDoneAssertion(
        text="A third assertion nobody published for.",
        proof_mode=PROOF_MODE_HOST_CAPTURED,
    )

    leg = _leg(comments=_proved(), assertions=(*_ASSERTIONS, orphan))

    assert leg.unproved == (orphan.text,)
    # The cited record is withheld while anything is unproved: a pointer naming
    # a record that did not carry the verdict would advertise proof the leg did
    # not rest on.
    assert leg.verified_record is None
