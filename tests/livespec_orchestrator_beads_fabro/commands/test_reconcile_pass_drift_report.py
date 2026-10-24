"""The reconcile pass REPORTS its drift lane, on both of its output surfaces.

The lane's whole state used to live in the records it appended to the
detection-coverage anchor, and the pass discarded its return value. That was
survivable only while every tick appended one: an operator could read the
anchor and see the lane's condition. Once the inert arm records ONCE instead of
once per tick — which is the defect this work-item repairs — a pass that still
said nothing would make the state invisible between the first tick and whenever
somebody next read the anchor, and invisible is the one thing a withheld
frontier must not be.

A LANE THAT ADVANCED AND A LANE THAT JUDGED NOTHING MUST NOT RENDER ALIKE,
which is what the third case here is for. Without it a renderer that printed a
constant line would satisfy both of the first two cases exactly as well as a
correct one, while telling an operator nothing at all.

AND THE LINE IS NOT SWALLOWED BY THE RUNS LANE'S OWN REFUSAL. A pass that
surveyed no factory returns early, before the orphan lines, because
"nothing to reconcile" and "nothing was looked at" are the same empty output
with opposite meanings. The two lanes answer unrelated questions — the pass
command says so itself — so the drift report is written BEFORE that return:
a repository whose factories table went unresolvable would otherwise stop
reporting its drift lane with nothing naming it as the casualty.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_reconcile_runs_command as command
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_drift_lane import (
    DriftLaneOutcome,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

if TYPE_CHECKING:
    from collections.abc import Iterator

_ANCHOR = "bd-ib-anchor"
_NO_BASELINE = "no-recorded-drift-frontier"


@pytest.fixture(autouse=True)
def _hermetic_fake_backend() -> Iterator[None]:
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="t", prefix="bd-ib", server_user="u", database="d", bd_path="bd", fake=True
    )


def _seed_anchor() -> None:
    append_work_item(
        path=_config(),
        item=WorkItem(
            id=_ANCHOR,
            type="task",
            status="backlog",
            title="anchor",
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


def _project(*, root: Path) -> None:
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
                    "dispatcher": {"detection_coverage_anchor": _ANCHOR},
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _args(*, root: Path, as_json: bool) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(root),
        factory=None,
        fabro_bin="fabro",
        dry_run=False,
        as_json=as_json,
        journal=str(root / "journal.jsonl"),
        calibration_spans=str(root / "spans.jsonl"),
        invoker="role:test",
    )


def test_the_json_projection_reports_the_lane_is_not_yet_baselined(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _project(root=tmp_path)
    _seed_anchor()

    _ = command.run_reconcile_runs_command(args=_args(root=tmp_path, as_json=True))

    # The REAL lane, end to end: the anchor carries no completed drift coverage
    # point, so the lane judged nothing and the pass says so.
    payload = json.loads(capsys.readouterr().out)
    assert payload["drift"]["advanced"] is False
    assert payload["drift"]["withheld_reason"] == _NO_BASELINE
    assert payload["drift"]["frontier"] is None


def test_the_human_output_leads_with_the_lane_it_could_not_advance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _project(root=tmp_path)
    _seed_anchor()

    exit_code = command.run_reconcile_runs_command(args=_args(root=tmp_path, as_json=False))

    # FIRST line, and the exit code still belongs to the runs lane alone: this
    # fixture declares no factories table, so that lane refuses and returns
    # early, and the drift report must precede the return rather than be lost
    # to it.
    lines = capsys.readouterr().out.splitlines()
    assert exit_code == 1
    assert lines[0] == f"DRIFT   advanced=false frontier=(none) reason={_NO_BASELINE}"


def test_a_lane_that_advanced_renders_its_frontier_and_no_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _project(root=tmp_path)
    _seed_anchor()
    advanced = DriftLaneOutcome(
        scope="deadbeef..HEAD",
        merges=("aaaaaaa1",),
        frontier="aaaaaaa1",
        filed=(),
        held=(),
        advanced=True,
        withheld_reason=None,
        records=None,
    )
    monkeypatch.setattr(command, "run_drift_lane", lambda **_kwargs: advanced)

    _ = command.run_reconcile_runs_command(args=_args(root=tmp_path, as_json=False))

    # The control for the two cases above. A renderer printing a constant line
    # would satisfy both of them; this is the reading that makes the line worth
    # printing at all, and the omitted reason follows the same idiom the held
    # claim line uses for its optional remedy.
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "DRIFT   advanced=true frontier=aaaaaaa1"
