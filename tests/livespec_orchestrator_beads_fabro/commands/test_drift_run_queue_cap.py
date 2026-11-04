"""At the queue cap a finding is HELD on the anchor and no proposal is filed.

Assertion 3 of `bd-ib-yvjxo4`: "When the count of open drift-origin proposals
is at `dispatcher.drift_proposal_queue_cap`, further findings are held on the
detection-coverage anchor with their identities and listed by needs-attention,
and no proposal is filed for them."

Five things are pinned, and the first two are each other's control.

BELOW the cap a finding files, AT the cap it holds. Either case alone is
satisfied by a build that always does that one thing — a pass that never held
looks perfect until the fifth open proposal, and a pass that always held files
nothing ever while every surface still reports findings.

HOLDING IS NOT FILING, so the held case asserts the open queue is UNCHANGED as
well as asserting the hold. A build that recorded the hold and ALSO wrote the
document would satisfy every hold assertion while defeating the cap entirely,
which is the whole point of the cap: the independent review of this plan's
scoping required a bounded queue because every proposal costs a human review
(research note 005, finding 14).

A RETRIED pass re-records nothing. The root reconcile timer fires every ten
minutes, so a hold that re-appended its record each tick would bury the anchor
in copies of one finding — and the needs-attention lane would list it once per
copy.

AND A HELD FINDING FILES ONCE A SLOT FREES, which is the second half of
assertion 4 — "a merge whose pass fails or that carries a held finding stops
the frontier until every finding of it is filed" — and the half a hold the pass
can never promote makes unreachable. A build whose already-held rung answers
before the cap is consulted is byte-identical to a correct one on every case
above: it holds at the cap, re-records nothing on retry, and lists the finding.
What it cannot do is ever file that finding again, so the first time the queue
fills, the coverage frontier wedges permanently and every later tick re-judges a
growing backlog at one model call per merge while filing nothing. The slot is
freed the way `revise` adjudication frees one — the open proposal moves into
`history/vNNN/proposed_changes/` — which also keeps that identity in the FILED
set, so the pass files the held finding and not the adjudicated one.

And the LISTING is read off the real composed attention lane rather than off
the pass's return value, because the contract's requirement is that
needs-attention lists the held finding with a handoff naming `revise`: a hold
the operator never sees is a finding the pass has silently dropped.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._drift_run import (
    DriftRunOutcome,
    DriftRunSeams,
    run_drift_pass,
)
from livespec_orchestrator_beads_fabro.commands._drift_run_frontier import contiguous_frontier
from livespec_orchestrator_beads_fabro.commands._needs_attention_detection_staleness import (
    DetectionStalenessSeams,
    detection_staleness_items,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_ANCHOR = "bd-ib-anchor"
_TARGET = "## A governing heading"
_HELD_FACT_ID = "hygiene:held-drift-findings:repo"


@dataclass(kw_only=True)
class _GitRunner:
    """A `CommandRunner` answering the git reads over one merge."""

    merges: tuple[str, ...] = ("aaaaaaa1",)
    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.argvs.append(argv)
        if argv[1] == "symbolic-ref":
            return CommandResult(exit_code=0, stdout="origin/master\n", stderr="")
        if argv[1] == "rev-list":
            return CommandResult(exit_code=0, stdout="\n".join(self.merges) + "\n", stderr="")
        return CommandResult(exit_code=0, stdout=f"a subject\n+ hunk {argv[-1]}\n", stderr="")


@pytest.fixture(autouse=True)
def _hermetic_fake_backend() -> object:
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="t",
        prefix="bd-ib",
        server_user="u",
        database="d",
        bd_path="bd",
        fake=True,
    )


def _seed_anchor() -> None:
    append_work_item(
        path=_config(),
        item=WorkItem(
            id=_ANCHOR,
            type="task",
            status="backlog",
            title="detection coverage anchor",
            description="d",
            origin="freeform",
            gap_id=None,
            rank="a0",
            assignee=None,
            depends_on=(),
            captured_at="2026-08-01T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            blocked_reason=None,
            factory_safety=None,
            admission_policy=None,
            acceptance_policy=None,
            spec_commitment_hint=None,
        ),
    )


def _unstated(prompt: str) -> str:
    _ = prompt
    return (
        f'{{"kind": "unstated", "stated_by": [], '
        f'"generalization_target": "{_TARGET}", "rationale": "r"}}'
    )


def _project(*, root: Path, cap: int, open_proposals: int) -> Path:
    spec_root = root / "SPECIFICATION"
    (spec_root / "proposed_changes").mkdir(parents=True)
    (spec_root / "history" / "v001" / "proposed_changes").mkdir(parents=True)
    _ = (spec_root / "contracts.md").write_text(f"{_TARGET}\n\ntext\n", encoding="utf-8")
    for index in range(open_proposals):
        _ = (spec_root / "proposed_changes" / f"drift-existing{index}.md").write_text(
            f"---\ntopic: drift-existing{index}\n"
            f"drift_origin: dispatcher-drift-run\n"
            f"finding_identity: drift-existing{index}\n---\n\nbody\n",
            encoding="utf-8",
        )
    _ = (root / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "t",
                        "prefix": "bd-ib",
                        "server_user": "u",
                        "database": "d",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {
                        "detection_coverage_anchor": _ANCHOR,
                        "drift_proposal_queue_cap": cap,
                        "drift_capture_merge_threshold": 99,
                    },
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return spec_root


def _run(*, root: Path, judge: Callable[[str], str] = _unstated) -> DriftRunOutcome:
    return run_drift_pass(
        project_root=root,
        frontier="deadbeef",
        seams=DriftRunSeams(
            runner=_GitRunner(),
            judge=judge,
            now=lambda: "2026-10-22T00:00:00Z",
        ),
    )


def _open_queue(*, spec_root: Path) -> list[Path]:
    return sorted((spec_root / "proposed_changes").glob("*.md"))


def _anchor_bodies() -> list[str]:
    return [
        str(comment["text"])
        for comment in make_beads_client(config=_config()).list_comments(issue_id=_ANCHOR)
    ]


def test_below_the_cap_a_finding_is_filed_and_not_held(tmp_path: Path) -> None:
    assert (_COMMANDS / "_drift_run_held.py").is_file()
    spec_root = _project(root=tmp_path, cap=5, open_proposals=4)
    _seed_anchor()

    outcome = _run(root=tmp_path)

    assert len(_open_queue(spec_root=spec_root)) == 5
    assert len(outcome.filed) == 1
    assert outcome.held == ()
    assert _anchor_bodies() == []


def test_at_the_cap_the_finding_is_held_with_its_identity_and_nothing_is_filed(
    tmp_path: Path,
) -> None:
    assert (_COMMANDS / "_drift_run_held.py").is_file()
    spec_root = _project(root=tmp_path, cap=5, open_proposals=5)
    _seed_anchor()

    outcome = _run(root=tmp_path)

    assert len(_open_queue(spec_root=spec_root)) == 5
    assert outcome.filed == ()
    assert len(outcome.held) == 1
    assert any(outcome.held[0] in body for body in _anchor_bodies())


def test_a_retried_pass_records_the_hold_once(tmp_path: Path) -> None:
    assert (_COMMANDS / "_drift_run_held.py").is_file()
    _ = _project(root=tmp_path, cap=1, open_proposals=1)
    _seed_anchor()

    first = _run(root=tmp_path)
    second = _run(root=tmp_path)

    assert first.held == second.held
    assert len(_anchor_bodies()) == 1


def test_a_held_finding_is_filed_once_a_queue_slot_frees_and_the_frontier_advances(
    tmp_path: Path,
) -> None:
    assert (_COMMANDS / "_drift_run_held.py").is_file()
    spec_root = _project(root=tmp_path, cap=1, open_proposals=1)
    _seed_anchor()

    held = _run(root=tmp_path)
    # The hold is observed FIRST, so the filing below is attributable to the
    # freed slot rather than to a build that never held anything.
    assert held.filed == ()
    assert len(held.held) == 1
    assert contiguous_frontier(judged=held.judged) is None

    adjudicated = spec_root / "proposed_changes" / "drift-existing0.md"
    _ = adjudicated.rename(spec_root / "history" / "v001" / "proposed_changes" / adjudicated.name)
    assert _open_queue(spec_root=spec_root) == []

    freed = _run(root=tmp_path)

    assert freed.filed == held.held
    assert freed.held == ()
    # The merge's every finding is now filed, so the frontier advances past it.
    assert contiguous_frontier(judged=freed.judged) == "aaaaaaa1"
    # Exactly the held finding's proposal, and not a second copy of the
    # adjudicated one: an archived proposal has been filed and is never re-filed.
    assert [path.name for path in _open_queue(spec_root=spec_root)] == [f"{held.held[0]}.md"]
    # And the hold record was not re-appended while it was being promoted.
    assert len(_anchor_bodies()) == 1


def test_needs_attention_lists_a_held_finding_with_a_revise_handoff(tmp_path: Path) -> None:
    assert (_COMMANDS / "_needs_attention_held_drift_findings.py").is_file()
    _ = _project(root=tmp_path, cap=1, open_proposals=1)
    _seed_anchor()
    outcome = _run(root=tmp_path)

    composed = {
        item.id: item.summary + "\n" + item.handoff.command
        for item in detection_staleness_items(
            project_root=tmp_path,
            repo="repo",
            config=_config(),
            seams=DetectionStalenessSeams(runner=_GitRunner()),
        )
    }

    assert _HELD_FACT_ID in composed
    assert outcome.held[0] in composed[_HELD_FACT_ID]
    assert "revise" in composed[_HELD_FACT_ID]
