"""Recapture exhaustion is held rather than reimplemented or auto-resumed."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_recovery_routing as routing
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM = "bd-ib-p6ammc"
_HEAD = "a" * 40


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


def test_a_recapture_exhausted_open_pull_request_is_held_with_its_resume_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The passing resume is preserved, but only an explicit resume may take it."""
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    journal.path.write_text(
        "\n".join(
            json.dumps(row)
            for row in (
                {"stage": "dispatch-id", "work_item_id": _ITEM, "dispatch_id": "d"},
                {"stage": "fabro-run", "work_item_id": _ITEM, "run_id": "run"},
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
    monkeypatch.setattr(routing, "current_seed_ruling", lambda **_kwargs: None)
    monkeypatch.setattr(
        routing,
        "gather_resume",
        lambda **_kwargs: SimpleNamespace(
            observation=SimpleNamespace(pull_request=4841, pull_request_head=_HEAD),
            earlier_run_ids=("run",),
        ),
    )

    routed = routing.route_recovery(
        args=argparse.Namespace(), repo=tmp_path, candidates=[_item()], journal=journal
    )

    route = routed.route_for(work_item_id=_ITEM)
    assert route is not None
    assert route.route == "held"
    rows = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    held = rows[-1]
    assert held["stage"] == "recovery-held"
    assert held["refusals"] == [
        f"recapture-exhausted: implementation preserved on #4841 at {_HEAD} ; "
        f"resume --item {_ITEM} at proof_capture with a proof rider"
    ]


@pytest.mark.parametrize(
    ("pull_request", "head", "preserved", "expected"),
    [
        (4841, _HEAD, None, f"implementation preserved on #4841 at {_HEAD}"),
        (
            None,
            None,
            ("refs/heads/needs-human/run", "b" * 40),
            "implementation preserved on refs/heads/needs-human/run at " + "b" * 40,
        ),
        (None, None, None, "no preserved implementation observed"),
    ],
)
def test_the_hold_detail_names_the_preserved_implementation(
    pull_request: int | None,
    head: str | None,
    preserved: tuple[str, str] | None,
    expected: str,
) -> None:
    """The record names the pull request, terminal ref, or observed absence."""
    assert hasattr(routing, "recapture_exhausted_refusal")
    detail = routing.recapture_exhausted_refusal(
        work_item_id=_ITEM,
        pull_request=pull_request,
        head=head,
        preserved=preserved,
    )
    assert expected in detail
    assert detail.endswith(f"resume --item {_ITEM} at proof_capture with a proof rider")
