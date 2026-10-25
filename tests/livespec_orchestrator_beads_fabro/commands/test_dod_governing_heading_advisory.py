"""A governing-heading omission holds only when the reference line governs nothing.

Ratified in `contracts.md` (the `dod_gate` reference-coverage rule) and
`scenarios.md` (Scenarios 141, 174 and 239): a reference-coverage finding REFUSES only when the
reference line names no heading the spec-stated judgement returns as governing
any of the item's assertions. When one named heading governs, every omitted one
is ADVISORY — reported with the same remedy and recorded by the host taking, but
the item is admitted. Work-item `bd-ib-52zhw`.

The spec-stated judgement names different governing headings for one unchanged
subject, which is why a hard refusal on PARTIAL omission made admission
non-convergent: measured on 2026-10-24, seven items were held for "add heading X"
after an earlier taking had passed or named a different heading.

EACH CASE PASSES THE RUBRIC JUDGE, so the outcome can only come from the
governing-heading fold-in. The two verdicts differ in exactly one respect —
whether the heading the item cites is among the governing ones — so the pair is
its own control: a fold-in that held or admitted unconditionally would fail one
of them.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_ADMITTED,
    JUDGEMENT_HELD,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    DodJudgementDecision,
    judge_definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_ADMISSION,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    dod_gate_prompt_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
    GoverningHeadingReader,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_CITED = "## Scenario 141 — The referenced scenario governs the proof"
_OMITTED = "## Scenario 206 — The spec-change tier is decided by the spec-stated judgement"
_PASS_REPLY = '{"outcome": "passed"}'
_REMEDY = "add that heading to the reference line"


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-52zhw",
        type="feature",
        status="ready",
        title="A governing-heading omission is advisory when a named heading governs",
        description=(
            "## Definition of Done\n\n- The omission is advisory.\n\n" f"References: {_CITED}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="b0f",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-24T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_CITED}\n\nIt states one half.\n\n{_OMITTED}\n\nThe other half.\n",
        encoding="utf-8",
    )
    _ = (repo / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "acp_nodes": {
        "dod_gate": {"agent": "claude-acp", "model": "claude-opus-5"}
      }
    }
  }
}
""",
        encoding="utf-8",
    )
    return repo


def _payload(*, tmp_path: Path) -> Path:
    prompts = tmp_path / "payload" / ".fabro" / "workflows" / "implement-work-item" / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    _ = (prompts / "dod-gate.md").write_text(
        dod_gate_prompt_path().read_text(encoding="utf-8"), encoding="utf-8"
    )
    return tmp_path / "payload"


class _Runner:
    """A `CommandRunner` double answering the rubric judge with a clean pass."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
        start_new_session: bool = False,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env, stdin, start_new_session)
        return CommandResult(exit_code=0, stdout=_PASS_REPLY, stderr="")


def _reader(*, verdict: GoverningHeadingVerdict) -> GoverningHeadingReader:
    def read(*, item: WorkItem, repo: Path) -> GoverningHeadingVerdict | None:
        _ = (item, repo)
        return verdict

    return read


def _judge(
    *, tmp_path: Path, bodies: list[str], verdict: GoverningHeadingVerdict
) -> DodJudgementDecision:
    def append(*, body: str) -> None:
        bodies.append(body)

    return judge_definition_of_done(
        item=_item(),
        repo=_repo(tmp_path=tmp_path),
        stage=STAGE_PRE_ADMISSION,
        comments=(),
        append=append,
        runner=_Runner(),
        payload_root=_payload(tmp_path=tmp_path),
        governing_heading=_reader(verdict=verdict),
    )


def test_an_omission_beside_a_governing_citation_admits_and_records_the_advisory(
    tmp_path: Path,
) -> None:
    bodies: list[str] = []
    verdict = GoverningHeadingVerdict(kind="stated", stated_by=(_CITED, _OMITTED))

    decision = _judge(tmp_path=tmp_path, bodies=bodies, verdict=verdict)

    assert decision.outcome == JUDGEMENT_ADMITTED
    assert any(_OMITTED in finding and _REMEDY in finding for finding in decision.findings)
    assert len(bodies) == 1
    assert _OMITTED in bodies[0]


def test_a_reference_line_that_governs_nothing_is_still_held(tmp_path: Path) -> None:
    bodies: list[str] = []
    verdict = GoverningHeadingVerdict(kind="stated", stated_by=(_OMITTED,))

    decision = _judge(tmp_path=tmp_path, bodies=bodies, verdict=verdict)

    assert decision.outcome == JUDGEMENT_HELD
    assert any(_OMITTED in finding and _REMEDY in finding for finding in decision.findings)
