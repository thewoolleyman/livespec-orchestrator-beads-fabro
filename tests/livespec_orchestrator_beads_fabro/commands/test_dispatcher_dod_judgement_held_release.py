"""The drain's standing-refusal reader keys a released item on the whole tree.

A repository-preflight verdict for a spec-change-tier item released from its
hold is recorded under the whole-tree identity. The judgement-free reader that
drive's candidate enumeration uses must derive that same identity, or the
standing refusal is invisible to it and drive advertises an item the
pre-dispatch taking would refuse.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import JUDGEMENT_HELD
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    held_judgement,
    judge_definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_DISPATCH,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    dod_gate_prompt_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
    governing_heading_verdict,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_HEADING = "## Scenario 240 — A recorded verdict binds identical digests"
_HELD_REPLY = '{"outcome": "failed", "failure_reason": "bd-ib-held: cite the scenario; add it."}'
_STATED = (
    '{"kind": "stated", "stated_by": ["'
    + _HEADING
    + '"], "generalization_target": null, "rationale": "The scenario states it.",'
    ' "evidence": [{"heading": "'
    + _HEADING
    + '", "quote": "A recorded verdict binds identical digests."}]}'
)
_HOLD = "livespec-spec-change-tier\n\ntier: spec-change"
_RELEASE = "livespec-spec-change-tier\n\ntier: none"


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass
class _Runner:
    calls: int = 0
    prompts: list[str] = field(default_factory=list)

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
        _ = (argv, cwd, timeout_seconds, env, start_new_session)
        assert stdin is not None
        self.prompts.append(os.read(stdin, 1_000_000).decode("utf-8"))
        self.calls += 1
        return CommandResult(exit_code=0, stdout=_HELD_REPLY, stderr="")


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-held",
        type="feature",
        status="ready",
        title="A released spec-change-tier item",
        description=(
            "## Definition of Done\n\n- A recorded verdict binds identical digests.\n\n"
            f"References: {_HEADING}\n"
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


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_HEADING}\n\nA recorded verdict binds identical digests.\n",
        encoding="utf-8",
    )
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"acp_nodes":'
        ' {"dod_gate": {"agent": "claude-acp", "model": "claude-opus-5"}}}}}\n',
        encoding="utf-8",
    )
    return repo


def _payload(*, tmp_path: Path) -> Path:
    root = tmp_path / "payload"
    prompts = root / ".fabro" / "workflows" / "implement-work-item" / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    _ = (prompts / "dod-gate.md").write_text(
        dod_gate_prompt_path().read_text(encoding="utf-8"), encoding="utf-8"
    )
    return root


def _stated(*, item: WorkItem, repo: Path) -> GoverningHeadingVerdict | None:
    return governing_heading_verdict(item=item, repo=repo, run_model=lambda _prompt: _STATED)


def test_a_released_items_standing_preflight_refusal_is_visible_to_the_held_reader(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    payload = _payload(tmp_path=tmp_path)
    bodies: list[str] = []
    runner = _Runner()

    taken = judge_definition_of_done(
        item=_item(),
        repo=repo,
        stage=STAGE_PRE_DISPATCH,
        comments=tuple(bodies),
        append=lambda *, body: bodies.append(body),
        runner=runner,
        payload_root=payload,
        governing_heading=_stated,
        release_of_held_spec_tier=True,
    )
    assert taken.outcome == JUDGEMENT_HELD

    released = (_HOLD, _RELEASE, *bodies)
    standing = held_judgement(item=_item(), repo=repo, comments=released, payload_root=payload)
    assert standing is not None
    assert standing.outcome == JUDGEMENT_HELD

    unreleased = (_HOLD, *bodies)
    assert (
        held_judgement(item=_item(), repo=repo, comments=unreleased, payload_root=payload) is None
    )
    assert runner.calls == 1


def test_a_record_naming_another_spec_identity_is_not_a_standing_refusal(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    payload = _payload(tmp_path=tmp_path)
    bodies: list[str] = []

    _ = judge_definition_of_done(
        item=_item(),
        repo=repo,
        stage=STAGE_PRE_DISPATCH,
        comments=tuple(bodies),
        append=lambda *, body: bodies.append(body),
        runner=_Runner(),
        payload_root=payload,
        governing_heading=_stated,
        release_of_held_spec_tier=True,
    )
    other = tuple(
        "spec-identity: tree:0000" if line.startswith("spec-identity: ") else line
        for line in bodies[0].splitlines()
    )
    assert "spec-identity: tree:0000" in other

    released = (_HOLD, _RELEASE, "\n".join(other))
    assert held_judgement(item=_item(), repo=repo, comments=released, payload_root=payload) is None
