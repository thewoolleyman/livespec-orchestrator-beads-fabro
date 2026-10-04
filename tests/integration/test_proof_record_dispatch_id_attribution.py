"""The real PR #2538 record payload, read by the real proof-evidence leg.

This module is the measured half of work-item `bd-ib-u2xeal`. The synthetic
coverage lives in
`tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_proof_attribution.py`;
what it cannot do is prove the repair works on the bytes a REAL factory published,
and the defect it repairs was invisible to every synthetic fixture precisely
because each one stamped its record with whatever identifier the fixture also fed
the pass.

THE PAYLOAD IS COMMITTED, NOT FETCHED. `fixtures/proof_records/
pull-request-2538-comments.json` is the verbatim
`gh api repos/thewoolleyman/livespec-orchestrator-beads-fabro/issues/2538/comments`
answer, reshaped only into the `{"comments": [...]}` envelope `gh pr view --json
comments` returns — which is the argv the pass actually runs. No field was edited.
A test that fetched it live would depend on the forge and would stop being a test
of this repository.

THE CONTROL IS THE MEASURED FAILURE ITSELF. The second case hands the same bytes
to the same reader with the dispatch id withheld — which is exactly what the
pre-repair build could see — and asserts the verified record is NOT attributed and
every assertion is unevidenced. Without it, "the record graded" is equally
consistent with a reader that would have graded it before.

ONE SEPARATE DEFECT IS MEASURED HERE AND DELIBERATELY NOT REPAIRED. The fourth
assertion of PR #2538 reads UNEVIDENCED even once its record is correctly
attributed, because `_dispatcher_proof_record._sections` splits the body at any
line matching `^#{1,6}\\s` — including the `# just.log:` comment lines inside that
assertion's fenced code block — so its `Reproduced:` line lands in a later
section than its heading. That is a fault in section SEGMENTATION, not in
attribution, and it is recorded as an assertion here so the finding is durable
rather than rediscovered; repairing it belongs to its own work-item.
"""

from __future__ import annotations

import json
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
    PROOF_RECORD_EVIDENCE_LEG,
    ProofLeg,
    read_proof_leg,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import VERDICT_VERIFIED

_PAYLOAD = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "proof_records"
    / "pull-request-2538-comments.json"
)
_PR_NUMBER = 2538
# Both identifiers of the ONE dispatch that merged PR #2538, as recorded by the
# dispatch that published the payload: the Fabro run id the acceptance pass asked
# for, and the dispatch id every record is actually stamped with.
_FABRO_RUN_ID = "01M3WH8Z10278S5V4SV9WRYW20"
_DISPATCH_ID = "f195238b76b942698485a780611fe1ef"
_VERIFIED_RECORD_URL = (
    "https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/pull/2538"
    "#issuecomment-5940752598"
)
# `bd-ib-mxqrr4`'s four Definition-of-Done assertions, as the record publishes
# them. The record clause requires each one to appear verbatim, so the published
# headings are the faithful transcription available to a sandbox with no ledger
# connection; the load-bearing claims below are about ATTRIBUTION, which no
# transcription of the assertions can affect.
_ASSERTIONS = (
    "dev-tooling/just-check.sh derives its executed target list from the justfile"
    " check recipe's targets array.",
    "A test or check fails when a slug listed in the justfile check recipe's targets"
    " array is absent from the set the runner executes.",
    "Running just check executes check-spec-governance-default-block and the other"
    " nine previously unrun slugs.",
    "The aggregate's final passed-count line reports the number of targets actually" " executed.",
)
# The one whose section the fenced-code-block segmentation defect splits.
_FENCE_SPLIT_ASSERTION = _ASSERTIONS[3]


@dataclass(kw_only=True)
class _CommentsRunner:
    """The pass's command seam, answering the comments read with the real payload."""

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


def _criteria() -> EffectiveCriteria:
    return EffectiveCriteria(
        text="\n".join(f"- {one}" for one in _ASSERTIONS),
        source=DESCRIPTION_DEFINITION_OF_DONE_SOURCE,
        assertions=_ASSERTIONS,
        proof_modes=(PROOF_MODE_FACTORY_CAPTURED,) * len(_ASSERTIONS),
    )


