"""Two real record payloads, read by the real proof-evidence leg, fences and all.

This module is the measured half of work-item `bd-ib-2z5wt2`. The synthetic
coverage lives in
`tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_proof_record.py`;
what it cannot do is prove the repair works on the bytes a REAL factory published,
and the defect it repairs was invisible to every synthetic fixture precisely
because a hand-written record body carries no fenced proof — the hazard arrives
only when the proof PRINTS something, which is what every real proof does.

THE DEFECT, AS MEASURED. `_dispatcher_proof_record._sections` split the record
body at every line matching `^#{1,6}\\s`, and the proofs inside those sections are
fenced code blocks whose lines routinely begin with a hash: shell comments, Python
comments, and the printed headings of a Markdown file. Each such line opened a new
section, so an assertion's section ended BEFORE its own `Reproduced:` line and the
reader answered `None` — UNEVIDENCED — for an assertion the record states was
reproduced. Measured 2026-10-04 against the pre-repair reader: PR #2561's verified
record graded `[None, None, True, True]` and PR #2538's graded
`[True, True, True, None]`, so five of eight assertions across two correctly
attributed, correctly published verified records read as unobserved and both items
parked on NEEDS_ATTENTION.

THE PAYLOADS ARE COMMITTED, NOT FETCHED, for the reason the sibling attribution
module records: a test that fetched them live would depend on the forge and would
stop being a test of this repository. Each is the verbatim
`gh api repos/thewoolleyman/livespec-orchestrator-beads-fabro/issues/<n>/comments`
answer, reshaped only into the `{"comments": [...]}` envelope `gh pr view --json
comments` returns — which is the argv the pass actually runs. No field was edited.

THE CONTROLS ARE WHAT MAKE "ALL FOUR PASSED" WORTH ANYTHING, and there are three,
because the claim has three independent ways to be vacuous. A reader that answered
`True` for everything would satisfy it, so a fabricated assertion is graded against
the same record and must stay unevidenced. A payload carrying no heading-like line
inside a fence would never have exercised the splitter, so each record's hazard is
counted off its own committed bytes. And a reader that had stopped reading the
`Reproduced:` line at all would also pass, so PR #2561's `not_reproduced` record —
whose first assertion says `Reproduced: NO.` while the other three say yes, and
which carries fenced hash lines of its own — is graded in the same breath and must
still report that one assertion as NOT reproduced.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_FACTORY_CAPTURED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    DESCRIPTION_DEFINITION_OF_DONE_SOURCE,
    EffectiveCriteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_attribution import (
    MergingDispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import (
    ProofLeg,
    read_proof_leg,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_NOT_REPRODUCED,
    VERDICT_VERIFIED,
    latest_proof_record,
    proof_records,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "proof_records"
# The reader's own heading pattern, restated so the hazard census below is a claim
# about the committed bytes rather than a second call into the code under test.
_HEADING = re.compile(r"^#{1,6}\s")

# PR #2561 merged work-item `bd-ib-2s3kkq` as `52aa6ee7`. Its records are stamped
# `6a9a2d129e934e74987b8a9203ff6a5d`, the DISPATCH id — the same value the merge
# commit carries as its `Factory-Run-Id` trailer — and the dispatch that merged it
# is modelled with no Fabro run id at all, which is the shape `reconcile-merged`
# resolves when it rebuilds an outcome from a merged pull request.
_PR_2561 = 2561
_DISPATCH_ID_2561 = "6a9a2d129e934e74987b8a9203ff6a5d"
_VERIFIED_RECORD_URL_2561 = (
    "https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/pull/2561"
    "#issuecomment-5979532725"
)
_NOT_REPRODUCED_RECORD_URL_2561 = (
    "https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/pull/2561"
    "#issuecomment-5979222402"
)
# `bd-ib-2s3kkq`'s four Definition-of-Done assertions, transcribed from the
# headings its records publish. The record clause requires each one to appear
# verbatim, so the published headings are the faithful transcription available to a
# sandbox with no ledger connection; the load-bearing claim below is about SECTION
# SEGMENTATION, which no transcription of the assertions can affect.
_ASSERTIONS_2561 = (
    "A proof_capture visit that ends with preferred_label fix publishes a record whose"
    " first line carries the verdict not_captured, naming the assertions it could not"
    " capture and the finding.",
    "The third preferred_label fix from proof_capture in one run routes to the"
    " non_converged terminal of the committed implement-work-item graph.",
    "The fix prompt directs the stage to read the latest proof record on the pull"
    " request when its preamble carries no finding, and to end through the structured"
    " needs-human ending rather than succeed on an unchanged tree.",
    "A red janitor outcome still routes to the fix stage with the janitor failure"
    " output as before.",
)

# PR #2538 merged work-item `bd-ib-mxqrr4` as `52783f67`. Its payload is the one
# the sibling attribution module reads, and both identifiers of its dispatch are
# known, so this leg models the ordinary dispatch-path shape rather than the
# reconcile one.
_PR_2538 = 2538
_FABRO_RUN_ID_2538 = "01M3WH8Z10278S5V4SV9WRYW20"
_DISPATCH_ID_2538 = "f195238b76b942698485a780611fe1ef"
_VERIFIED_RECORD_URL_2538 = (
    "https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/pull/2538"
    "#issuecomment-5940752598"
)
_ASSERTIONS_2538 = (
    "dev-tooling/just-check.sh derives its executed target list from the justfile"
    " check recipe's targets array.",
    "A test or check fails when a slug listed in the justfile check recipe's targets"
    " array is absent from the set the runner executes.",
    "Running just check executes check-spec-governance-default-block and the other"
    " nine previously unrun slugs.",
    "The aggregate's final passed-count line reports the number of targets actually executed.",
)

# An assertion no record on either pull request mentions. It is the control for
# every "all four passed" claim below: a reader answering `True` for whatever it is
# handed grades this one too.
_FABRICATED_ASSERTION = "The reader invents evidence for an assertion nobody published."


@dataclass(kw_only=True)
class _CommentsRunner:
    """The pass's command seam, answering the comments read with a real payload."""

    stdout: str
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
        return CommandResult(exit_code=0, stdout=self.stdout, stderr="")


