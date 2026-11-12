"""A recapture-exhausted recovery hold names its terminal preservation ref."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_recovery_routing as routing
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoverySeed
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM = "bd-ib-p6ammc"
_RUN = "01M73ZK6Z090"
_REF = f"refs/heads/needs-human/{_RUN}"
_COMMIT = "b" * 40


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="feature",
        status="ready",
        title="recapture hold",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def test_a_terminal_needs_human_ref_is_named_when_no_pull_request_is_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The terminal ref replaces the absent pull request in the explicit route."""
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    journal.path.write_text(
        "\n".join(
            json.dumps(row)
            for row in (
                {"stage": "dispatch-id", "work_item_id": _ITEM, "dispatch_id": "d"},
                {"stage": "fabro-run", "work_item_id": _ITEM, "run_id": _RUN},
                {
                    "stage": "outcome",
                    "outcome": {
                        "work_item_id": _ITEM,
                        "status": "blocked",
                        "stage": "non_converged",
                        "detail": "LIVESPEC_RECAPTURE_EXHAUSTED",
                    },
                },
            )
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        routing,
        "gather_resume",
        lambda **_kwargs: SimpleNamespace(
            observation=SimpleNamespace(pull_request=None, pull_request_head=None),
            earlier_run_ids=(_RUN,),
            publications=(),
        ),
    )
    monkeypatch.setattr(
        routing,
        "verified_preserved_seed",
        lambda **_kwargs: RecoverySeed(
            source_run_id=_RUN,
            remote="origin",
            commit_sha=_COMMIT,
            preservation_ref=_REF,
            preservation_tip_sha=_COMMIT,
        ),
    )

    routed = routing.route_recovery(
        args=argparse.Namespace(), repo=tmp_path, candidates=[_item()], journal=journal
    )

    route = routed.route_for(work_item_id=_ITEM)
    assert route is not None
    assert route.hold is not None
    assert route.hold.refusals == (
        f"recapture-exhausted: implementation preserved on {_REF} at {_COMMIT} ; "
        f"resume --item {_ITEM} at proof_capture with a proof rider",
    )
