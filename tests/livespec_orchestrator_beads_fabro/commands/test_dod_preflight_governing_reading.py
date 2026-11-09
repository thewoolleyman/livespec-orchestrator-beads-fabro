"""The preflight's governing-heading reading spends no model on a current recorded verdict.

`dev-tooling/dod-preflight.sh` took the governing-heading judgement on every run,
while the pre-dispatch gate reads `reusable_governing_heading_verdict` first
(`bd-ib-ot4av7`). The reading is a seam taking the comment texts the script already
reads and a command runner, so a recording runner counts the judge candidates it
starts without a live tenant, a registered build or a model-host CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_governing_reuse import (
    governing_heading_subject_digest,
    reusable_governing_heading_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_ADMITTED,
    DodJudgement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_DISPATCH,
    GoverningHeadingReceipt,
    verdict_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dod_preflight_governing_reading import (
    preflight_governing_heading_reading,
)
from livespec_orchestrator_beads_fabro.commands._spec_tier_attestation import attestation_comment
from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import clauses_named
from livespec_orchestrator_beads_fabro.types import WorkItem

_GOVERNING = "## Scenario 240 — A recorded verdict binds every host"
_CITED = "## Scenario 1 — Something the line cites instead"
_QUOTE = "The preflight reads the recorded verdict."
_TEXT = f"# Scenarios\n\n{_GOVERNING}\n\n{_QUOTE}\n\n{_CITED}\n\nOther body.\n"
_REPLY = (
    '{"kind": "stated", "stated_by": ["' + _GOVERNING + '"],'
    ' "generalization_target": null, "rationale": "The scenario states it.",'
    ' "evidence": [{"heading": "' + _GOVERNING + '", "quote": "' + _QUOTE + '"}]}'
)


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass
class _Runner:
    """A CommandRunner double that counts the judge candidates it is asked to start."""

    calls: int = 0
    argvs: list[list[str]] = field(default_factory=list)

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
        _ = (cwd, timeout_seconds, env, stdin, start_new_session)
        self.argvs.append(argv)
        self.calls += 1
        return CommandResult(exit_code=0, stdout=_REPLY, stderr="")


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-ot4av7",
        type="bug",
        status="ready",
        title="Read the recorded verdict",
        description=(f"## Definition of Done\n\n- {_QUOTE}\n\nReferences: {_CITED}\n"),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-09T00:00:00Z",
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
    _ = (spec / "scenarios.md").write_text(_TEXT, encoding="utf-8")
    _ = (repo / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "acp_nodes": {
        "dod_gate": {"agent": "codex-acp", "model": "gpt-5.6-terra", "effort": "high"}
      }
    }
  }
}
""",
        encoding="utf-8",
    )
    return repo


def _recorded(*, item: WorkItem, repo: Path) -> str:
    """The comment a pre-dispatch taking leaves: the verdict beside its subject digest."""
    fresh = preflight_governing_heading_reading(
        item=item, repo=repo, comments=(), runner=_Runner()
    ).verdict
    assert fresh is not None
    return verdict_comment(
        item_id=item.id,
        stage=STAGE_PRE_DISPATCH,
        digest="subject",
        rubric_digest="rubric",
        judgement=DodJudgement(outcome=JUDGEMENT_ADMITTED),
        governing=GoverningHeadingReceipt(
            verdict=fresh,
            subject_digest=governing_heading_subject_digest(item=item, comments=()),
        ),
    )


def test_a_fresh_taking_starts_one_judge_candidate_and_reports_the_verdict(
    tmp_path: Path,
) -> None:
    runner = _Runner()

    reading = preflight_governing_heading_reading(
        item=_item(), repo=_repo(tmp_path=tmp_path), comments=(), runner=runner
    )

    assert runner.calls == 1
    assert reading.report == (
        "governing-heading-kind: stated",
        f"governing-heading: {_GOVERNING}",
    )
    assert len(reading.findings) == 1
    assert reading.holds is True


def test_a_current_recorded_verdict_starts_no_judge_candidate_and_reads_as_a_fresh_taking(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    fresh = preflight_governing_heading_reading(
        item=_item(), repo=repo, comments=(), runner=_Runner()
    )
    runner = _Runner()

    reused = preflight_governing_heading_reading(
        item=_item(), repo=repo, comments=(_recorded(item=_item(), repo=repo),), runner=runner
    )

    assert runner.calls == 0
    assert reused.report == fresh.report
    assert reused.findings == fresh.findings
    assert reused.holds == fresh.holds


def test_a_candidate_edit_that_changes_the_governing_subject_starts_one_judge_candidate(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    recorded = _recorded(item=_item(), repo=repo)
    edited = replace(
        _item(), description=f"{_item().description}\n- It also does a second thing.\n"
    )
    runner = _Runner()

    _ = preflight_governing_heading_reading(
        item=edited, repo=repo, comments=(recorded,), runner=runner
    )

    assert runner.calls == 1


def test_a_standing_release_spec_tier_attestation_yields_the_verdict_the_gate_yields(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    clause = clauses_named(spec_tree={"scenarios.md": _TEXT}, headings=[_GOVERNING])[0]
    attestation = attestation_comment(
        item=_item(), actor="human:chad", clause=clause, spec_version="3"
    )
    runner = _Runner()

    reading = preflight_governing_heading_reading(
        item=_item(), repo=repo, comments=(attestation,), runner=runner
    )

    assert runner.calls == 0
    assert reading.verdict is not None
    assert reading.verdict == reusable_governing_heading_verdict(
        item=_item(), repo=repo, comments=(attestation,)
    )


def test_a_taking_that_yields_no_verdict_is_reported_unobserved_with_no_finding(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "no-such-repository"

    reading = preflight_governing_heading_reading(
        item=_item(), repo=missing, comments=(), runner=_Runner()
    )

    assert reading.verdict is None
    assert reading.report == ("governing-heading-kind: unobserved",)
    assert reading.findings == ()
    assert reading.holds is False