def _payload(*, pr_number: int) -> str:
    return (_FIXTURES / f"pull-request-{pr_number}-comments.json").read_text(encoding="utf-8")


def _criteria(*, assertions: tuple[str, ...]) -> EffectiveCriteria:
    return EffectiveCriteria(
        text="\n".join(f"- {one}" for one in assertions),
        source=DESCRIPTION_DEFINITION_OF_DONE_SOURCE,
        assertions=assertions,
        proof_modes=(PROOF_MODE_FACTORY_CAPTURED,) * len(assertions),
    )


def _leg(
    *,
    pr_number: int,
    work_item_id: str,
    merge_sha: str,
    assertions: tuple[str, ...],
    dispatch: MergingDispatch,
    tmp_path: Path,
) -> ProofLeg:
    return read_proof_leg(
        repo=tmp_path,
        criteria=_criteria(assertions=assertions),
        outcome=DispatchOutcome(
            work_item_id=work_item_id,
            status="green",
            stage="done",
            pr_number=pr_number,
            merge_sha=merge_sha,
            detail="merged",
            fabro_run_id=dispatch.fabro_run_id,
        ),
        runner=_CommentsRunner(stdout=_payload(pr_number=pr_number)),
        dispatch=dispatch,
    )


def test_every_assertion_of_pull_request_2561_grades_from_its_verified_record(
    tmp_path: Path,
) -> None:
    """The repair, on the bytes PR #2561's verifier published.

    The fabricated assertion rides in the SAME criteria rather than in a second
    case, so it is graded against the same record in the same pass: a fifth
    assertion the record never mentions must still come back unevidenced while the
    four it does mention all pass.
    """
    leg = _leg(
        pr_number=_PR_2561,
        work_item_id="bd-ib-2s3kkq",
        merge_sha="52aa6ee7",
        assertions=(*_ASSERTIONS_2561, _FABRICATED_ASSERTION),
        dispatch=MergingDispatch(fabro_run_id=None, dispatch_id=_DISPATCH_ID_2561),
        tmp_path=tmp_path,
    )

    assert leg.record is not None
    assert leg.record.verdict == VERDICT_VERIFIED
    assert leg.record.url == _VERIFIED_RECORD_URL_2561
    assert [check.text for check in leg.checks] == list(_ASSERTIONS_2561)
    assert [check.passed for check in leg.checks] == [True, True, True, True]
    assert leg.unevidenced == (_FABRICATED_ASSERTION,)


