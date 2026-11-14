"""Repository-preflight verdicts are durable, reusable package decisions."""

from __future__ import annotations

import importlib
import inspect
import os
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_ADMITTED,
    JUDGEMENT_HELD,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    dod_gate_prompt_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dod_preflight_judgement.py"
)


def test_a_passing_repository_preflight_records_its_taking() -> None:
    """The package seam owns the record a successful preflight leaves behind."""
    assert _MODULE_PATH.is_file()

    judgement = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dod_preflight_judgement"
    )

    assert "item" in inspect.signature(judgement.repository_preflight_reading).parameters


@dataclass
class _CommentStore:
    bodies: list[str] = field(default_factory=list)

    def comments(self) -> tuple[str, ...]:
        return tuple(self.bodies)

    def append(self, *, body: str) -> None:
        self.bodies.append(body)


@dataclass
class _Runner:
    reply: str
    calls: int = 0

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
        _ = os.read(stdin, 1_000_000)
        self.calls += 1
        return CommandResult(exit_code=0, stdout=self.reply, stderr="")


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-hofndb",
        type="bug",
        status="ready",
        title="Record repository preflight verdicts",
        description="## Definition of Done\n\n- Record the verdict.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-13T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "SPECIFICATION").mkdir(parents=True)
    (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro":{"dispatcher":{"acp_nodes":'
        '{"dod_gate":{"agent":"claude-acp","model":"claude-opus-5"}}}}}',
        encoding="utf-8",
    )
    return repo


def _payload(*, tmp_path: Path) -> Path:
    prompts = tmp_path / "payload" / ".fabro" / "workflows" / "implement-work-item" / "prompts"
    prompts.mkdir(parents=True)
    (prompts / "dod-gate.md").write_text(
        dod_gate_prompt_path().read_text(encoding="utf-8"), encoding="utf-8"
    )
    return prompts.parents[3]


def _governing(**_: object) -> GoverningHeadingVerdict:
    return GoverningHeadingVerdict(kind="stated", stated_by=())


def test_a_fresh_passing_or_refusing_taking_appends_one_repository_preflight_record(
    tmp_path: Path,
) -> None:
    judgement = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dod_preflight_judgement"
    )
    store = _CommentStore()
    runner = _Runner(reply='{"outcome":"failed","failure_reason":"repair it"}')

    decision = judgement.repository_preflight_reading(
        item=_item(),
        repo=_repo(tmp_path=tmp_path),
        store=store,
        runner=runner,
        payload_root=_payload(tmp_path=tmp_path),
        governing_heading=_governing,
    )

    assert decision.outcome == JUDGEMENT_HELD
    assert runner.calls == 1
    assert len(store.bodies) == 1
    assert "stage: repository-preflight" in store.bodies[0]
    assert "outcome: rests-at-needs-human" in store.bodies[0]
    assert "finding: repair it" in store.bodies[0]


def test_an_identical_preflight_reuses_its_record_without_a_runner_call(tmp_path: Path) -> None:
    judgement = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dod_preflight_judgement"
    )
    store = _CommentStore()
    runner = _Runner(reply='{"outcome":"passed"}')
    kwargs = {
        "item": _item(),
        "repo": _repo(tmp_path=tmp_path),
        "store": store,
        "runner": runner,
        "payload_root": _payload(tmp_path=tmp_path),
        "governing_heading": _governing,
    }

    first = judgement.repository_preflight_reading(**kwargs)
    second = judgement.repository_preflight_reading(**kwargs)

    assert first.outcome == JUDGEMENT_ADMITTED
    assert second.outcome == JUDGEMENT_ADMITTED
    assert second.reused is True
    assert runner.calls == 1
    assert len(store.bodies) == 1


def test_a_fresh_governing_verdict_is_recorded_for_the_next_repository_preflight(
    tmp_path: Path,
) -> None:
    judgement = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dod_preflight_judgement"
    )
    store = _CommentStore()
    runner = _Runner(reply='{"outcome":"passed"}')
    kwargs = {
        "item": _item(),
        "repo": _repo(tmp_path=tmp_path),
        "store": store,
        "runner": runner,
        "payload_root": _payload(tmp_path=tmp_path),
        "governing_heading": _governing,
    }

    _ = judgement.repository_preflight_reading(**kwargs)
    reused = judgement.repository_preflight_reading(**kwargs)

    assert "governing-heading-kind: stated" in store.bodies[0]
    assert reused.reused is True
