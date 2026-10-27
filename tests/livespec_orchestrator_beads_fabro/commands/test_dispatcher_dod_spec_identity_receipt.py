"""Host Definition-of-Done identities cross the dispatch boundary intact."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    judge_definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_ADMISSION,
    STAGE_PRE_DISPATCH,
    recorded_spec_identity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    dod_gate_prompt_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_spec_identity import (
    spec_identity_for_governing,
    subject_digest_for_governing,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import render_goal
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)
from livespec_orchestrator_beads_fabro.store import WorkItemComment
from livespec_orchestrator_beads_fabro.types import WorkItem

_GOVERNING = "## Scenario 240 — A recorded verdict binds identical digests"
_CITED = "## Dispatcher admission, WIP cap, and post-merge acceptance"
_PASS_REPLY = '{"outcome": "passed"}'
_STATED = GoverningHeadingVerdict(kind="stated", stated_by=(_GOVERNING,))


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-onrjh3",
        type="feature",
        status="ready",
        title="Clause identity",
        description=(
            "## Definition of Done\n\n- The host taking reuses this verdict.\n\n"
            f"References: {_CITED}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-27T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    specification = repo / "SPECIFICATION"
    specification.mkdir(parents=True)
    (specification / "scenarios.md").write_text(
        f"# Scenarios\n\n{_GOVERNING}\n\nOriginal governing body.\n\n{_CITED}\n\nOther.\n",
        encoding="utf-8",
    )
    (repo / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "acp_nodes": {"dod_gate": {"agent": "claude-acp", "model": "claude-opus-5"}}
    }
  }
}
""",
        encoding="utf-8",
    )
    return repo


def _payload(tmp_path: Path) -> Path:
    root = tmp_path / "payload"
    prompt = root / ".fabro/workflows/implement-work-item/prompts/dod-gate.md"
    prompt.parent.mkdir(parents=True)
    prompt.write_text(dod_gate_prompt_path().read_text(encoding="utf-8"), encoding="utf-8")
    return root


class _Runner:
    def run(self, **_: object) -> CommandResult:
        return CommandResult(exit_code=0, stdout=_PASS_REPLY, stderr="")


class _Ledger:
    def __init__(self) -> None:
        self.bodies: list[str] = []

    def append(self, *, body: str) -> None:
        self.bodies.append(body)


def _take(
    *,
    item: WorkItem,
    repo: Path,
    payload: Path,
    ledger: _Ledger,
    stage: str,
    governing: GoverningHeadingVerdict = _STATED,
):
    return judge_definition_of_done(
        item=item,
        repo=repo,
        stage=stage,
        comments=tuple(ledger.bodies),
        append=ledger.append,
        runner=_Runner(),
        payload_root=payload,
        governing_heading=lambda **_: governing,
    )


def test_partial_governing_verdict_uses_tree_identity(tmp_path: Path) -> None:
    """A clause list cannot identify a subject when it covers only some assertions."""
    ledger = _Ledger()
    decision = _take(
        item=_item(),
        repo=_repo(tmp_path),
        payload=_payload(tmp_path),
        ledger=ledger,
        stage=STAGE_PRE_DISPATCH,
        governing=GoverningHeadingVerdict(kind="partial", stated_by=(_GOVERNING,)),
    )

    assert decision.spec_identity is not None
    assert decision.spec_identity.form == "tree"


def test_host_taking_reuses_only_when_selected_clauses_are_unchanged(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    payload = _payload(tmp_path)
    ledger = _Ledger()
    first = _take(item=_item(), repo=repo, payload=payload, ledger=ledger, stage=STAGE_PRE_DISPATCH)
    (repo / "SPECIFICATION" / "unrelated.md").write_text(
        "# Other\n\n## Scenario 999 — Unrelated\n\nUnrelated body.\n", encoding="utf-8"
    )
    reused = _take(
        item=_item(), repo=repo, payload=payload, ledger=ledger, stage=STAGE_PRE_DISPATCH
    )
    (repo / "SPECIFICATION" / "scenarios.md").write_text(
        f"# Scenarios\n\n{_GOVERNING}\n\nChanged governing body.\n\n{_CITED}\n\nOther.\n",
        encoding="utf-8",
    )
    changed = _take(
        item=_item(), repo=repo, payload=payload, ledger=ledger, stage=STAGE_PRE_DISPATCH
    )

    assert first.reused is False
    assert reused.reused is True
    assert changed.reused is False
    assert len(ledger.bodies) == 2


def test_spec_change_admission_uses_tree_identity(tmp_path: Path) -> None:
    ledger = _Ledger()
    decision = _take(
        item=replace(_item(), spec_commitment_hint="ratified-spec-change"),
        repo=_repo(tmp_path),
        payload=_payload(tmp_path),
        ledger=ledger,
        stage=STAGE_PRE_ADMISSION,
    )

    assert decision.spec_identity is not None
    assert decision.spec_identity.form == "tree"


def test_receipt_supplies_the_identity_and_clause_provenance_to_the_goal(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    ledger = _Ledger()
    decision = _take(
        item=_item(),
        repo=repo,
        payload=_payload(tmp_path),
        ledger=ledger,
        stage=STAGE_PRE_DISPATCH,
    )
    recorded = recorded_spec_identity(comments=tuple(ledger.bodies))
    goal = render_goal(
        item=_item(),
        repo=repo,
        branch="feat/x",
        comments=tuple(
            WorkItemComment(text=body, author="dispatcher", created_at="now")
            for body in ledger.bodies
        ),
    )

    assert decision.spec_identity is not None
    assert recorded is not None
    assert recorded.form == decision.spec_identity.form == "clauses"
    assert recorded.value == decision.spec_identity.value
    assert recorded.provenance[0][:2] == ("scenarios.md", _GOVERNING.removeprefix("## "))
    assert "Definition-of-Done spec identity (from the pre-dispatch taking)" in goal
    assert "form: clauses" in goal


def test_clause_identity_rejects_ambiguous_headings(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "SPECIFICATION" / "duplicate.md").write_text(
        f"# Duplicate\n\n{_GOVERNING}\n\nDifferent body.\n", encoding="utf-8"
    )

    identity = spec_identity_for_governing(item=_item(), cwd=repo, governing=_STATED)

    assert identity.form == "tree"


def test_subject_digest_uses_the_recorded_governing_identity(tmp_path: Path) -> None:
    """The digest wrapper receives the resolved clause identity, not the tree."""
    digest = subject_digest_for_governing(
        item=_item(), cwd=_repo(tmp_path), comments=(), governing=_STATED
    )

    assert isinstance(digest, str)
    assert digest


def test_identity_reader_rejects_partial_clause_provenance() -> None:
    assert (
        recorded_spec_identity(
            comments=(
                "livespec-dod-judgement\n"
                "spec-identity-form: clauses\n"
                "spec-identity: clauses:abc\n"
                "spec-clause-path: scenarios.md\n",
            )
        )
        is None
    )
