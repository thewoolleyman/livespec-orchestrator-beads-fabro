"""Tests for the proof evidence leg's own reads and its unevidenced third state.

`test_dispatcher_proof_evidence_leg.py` binds the leg through the whole
acceptance pass, which is where the ratified behaviour lives. This module covers
the reads and refusals that pass cannot reach from one green fixture: the three
ways the merging run's record fails to be observable, the human-attested
assertion that rides as pending, and the UNOBSERVED-versus-EMPTY distinction in
the comments read — a pull request with no records is evidence that none were
published, a failed read is evidence of nothing, and the two must not produce the
same verdict.
"""

from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_FACTORY_CAPTURED,
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import (
    HUMAN_ATTESTED_EVIDENCE_LEG,
    PENDING_HUMAN_ATTESTATION_REASON,
    PROOF_RECORD_EVIDENCE_LEG,
    proof_leg,
    read_proof_leg,
    read_pull_request_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_VERIFIED,
    proof_records,
)

_RUN_ID = "01M3EVIDENCERUN"
_FACTORY_ASSERTION = "The projection carries the parent field."
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


def _outcome(*, pr_number: int | None = 7, run_id: str | None = _RUN_ID) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-evidence",
        status="green",
        stage="done",
        pr_number=pr_number,
        merge_sha="abc123",
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
    )
    unreadable_leg = read_proof_leg(
        repo=tmp_path, criteria=_factory_criteria(), outcome=_outcome(), runner=unreadable
    )
    no_run_id = read_proof_leg(
        repo=tmp_path,
        criteria=_factory_criteria(),
        outcome=_outcome(run_id=None),
        runner=readable,
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
        repo=tmp_path, criteria=_factory_criteria(), outcome=_outcome(), runner=runner
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

    leg = read_proof_leg(repo=tmp_path, criteria=criteria, outcome=_outcome(), runner=runner)

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

    leg = proof_leg(criteria=criteria, records=records, run_id=_RUN_ID, reason="read")

    assert leg.pending_human_attested == (_HUMAN_ASSERTION,)
    assert leg.unevidenced == ()
    assert [check.passed for check in leg.checks] == [True, True]
    assert [check.reason for check in leg.checks][1] == PENDING_HUMAN_ATTESTATION_REASON
    assert [one.leg for one in leg.assertions] == [
        PROOF_RECORD_EVIDENCE_LEG,
        HUMAN_ATTESTED_EVIDENCE_LEG,
    ]


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
        criteria=criteria, records=records, run_id=_RUN_ID, reason="read"
    ).as_record()

    assert projection == {
        "reason": "read",
        "record_comment": "https://example.test/c/9",
        "record_run_id": _RUN_ID,
        "record_verdict": VERDICT_VERIFIED,
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
        criteria=_factory_criteria(), records=(), run_id=None, reason="nothing read"
    ).as_record()

    assert projection["record_comment"] is None
    assert projection["record_run_id"] is None
    assert projection["record_verdict"] is None