def _outcome() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-mxqrr4",
        status="green",
        stage="done",
        pr_number=_PR_NUMBER,
        merge_sha="52783f67",
        detail="merged",
        fabro_run_id=_FABRO_RUN_ID,
    )


def _leg(*, dispatch: MergingDispatch, tmp_path: Path) -> ProofLeg:
    runner = _CommentsRunner(stdout=_PAYLOAD.read_text(encoding="utf-8"))
    return read_proof_leg(
        repo=tmp_path, criteria=_criteria(), outcome=_outcome(), runner=runner, dispatch=dispatch
    )


def test_the_real_payload_is_attributed_by_the_dispatch_id_it_is_stamped_with(
    tmp_path: Path,
) -> None:
    """The repair, on the bytes the factory published."""
    leg = _leg(
        dispatch=MergingDispatch(fabro_run_id=_FABRO_RUN_ID, dispatch_id=_DISPATCH_ID),
        tmp_path=tmp_path,
    )

    # Both records on the pull request are stamped with the DISPATCH id, which is
    # the fact the whole repair turns on; neither names the Fabro run id.
    assert [one.run_id for one in leg.records] == [_DISPATCH_ID, _DISPATCH_ID]
    assert leg.record is not None
    assert leg.record.verdict == VERDICT_VERIFIED
    assert leg.record.url == _VERIFIED_RECORD_URL
    assert leg.record.timestamp == "2026-10-01T21:15:01Z"
    # Three of the four assertions grade REPRODUCED off that record. The fourth is
    # the separate section-segmentation defect this module's docstring records: its
    # `Reproduced:` line sits past a `# just.log:` line inside a fenced block, so
    # the splitter has already opened a new section by the time it is reached.
    assert [check.passed for check in leg.checks] == [True, True, True]
    assert leg.unevidenced == (_FENCE_SPLIT_ASSERTION,)


def test_the_same_payload_is_unobserved_when_only_the_fabro_run_id_is_accepted(
    tmp_path: Path,
) -> None:
    """The control: the measured pre-repair failure, reproduced on the same bytes.

    This is what the dispatch of `bd-ib-mxqrr4` recorded on 2026-10-01 — journal
    `acceptance_verdict NEEDS_ATTENTION` and `proof-pointer-skipped` with reason
    "no verified Proof of Done record for the merging run" — and it is why "the
    record graded" in the case above is evidence of the repair rather than of a
    reader that would always have graded it.
    """
    leg = _leg(
        dispatch=MergingDispatch(fabro_run_id=_FABRO_RUN_ID, dispatch_id=None), tmp_path=tmp_path
    )

    # The records WERE read — the payload is identical — and none is attributable.
    assert len(leg.records) == 2
    assert leg.record is None
    assert leg.checks == ()
    assert leg.unevidenced == _ASSERTIONS
    assert leg.absent_evidence == tuple(
        f"{PROOF_RECORD_EVIDENCE_LEG} for {one!r}" for one in _ASSERTIONS
    )


def test_the_committed_payload_is_the_forge_shape_the_pass_reads(tmp_path: Path) -> None:
    """The fixture is what `gh pr view --json comments` returns, and nothing else.

    Asserted because every claim above rides on the payload being the real forge
    shape: a fixture reshaped into something the production argv never produces
    would exercise a reader nobody runs. The argv is read off the seam rather than
    restated, so it is the one the pass actually issued.
    """
    runner = _CommentsRunner(stdout=_PAYLOAD.read_text(encoding="utf-8"))

    _ = read_proof_leg(
        repo=tmp_path,
        criteria=_criteria(),
        outcome=_outcome(),
        runner=runner,
        dispatch=MergingDispatch(fabro_run_id=_FABRO_RUN_ID, dispatch_id=_DISPATCH_ID),
    )

    assert runner.argvs == [["gh", "pr", "view", str(_PR_NUMBER), "--json", "comments"]]
    payload = json.loads(_PAYLOAD.read_text(encoding="utf-8"))
    assert sorted(payload) == ["comments"]
    assert all(sorted(one) == ["body", "url"] for one in payload["comments"])