def test_every_assertion_of_pull_request_2538_grades_from_its_verified_record(
    tmp_path: Path,
) -> None:
    """The repair, on the payload whose fourth assertion the splitter used to lose.

    The sibling attribution module recorded that loss as an assertion of its own
    while the segmentation defect was still open; this is the same payload read
    after the repair, with the fabricated control alongside.
    """
    leg = _leg(
        pr_number=_PR_2538,
        work_item_id="bd-ib-mxqrr4",
        merge_sha="52783f67",
        assertions=(*_ASSERTIONS_2538, _FABRICATED_ASSERTION),
        dispatch=MergingDispatch(fabro_run_id=_FABRO_RUN_ID_2538, dispatch_id=_DISPATCH_ID_2538),
        tmp_path=tmp_path,
    )

    assert leg.record is not None
    assert leg.record.verdict == VERDICT_VERIFIED
    assert leg.record.url == _VERIFIED_RECORD_URL_2538
    assert [check.text for check in leg.checks] == list(_ASSERTIONS_2538)
    assert [check.passed for check in leg.checks] == [True, True, True, True]
    assert leg.unevidenced == (_FABRICATED_ASSERTION,)


def test_the_not_reproduced_record_of_pull_request_2561_still_reports_its_failure() -> None:
    """A `Reproduced: NO.` line survives the repair, on a real fenced-proof record.

    This record is the live counterpart of the synthetic `no` and absent arms, and
    it is the control that discriminates the repair from a reader that stopped
    reading the load-bearing line: its first assertion says NO while the other
    three say yes, and it carries fenced hash lines of its own, so a splitter that
    lost the line would answer `None` for all four — which is exactly what the
    pre-repair reader measured here.
    """
    records = proof_records(comments=json.loads(_payload(pr_number=_PR_2561))["comments"])
    record = latest_proof_record(
        records=records, verdict=VERDICT_NOT_REPRODUCED, run_ids=(_DISPATCH_ID_2561,)
    )

    assert record is not None
    assert record.url == _NOT_REPRODUCED_RECORD_URL_2561
    assert [record.reproduced(assertion=one) for one in _ASSERTIONS_2561] == [
        False,
        True,
        True,
        True,
    ]
    assert record.reproduced(assertion=_FABRICATED_ASSERTION) is None


def test_both_committed_payloads_carry_the_hazard_and_the_forge_shape() -> None:
    """The fixtures are the forge shape, and each one really does exercise the fence.

    Asserted because every claim above rides on both properties. A payload reshaped
    into something the production argv never returns would exercise a reader nobody
    runs; and a record whose body carried no heading-like line beyond its own four
    assertion headings would have graded identically before the repair, so "all four
    passed" would be evidence of nothing. The census counts heading-like lines in
    each body against the FOUR assertion headings the record is required to carry,
    which is the surplus the pre-repair splitter turned into spurious sections.
    """
    for pr_number in (_PR_2561, _PR_2538):
        payload = json.loads(_payload(pr_number=pr_number))

        assert sorted(payload) == ["comments"]
        assert all(sorted(one) == ["body", "url"] for one in payload["comments"])
        for comment in payload["comments"]:
            headings = [one for one in comment["body"].splitlines() if _HEADING.match(one)]
            assert len(headings) > len(_ASSERTIONS_2561)


def test_the_production_argv_is_what_each_leg_issued(tmp_path: Path) -> None:
    """Read off the seam rather than restated, so it is the argv the pass ran."""
    runner = _CommentsRunner(stdout=_payload(pr_number=_PR_2561))

    _ = read_proof_leg(
        repo=tmp_path,
        criteria=_criteria(assertions=_ASSERTIONS_2561),
        outcome=DispatchOutcome(
            work_item_id="bd-ib-2s3kkq",
            status="green",
            stage="done",
            pr_number=_PR_2561,
            merge_sha="52aa6ee7",
            detail="merged",
        ),
        runner=runner,
        dispatch=MergingDispatch(fabro_run_id=None, dispatch_id=_DISPATCH_ID_2561),
    )

    assert runner.argvs == [["gh", "pr", "view", str(_PR_2561), "--json", "comments"]]
