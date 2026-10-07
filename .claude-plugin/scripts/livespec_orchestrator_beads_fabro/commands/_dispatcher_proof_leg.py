"""The proof leg of one acceptance pass, as a value, with its journal projections.

Split out of `_dispatcher_proof_evidence` along the cohesion seam between WHAT the
proof leg IS and HOW it is obtained: that module performs the forge reads and grades
each assertion, and this one is the value those reads produce plus the projections
every downstream consumer reads off it — the acceptance verdict's check list, the
parking record's pending sets, the pointer's record, and the dispatch journal's
per-assertion record.

WHY THE PROJECTIONS LIVE WITH THE VALUE RATHER THAN WITH THE GRADING. Four different
consumers ask this value four different questions, and none of them should have to
know how it was built. Keeping the questions here is what lets the pointer write
consume the leg the verdict was reached on instead of asking the forge a second time —
the property that makes it impossible for the record the pass graded and the record
the pointer cites to be two different records.

THE TWO PENDING PROJECTIONS ARE DELIBERATELY ASYMMETRIC, and the asymmetry is the most
load-bearing thing in the module. `pending_human_attested` is unconditional: the
ratified clause gives the human leg to the `accept` valve, so this pass never holds
evidence that could retire one. `pending_host_captured` is NOT — it reports only the
host-captured assertions still awaiting an independent replay, because the pass DOES
grade that leg. That projection is what the completion disposition's close gate reads,
so a reader who "simplified" it into the symmetric unconditional form would leave every
host-captured item resting in `acceptance` for ever, on a verdict of PASS, with a
verified host record sitting on its pull request.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_criteria import (
    CriterionCheck,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_HOST_CAPTURED,
    PROOF_MODE_HUMAN_ATTESTED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_leg import HostLeg
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import ProofRecord

__all__: list[str] = [
    "PROOF_RECORD_EVIDENCE_LEG",
    "AssertionEvidence",
    "ProofLeg",
]

PROOF_RECORD_EVIDENCE_LEG = "proof of done record"


@dataclass(frozen=True, kw_only=True)
class AssertionEvidence:
    """One effective assertion, the leg that evidenced it, and the record read."""

    text: str
    proof_mode: str
    leg: str
    record_comment: str | None
    check: CriterionCheck | None

    def as_record(self) -> dict[str, object]:
        """The per-assertion journal projection the clause requires of the pass."""
        return {
            "text": self.text,
            "proof_mode": self.proof_mode,
            "evidence_leg": self.leg,
            "record_comment": self.record_comment,
            "evidenced": self.check is not None,
        }


@dataclass(frozen=True, kw_only=True)
class ProofLeg:
    """The proof leg of one acceptance pass: per assertion, plus the record read.

    `host` is the host leg's own verdict, carried rather than recomputed: the pointer
    needs the `host_verified` record it rested on, the parking record needs the
    pending set, and a second grading could disagree with the one the verdict used.
    """

    assertions: tuple[AssertionEvidence, ...]
    record: ProofRecord | None
    records: tuple[ProofRecord, ...]
    reason: str
    host: HostLeg

    @property
    def checks(self) -> tuple[CriterionCheck, ...]:
        """The graded checks, in Definition of Done order."""
        return tuple(one.check for one in self.assertions if one.check is not None)

    @property
    def unevidenced(self) -> tuple[str, ...]:
        """The assertions the record evidenced neither way."""
        return tuple(one.text for one in self.assertions if one.check is None)

    @property
    def pending_host_captured(self) -> tuple[str, ...]:
        """The host-captured assertions STILL awaiting an independent host replay.

        Read off the host leg rather than off the mode, which is the change that
        makes a host-captured item closeable: an assertion a `host_verified` record
        has passed is no longer pending, and the completion disposition's close gate
        reads exactly this set.
        """
        return self.host.pending

    @property
    def host_verified_record(self) -> ProofRecord | None:
        """The `host_verified` record this pass rested on, for the pointer to cite."""
        return self.host.verified_record

    @property
    def host_captured_only(self) -> bool:
        """Whether EVERY assertion this item declares is `host_captured`.

        The question the pointer write asks before it may cite a HOST record as the
        record the merge was judged against. It is deliberately a property of the
        DECLARED modes rather than of which records happened to be readable: the
        item's Definition of Done is what decides whether a factory `verified`
        record is owed at all, and a run whose factory record was merely
        unattributable still owes one.

        That is what keeps the factory attribution fail-closed. A MIXED item whose
        `verified` record could not be attributed has `factory_captured` assertions
        with no evidence — they are unevidenced, the pass reaches NEEDS_ATTENTION,
        and promoting a host record into its pointer would advertise provenance for
        a merge whose factory leg nothing graded.

        An item with NO assertions answers False rather than True, which is the
        same fail-closed direction: `all()` over an empty sequence is vacuously
        true, and a leg carrying no assertions has no host evidence to be the whole
        of.
        """
        return bool(self.assertions) and all(
            one.proof_mode == PROOF_MODE_HOST_CAPTURED for one in self.assertions
        )

    @property
    def pending_human_attested(self) -> tuple[str, ...]:
        """The assertions awaiting a human-attested record, in section order.

        Unconditional on purpose, unlike the host projection above: the clause gives
        the human leg to the `accept` valve, so this pass never has evidence that
        could retire one.
        """
        return tuple(
            one.text for one in self.assertions if one.proof_mode == PROOF_MODE_HUMAN_ATTESTED
        )

    @property
    def absent_evidence(self) -> tuple[str, ...]:
        """One absent-evidence leg per unevidenced assertion, NAMING the assertion.

        Named rather than counted because the clause requires the verdict to name
        the assertion: an operator told only that "the proof leg is absent" has to
        read the whole record to find out which of five assertions it failed to
        evidence.
        """
        return tuple(f"{PROOF_RECORD_EVIDENCE_LEG} for {text!r}" for text in self.unevidenced)

    def as_record(self) -> dict[str, object]:
        """The journal projection naming, per assertion, its leg and record comment."""
        return {
            "reason": self.reason,
            "record_comment": None if self.record is None else self.record.url,
            "record_run_id": None if self.record is None else self.record.run_id,
            "record_verdict": None if self.record is None else self.record.verdict,
            "pending_host_captured": list(self.pending_host_captured),
            "pending_human_attested": list(self.pending_human_attested),
            "assertions": [one.as_record() for one in self.assertions],
        }
