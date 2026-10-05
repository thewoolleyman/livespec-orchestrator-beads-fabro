"""Tests for the proof evidence leg's own reads and its unevidenced third state.

`test_dispatcher_proof_evidence_leg.py` binds the leg through the whole
acceptance pass, which is where the ratified behaviour lives. This module covers
the reads and refusals that pass cannot reach from one green fixture: the three
ways the merging run's record fails to be observable, the human-attested
assertion that rides as pending, and the UNOBSERVED-versus-EMPTY distinction in
the comments read — a pull request with no records is evidence that none were
published, a failed read is evidence of nothing, and the two must not produce the
same verdict.

IT ALSO COVERS THE HOST LEG'S ARRIVAL INTO THIS MODULE. `_dispatcher_host_leg` owns
the evidence rule and is tested there; what is tested HERE is the join — that the
pure grading receives a containment reader, that `read_proof_leg` resolves that
reader through the forge, and that each disposition the host leg can reach lands in
the right shape on `ProofLeg`: a PASS drops the assertion from
`pending_host_captured` (which is what lets the item close), a FAIL becomes a
failing check (which is what routes it to rework), and every refusal stays pending
with the reason reported on the check.
"""

from __future__ import annotations

import json
import textwrap
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_FACTORY_CAPTURED,
    PROOF_MODE_HOST_CAPTURED,
    PROOF_MODE_HUMAN_ATTESTED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    DESCRIPTION_DEFINITION_OF_DONE_SOURCE,
    EffectiveCriteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    RELEASE_TAG_LABEL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_containment import (
    compare_argv,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_leg import (
    NOT_EVIDENCE_CONTAINMENT,
    NOT_EVIDENCE_SELF_REPLAY,
    NOT_EVIDENCE_UNOBSERVABLE_CONTAINMENT,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_attribution import (
    MergingDispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import (
    HOST_CAPTURED_EVIDENCE_LEG,
    HUMAN_ATTESTED_EVIDENCE_LEG,
    PENDING_HOST_LEG_REASON,
    PENDING_HUMAN_ATTESTATION_REASON,
    proof_leg,
    read_proof_leg,
    read_pull_request_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_leg import (
    PROOF_RECORD_EVIDENCE_LEG,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_VERIFIED,
    ProofRecord,
    proof_records,
)

_RUN_ID = "01M3EVIDENCERUN"
_RELEASE_TAG = "v0.166.0"
_FACTORY_ASSERTION = "The projection carries the parent field."
_HOST_ASSERTION = "The released build resolves the mode on an operator host."
_HUMAN_ASSERTION = "The production console renders the banner."


@dataclass(kw_only=True)
class _Runner:
    result: CommandResult
    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        self.argvs.append(list(argv))
        return self.result


@dataclass(kw_only=True)
class _SequencedRunner:
    """A runner answering a SEQUENCE of reads, so a second call cannot reuse the first.

    The host leg's read makes two different forge calls — the comment read and the
    containment comparison — and a single-result double would answer the comparison
    with the comment payload, which parses as an unknown status and refuses. The
    refusal would look exactly like the one a genuinely unreadable comparison earns.
    """

    results: list[CommandResult]
    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        self.argvs.append(list(argv))
        return self.results.pop(0)


def _criteria(*, modes: tuple[str, ...], assertions: tuple[str, ...]) -> EffectiveCriteria:
    return EffectiveCriteria(
        text="\n".join(assertions),
        source=DESCRIPTION_DEFINITION_OF_DONE_SOURCE,
        assertions=assertions,
        proof_modes=modes,
    )


def _factory_criteria() -> EffectiveCriteria:
    return _criteria(modes=(PROOF_MODE_FACTORY_CAPTURED,), assertions=(_FACTORY_ASSERTION,))


def _verified_comments(*, run_id: str = _RUN_ID) -> str:
    body = textwrap.dedent(f"""\
        Proof of Done — verified — run {run_id} — 2026-10-01T09:00:00Z

        ## Assertion 1 — {_FACTORY_ASSERTION}

        Reproduced: yes.
        """)
    return json.dumps({"comments": [{"url": "https://example.test/c/9", "body": body}]})


def _dispatch(*, run_id: str | None = _RUN_ID) -> MergingDispatch:
    """The no-journal attribution: the outcome's own Fabro run id and nothing else.

    Every case in this module is about the READ rather than about the widening, so
    it hands the leg the narrowest identifier set a real dispatch can produce —
    which is also what the pass resolves when no dispatch journal is available.
    The widening itself is bound in `test_dispatcher_proof_attribution.py`.
    """
    return MergingDispatch(fabro_run_id=run_id, dispatch_id=None)


def _outcome(
    *,
    pr_number: int | None = 7,
    run_id: str | None = _RUN_ID,
    merge_sha: str | None = "abc123",
) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-evidence",
        status="green",
        stage="done",
        pr_number=pr_number,
        merge_sha=merge_sha,
        detail="merged",
        fabro_run_id=run_id,
    )


def test_an_unreadable_comments_payload_is_unobserved_not_an_empty_record_set(
    tmp_path: Path,
) -> None:
    """Every arm of the read that cannot yield records, each one distinct.

    A non-zero exit, output that is not JSON, output that is JSON but not an
    object, and an object whose `comments` key is not a list all answer `None`.
    The positive control is the last assertion: the SAME reader returns an empty
    tuple for a pull request that genuinely carries no record, which is the
    answer the three refusals must not be confused with.
    """
    for stdout, exit_code in (
        ("", 1),
        ("not json at all", 0),
        ("[1, 2]", 0),
        (json.dumps({"comments": "nope"}), 0),
    ):
        runner = _Runner(result=CommandResult(exit_code=exit_code, stdout=stdout, stderr=""))

        assert read_pull_request_records(repo=tmp_path, pr_number=7, runner=runner) is None

    empty = _Runner(
        result=CommandResult(exit_code=0, stdout=json.dumps({"comments": []}), stderr="")
    )

    assert read_pull_request_records(repo=tmp_path, pr_number=7, runner=empty) == ()


def test_a_non_object_comment_entry_is_dropped(tmp_path: Path) -> None:
    runner = _Runner(
        result=CommandResult(
            exit_code=0, stdout=json.dumps({"comments": ["a string", 7]}), stderr=""
        )
    )

    assert read_pull_request_records(repo=tmp_path, pr_number=7, runner=runner) == ()


def test_the_three_unobservable_reads_each_name_their_own_reason(tmp_path: Path) -> None:
    """A dispatch with no pull request, an unreadable read, and no run id.

    All three leave the assertion unevidenced, and the `reason` is the only thing
    that tells an operator which of the three happened.
    """
    unreadable = _Runner(result=CommandResult(exit_code=1, stdout="", stderr="boom"))
    readable = _Runner(result=CommandResult(exit_code=0, stdout=_verified_comments(), stderr=""))

    no_pull_request = read_proof_leg(
        repo=tmp_path,
        criteria=_factory_criteria(),
        outcome=_outcome(pr_number=None),
        runner=unreadable,
        dispatch=_dispatch(),
    )
    unreadable_leg = read_proof_leg(
        repo=tmp_path,
        criteria=_factory_criteria(),
        outcome=_outcome(),
        runner=unreadable,
        dispatch=_dispatch(),
    )
    no_run_id = read_proof_leg(
        repo=tmp_path,
        criteria=_factory_criteria(),
        outcome=_outcome(run_id=None),
        runner=readable,
        dispatch=_dispatch(run_id=None),
    )

    assert no_pull_request.reason == "pull request number unavailable"
    assert unreadable_leg.reason == "pull request #7 comments unreadable"
    assert no_run_id.reason == "merging run id unavailable"
    for leg in (no_pull_request, unreadable_leg, no_run_id):
        assert leg.unevidenced == (_FACTORY_ASSERTION,)
        assert leg.checks == ()
        assert leg.absent_evidence == (f"{PROOF_RECORD_EVIDENCE_LEG} for {_FACTORY_ASSERTION!r}",)
    # The no-run-id leg READ the records; it simply cannot attribute one to the
    # merging run. That is why its record set is non-empty and its record is not.
    assert no_run_id.records != ()
    assert no_run_id.record is None
    assert no_pull_request.records == ()


def test_a_verified_record_for_another_run_does_not_evidence_this_merge(
    tmp_path: Path,
) -> None:
    runner = _Runner(
        result=CommandResult(exit_code=0, stdout=_verified_comments(run_id="other"), stderr="")
    )

    leg = read_proof_leg(
        repo=tmp_path,
        criteria=_factory_criteria(),
        outcome=_outcome(),
        runner=runner,
        dispatch=_dispatch(),
    )

    assert leg.record is None
    assert leg.unevidenced == (_FACTORY_ASSERTION,)
    assert leg.reason == f"pull request #7 records read for run {_RUN_ID}"


def test_a_record_that_omits_the_assertion_leaves_it_unevidenced_naming_the_record(
    tmp_path: Path,
) -> None:
    """The record IS this run's, and still evidences nothing about this assertion."""
    criteria = _criteria(
        modes=(PROOF_MODE_FACTORY_CAPTURED,), assertions=("An assertion nobody captured.",)
    )
    runner = _Runner(result=CommandResult(exit_code=0, stdout=_verified_comments(), stderr=""))

    leg = read_proof_leg(
        repo=tmp_path,
        criteria=criteria,
        outcome=_outcome(),
        runner=runner,
        dispatch=_dispatch(),
    )

    assert leg.record is not None
    assert leg.unevidenced == ("An assertion nobody captured.",)
    assert [one.record_comment for one in leg.assertions] == ["https://example.test/c/9"]


def test_a_human_attested_assertion_rides_as_pending_rather_than_graded() -> None:
    criteria = _criteria(
        modes=(PROOF_MODE_FACTORY_CAPTURED, PROOF_MODE_HUMAN_ATTESTED),
        assertions=(_FACTORY_ASSERTION, _HUMAN_ASSERTION),
    )
    records = proof_records(
        comments=[
            {
                "url": "https://example.test/c/9",
                "body": (
                    f"Proof of Done — verified — run {_RUN_ID} — t\n\n"
                    f"## Assertion 1 — {_FACTORY_ASSERTION}\n\nReproduced: yes.\n"
                ),
            }
        ]
    )

    leg = proof_leg(criteria=criteria, records=records, run_ids=(_RUN_ID,), reason="read")

    assert leg.pending_human_attested == (_HUMAN_ASSERTION,)
    assert leg.unevidenced == ()
    assert [check.passed for check in leg.checks] == [True, True]
    assert [check.reason for check in leg.checks][1] == PENDING_HUMAN_ATTESTATION_REASON
    assert [one.leg for one in leg.assertions] == [
        PROOF_RECORD_EVIDENCE_LEG,
        HUMAN_ATTESTED_EVIDENCE_LEG,
    ]


def test_a_host_captured_assertion_rides_as_pending_the_host_leg() -> None:
    """The v115 third mode reaches the leg as PENDING, never as absent evidence.

    `unevidenced == ()` is the load-bearing assertion and the one that separates
    this from the pre-repair behaviour: an assertion routed through
    `absent_evidence` makes the whole pass NEEDS_ATTENTION, which parks the item on
    a cannot-judge verdict and reports the merging run's `verified` record — which
    exists here, and which the factory assertion is graded against — as the missing
    thing.
    """
    criteria = _criteria(
        modes=(PROOF_MODE_FACTORY_CAPTURED, PROOF_MODE_HOST_CAPTURED),
        assertions=(_FACTORY_ASSERTION, _HOST_ASSERTION),
    )
    records = proof_records(
        comments=[
            {
                "url": "https://example.test/c/9",
                "body": (
                    f"Proof of Done — verified — run {_RUN_ID} — t\n\n"
                    f"## Assertion 1 — {_FACTORY_ASSERTION}\n\nReproduced: yes.\n"
                ),
            }
        ]
    )

    leg = proof_leg(criteria=criteria, records=records, run_ids=(_RUN_ID,), reason="read")

    assert leg.pending_host_captured == (_HOST_ASSERTION,)
    assert leg.pending_human_attested == ()
    assert leg.unevidenced == ()
    assert leg.absent_evidence == ()
    assert [check.passed for check in leg.checks] == [True, True]
    assert [check.reason for check in leg.checks][1] == PENDING_HOST_LEG_REASON
    assert [one.leg for one in leg.assertions] == [
        PROOF_RECORD_EVIDENCE_LEG,
        HOST_CAPTURED_EVIDENCE_LEG,
    ]


def _host_comments(
    *,
    verdict: str = "host_verified",
    identity: str = "replaying-session",
    recorded_by: str | None = None,
    release_tag: str = _RELEASE_TAG,
    reproduced: str = "yes",
) -> tuple[ProofRecord, ...]:
    """A host replay on the pull request, optionally preceded by its own capture.

    `recorded_by` publishes a `host_recorded` record FIRST, which is what gives the
    leg a capturing identity to compare the replay against. Without one no replay can
    be a self-replay, because there is no capture for it to be a replay of.
    """
    capture = (
        []
        if recorded_by is None
        else [
            {
                "url": "https://example.test/c/8",
                "body": (
                    f"Proof of Done — host_recorded — session {recorded_by} — t\n\n"
                    f"- {RELEASE_TAG_LABEL}: {release_tag}\n\n"
                    f"## Assertion 1 — {_HOST_ASSERTION}\n"
                ),
            }
        ]
    )
    replay = {
        "url": "https://example.test/c/9",
        "body": (
            f"Proof of Done — {verdict} — session {identity} — t\n\n"
            f"- {RELEASE_TAG_LABEL}: {release_tag}\n\n"
            f"## Assertion 1 — {_HOST_ASSERTION}\n\nReproduced: {reproduced}.\n"
        ),
    }
    return proof_records(comments=[*capture, replay])


def _contains(*, answer: bool | None) -> Callable[[str], bool | None]:
    return lambda ref: answer if ref == _RELEASE_TAG else None


def test_an_independent_host_verified_record_grades_the_assertion_passing() -> None:
    """The host leg now DECIDES, which is what lets a host-captured item close.

    Before this slice a `host_verified` record left the assertion pending whatever it
    said, because the containment check and the identity-independence rule had not
    been built. Both arrive here, so a replay that clears them passes the assertion
    and `pending_host_captured` drops it — and that projection is exactly what the
    completion disposition reads to decide whether the item may close.
    """
    criteria = _criteria(modes=(PROOF_MODE_HOST_CAPTURED,), assertions=(_HOST_ASSERTION,))

    leg = proof_leg(
        criteria=criteria,
        records=_host_comments(recorded_by="capturing-session"),
        run_ids=(_RUN_ID,),
        reason="read",
        contains_merge=_contains(answer=True),
    )

    assert leg.pending_host_captured == ()
    assert [check.passed for check in leg.checks] == [True]
    assert leg.host_verified_record is not None
    assert leg.host_verified_record.url == "https://example.test/c/9"
    assert _RELEASE_TAG in leg.checks[0].reason


def test_a_self_replayed_host_record_leaves_the_assertion_pending_and_reports_why() -> None:
    """The identity-independence rule, enforced by the PASS however the record arrived."""
    criteria = _criteria(modes=(PROOF_MODE_HOST_CAPTURED,), assertions=(_HOST_ASSERTION,))

    leg = proof_leg(
        criteria=criteria,
        records=_host_comments(identity="one-session", recorded_by="one-session"),
        run_ids=(_RUN_ID,),
        reason="read",
        contains_merge=_contains(answer=True),
    )

    assert leg.pending_host_captured == (_HOST_ASSERTION,)
    assert leg.host_verified_record is None
    assert NOT_EVIDENCE_SELF_REPLAY in leg.checks[0].reason


def test_a_host_record_against_a_build_without_the_merge_stays_pending_and_reports_why() -> None:
    """The containment check the clause requires the pass to verify itself."""
    criteria = _criteria(modes=(PROOF_MODE_HOST_CAPTURED,), assertions=(_HOST_ASSERTION,))

    leg = proof_leg(
        criteria=criteria,
        records=_host_comments(recorded_by="capturing-session"),
        run_ids=(_RUN_ID,),
        reason="read",
        contains_merge=_contains(answer=False),
    )

    assert leg.pending_host_captured == (_HOST_ASSERTION,)
    assert NOT_EVIDENCE_CONTAINMENT in leg.checks[0].reason
    assert _RELEASE_TAG in leg.checks[0].reason


def test_an_independent_host_not_reproduced_record_fails_the_assertion() -> None:
    """A replay that did not reproduce is a FAILING check, which is rework input."""
    criteria = _criteria(modes=(PROOF_MODE_HOST_CAPTURED,), assertions=(_HOST_ASSERTION,))

    leg = proof_leg(
        criteria=criteria,
        records=_host_comments(
            verdict="host_not_reproduced", recorded_by="capturing-session", reproduced="no"
        ),
        run_ids=(_RUN_ID,),
        reason="read",
        contains_merge=_contains(answer=True),
    )

    assert leg.pending_host_captured == ()
    assert [check.passed for check in leg.checks] == [False]
    assert leg.host_verified_record is None


def test_an_unchecked_containment_refuses_every_host_record(tmp_path: Path) -> None:
    """With no containment reader the leg refuses, which is the fail-closed default.

    `contains_merge` defaults to "not checked" rather than to "contained" so that a
    caller which forgot to supply one parks the item instead of closing it on a build
    nothing compared. The one production caller — `read_proof_leg` — always supplies
    one, which the read test below asserts by its forge calls.
    """
    del tmp_path
    criteria = _criteria(modes=(PROOF_MODE_HOST_CAPTURED,), assertions=(_HOST_ASSERTION,))

    leg = proof_leg(
        criteria=criteria,
        records=_host_comments(recorded_by="capturing-session"),
        run_ids=(_RUN_ID,),
        reason="read",
    )

    assert leg.pending_host_captured == (_HOST_ASSERTION,)
    assert NOT_EVIDENCE_UNOBSERVABLE_CONTAINMENT in leg.checks[0].reason


def test_the_read_checks_containment_through_the_forge_for_each_named_build(
    tmp_path: Path,
) -> None:
    """`read_proof_leg` resolves the containment the pure grading consumes.

    The comparison argv is asserted so the read cannot come to ask a question the
    host leg's own tests never exercised, and it is asserted ONCE per distinct build
    rather than once per record: two replays naming the same release are one
    comparison, and a reader that re-asked per record would spend a forge round trip
    per published record on every pass.
    """
    comments = json.dumps(
        {
            "comments": [
                {
                    "url": "https://example.test/c/9",
                    "body": (
                        "Proof of Done — host_verified — session replaying — t\n\n"
                        f"- {RELEASE_TAG_LABEL}: {_RELEASE_TAG}\n\n"
                        f"## Assertion 1 — {_HOST_ASSERTION}\n\nReproduced: yes.\n"
                    ),
                },
                {
                    "url": "https://example.test/c/10",
                    "body": (
                        "Proof of Done — host_verified — session second — t\n\n"
                        f"- {RELEASE_TAG_LABEL}: {_RELEASE_TAG}\n\n"
                        f"## Assertion 1 — {_HOST_ASSERTION}\n\nReproduced: yes.\n"
                    ),
                },
            ]
        }
    )
    runner = _SequencedRunner(
        results=[
            CommandResult(exit_code=0, stdout=comments, stderr=""),
            CommandResult(exit_code=0, stdout="ahead\n", stderr=""),
        ]
    )

    leg = read_proof_leg(
        repo=tmp_path,
        criteria=_criteria(modes=(PROOF_MODE_HOST_CAPTURED,), assertions=(_HOST_ASSERTION,)),
        outcome=_outcome(),
        runner=runner,
        dispatch=_dispatch(),
    )

    assert runner.argvs[1] == compare_argv(base="abc123", head=_RELEASE_TAG)
    assert len(runner.argvs) == 2
    assert leg.pending_host_captured == ()


def test_the_read_skips_the_comparison_when_the_merge_sha_is_unknown(tmp_path: Path) -> None:
    """With no merge commit there is nothing to check containment OF, so none is run.

    The assertion stays pending rather than passing, because a replay whose
    containment was never established is not evidence — the same answer the
    unobservable arm gives, reached without spending a forge call that could not
    have a meaningful base.
    """
    comments = json.dumps(
        {
            "comments": [
                {
                    "url": "https://example.test/c/9",
                    "body": (
                        "Proof of Done — host_verified — session replaying — t\n\n"
                        f"- {RELEASE_TAG_LABEL}: {_RELEASE_TAG}\n\n"
                        f"## Assertion 1 — {_HOST_ASSERTION}\n\nReproduced: yes.\n"
                    ),
                }
            ]
        }
    )
    runner = _SequencedRunner(results=[CommandResult(exit_code=0, stdout=comments, stderr="")])

    leg = read_proof_leg(
        repo=tmp_path,
        criteria=_criteria(modes=(PROOF_MODE_HOST_CAPTURED,), assertions=(_HOST_ASSERTION,)),
        outcome=_outcome(merge_sha=None),
        runner=runner,
        dispatch=_dispatch(),
    )

    assert len(runner.argvs) == 1
    assert leg.pending_host_captured == (_HOST_ASSERTION,)


def test_the_journal_projection_names_the_leg_and_record_per_assertion() -> None:
    criteria = _criteria(
        modes=(PROOF_MODE_FACTORY_CAPTURED, PROOF_MODE_HUMAN_ATTESTED),
        assertions=(_FACTORY_ASSERTION, _HUMAN_ASSERTION),
    )
    records = proof_records(
        comments=[
            {
                "url": "https://example.test/c/9",
                "body": (
                    f"Proof of Done — verified — run {_RUN_ID} — 2026-10-01T09:00:00Z\n\n"
                    f"## Assertion 1 — {_FACTORY_ASSERTION}\n\nReproduced: yes.\n"
                ),
            }
        ]
    )

    projection = proof_leg(
        criteria=criteria, records=records, run_ids=(_RUN_ID,), reason="read"
    ).as_record()

    assert projection == {
        "reason": "read",
        "record_comment": "https://example.test/c/9",
        "record_run_id": _RUN_ID,
        "record_verdict": VERDICT_VERIFIED,
        "pending_host_captured": [],
        "pending_human_attested": [_HUMAN_ASSERTION],
        "assertions": [
            {
                "text": _FACTORY_ASSERTION,
                "proof_mode": PROOF_MODE_FACTORY_CAPTURED,
                "evidence_leg": PROOF_RECORD_EVIDENCE_LEG,
                "record_comment": "https://example.test/c/9",
                "evidenced": True,
            },
            {
                "text": _HUMAN_ASSERTION,
                "proof_mode": PROOF_MODE_HUMAN_ATTESTED,
                "evidence_leg": HUMAN_ATTESTED_EVIDENCE_LEG,
                "record_comment": None,
                "evidenced": True,
            },
        ],
    }


def test_the_projection_reports_no_record_when_none_was_attributed() -> None:
    projection = proof_leg(
        criteria=_factory_criteria(), records=(), run_ids=(), reason="nothing read"
    ).as_record()

    assert projection["record_comment"] is None
    assert projection["record_run_id"] is None
    assert projection["record_verdict"] is None
