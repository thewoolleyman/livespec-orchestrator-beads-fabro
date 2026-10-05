"""Tests for the proof leg as a VALUE — the four questions its consumers ask it.

`test_dispatcher_proof_evidence.py` builds this value through the reads and the
grading. This module asks it the questions directly, because each one has a different
downstream consequence and a value assembled by hand is the only way to pose a
combination the grading cannot currently produce.

THE ASYMMETRY BETWEEN THE TWO PENDING PROJECTIONS IS THE POINT OF THIS FILE.
`pending_human_attested` is unconditional — the ratified clause gives the human leg to
the `accept` valve, so the pass holds no evidence that could retire one — while
`pending_host_captured` reports only the host assertions still awaiting a replay,
because the pass DOES grade that leg. The second is what the completion disposition's
close gate reads, so collapsing the two into one symmetric projection would leave every
host-captured item resting in `acceptance` for ever on a verdict of PASS. One test
below holds a host leg with nothing pending beside a human leg with something pending,
which is the one shape that fails if the two are ever unified.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_criteria import (
    CriterionCheck,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_FACTORY_CAPTURED,
    PROOF_MODE_HOST_CAPTURED,
    PROOF_MODE_HUMAN_ATTESTED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_leg import (
    HostAssertionGrade,
    HostLeg,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_leg import (
    PROOF_RECORD_EVIDENCE_LEG,
    AssertionEvidence,
    ProofLeg,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_HOST_VERIFIED,
    ProofRecord,
)

_FACTORY = "The projection carries the parent field."
_HOST = "The released build resolves the mode on an operator host."
_HUMAN = "The production console renders the banner."
_URL = "https://example.test/c/9"


def _record(*, verdict: str = VERDICT_HOST_VERIFIED, url: str = _URL) -> ProofRecord:
    return ProofRecord(verdict=verdict, run_id="replaying", timestamp="t", url=url, body="")


def _evidence(
    *, text: str, mode: str, leg: str, passed: bool | None, comment: str | None = None
) -> AssertionEvidence:
    return AssertionEvidence(
        text=text,
        proof_mode=mode,
        leg=leg,
        record_comment=comment,
        check=None
        if passed is None
        else CriterionCheck(text=text, passed=passed, reason="because"),
    )


def _leg(
    *, assertions: tuple[AssertionEvidence, ...], host: HostLeg, record: ProofRecord | None = None
) -> ProofLeg:
    return ProofLeg(assertions=assertions, record=record, records=(), reason="read", host=host)


def test_a_satisfied_host_leg_leaves_nothing_pending_while_the_human_leg_still_does() -> None:
    """The asymmetric shape: host leg discharged, human leg outstanding.

    If the two projections were ever unified, this is the case that breaks — and it is
    exactly the state a host-captured item reaches the moment its independent replay
    lands, which is when the close gate has to be able to tell the two legs apart.
    """
    host = HostLeg(
        grades=(
            HostAssertionGrade(text=_HOST, passed=True, reason="verified", record_comment=_URL),
        ),
        verified_record=_record(),
        refused=(),
    )

    leg = _leg(
        assertions=(
            _evidence(
                text=_HOST, mode=PROOF_MODE_HOST_CAPTURED, leg="host-captured record", passed=True
            ),
            _evidence(
                text=_HUMAN,
                mode=PROOF_MODE_HUMAN_ATTESTED,
                leg="human-attested record",
                passed=True,
            ),
        ),
        host=host,
    )

    assert leg.pending_host_captured == ()
    assert leg.pending_human_attested == (_HUMAN,)
    assert leg.host_verified_record is not None
    assert leg.host_verified_record.url == _URL


def test_the_pending_host_projection_is_the_host_legs_own_answer() -> None:
    """Read off the host leg, never off the mode — which is what makes it narrow."""
    host = HostLeg(
        grades=(
            HostAssertionGrade(text=_HOST, passed=None, reason="pending", record_comment=None),
        ),
        verified_record=None,
        refused=("a refused record",),
    )

    leg = _leg(
        assertions=(
            _evidence(
                text=_HOST, mode=PROOF_MODE_HOST_CAPTURED, leg="host-captured record", passed=True
            ),
        ),
        host=host,
    )

    assert leg.pending_host_captured == (_HOST,)
    assert leg.host_verified_record is None


def test_an_unevidenced_assertion_is_named_in_the_absent_evidence_leg() -> None:
    """A `None` check is the unevidenced third state, and it names the assertion."""
    leg = _leg(
        assertions=(
            _evidence(
                text=_FACTORY,
                mode=PROOF_MODE_FACTORY_CAPTURED,
                leg=PROOF_RECORD_EVIDENCE_LEG,
                passed=None,
            ),
        ),
        host=HostLeg(grades=(), verified_record=None, refused=()),
    )

    assert leg.unevidenced == (_FACTORY,)
    assert leg.checks == ()
    assert leg.absent_evidence == (f"{PROOF_RECORD_EVIDENCE_LEG} for {_FACTORY!r}",)


def test_the_checks_projection_keeps_definition_of_done_order_and_drops_unevidenced() -> None:
    """The verdict reads `checks`, so its order and its membership both matter."""
    leg = _leg(
        assertions=(
            _evidence(
                text=_FACTORY,
                mode=PROOF_MODE_FACTORY_CAPTURED,
                leg=PROOF_RECORD_EVIDENCE_LEG,
                passed=True,
            ),
            _evidence(
                text=_HOST, mode=PROOF_MODE_HOST_CAPTURED, leg="host-captured record", passed=False
            ),
            _evidence(
                text=_HUMAN,
                mode=PROOF_MODE_HUMAN_ATTESTED,
                leg="human-attested record",
                passed=None,
            ),
        ),
        host=HostLeg(
            grades=(
                HostAssertionGrade(
                    text=_HOST, passed=False, reason="not reproduced", record_comment=_URL
                ),
            ),
            verified_record=None,
            refused=(),
        ),
    )

    assert [check.text for check in leg.checks] == [_FACTORY, _HOST]
    assert [check.passed for check in leg.checks] == [True, False]


def test_the_journal_projection_reports_the_record_and_every_assertions_leg() -> None:
    """The per-assertion record the clause requires of the pass's journal entry."""
    leg = _leg(
        assertions=(
            _evidence(
                text=_FACTORY,
                mode=PROOF_MODE_FACTORY_CAPTURED,
                leg=PROOF_RECORD_EVIDENCE_LEG,
                passed=True,
                comment=_URL,
            ),
        ),
        host=HostLeg(grades=(), verified_record=None, refused=()),
        record=_record(verdict="verified"),
    )

    assert leg.as_record() == {
        "reason": "read",
        "record_comment": _URL,
        "record_run_id": "replaying",
        "record_verdict": "verified",
        "pending_host_captured": [],
        "pending_human_attested": [],
        "assertions": [
            {
                "text": _FACTORY,
                "proof_mode": PROOF_MODE_FACTORY_CAPTURED,
                "evidence_leg": PROOF_RECORD_EVIDENCE_LEG,
                "record_comment": _URL,
                "evidenced": True,
            }
        ],
    }


def test_the_journal_projection_reports_no_record_when_none_was_attributed() -> None:
    """Three nulls rather than an omitted key, so the absence is legible in the journal."""
    leg = _leg(
        assertions=(), host=HostLeg(grades=(), verified_record=None, refused=()), record=None
    )

    projection = leg.as_record()

    assert projection["record_comment"] is None
    assert projection["record_run_id"] is None
    assert projection["record_verdict"] is None
