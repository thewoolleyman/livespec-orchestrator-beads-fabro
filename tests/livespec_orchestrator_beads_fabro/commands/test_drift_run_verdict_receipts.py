"""The durable receipt reader fails soft for unusable historical comments."""

from __future__ import annotations

import importlib

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._detection_coverage import (
    DRIFT_CAPTURE_OPERATION,
    DetectionRun,
    record_detection_run,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.spec_stated import SpecStatedVerdict

_ANCHOR = "bd-ib-anchor"


@pytest.fixture(autouse=True)
def _hermetic_fake_backend() -> None:
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
    _ = record_detection_run(
        path=_config(),
        anchor=_ANCHOR,
        run=DetectionRun(
            operation=DRIFT_CAPTURE_OPERATION,
            scope="baseline",
            invoker="human:maintainer",
            outcome="succeeded",
            exit_code=0,
            coverage_point="deadbeef",
        ),
    )


def test_receipt_reader_ignores_missing_and_malformed_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipts = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._drift_run_verdicts"
    )
    verdict = SpecStatedVerdict(
        kind="partial",
        stated_by=("## Governing heading",),
        generalization_target="## Generalization target",
        rationale="r",
    )

    assert (
        receipts.recorded_drift_verdict(
            path=None, anchor=_ANCHOR, merge="merge", spec_revision="tree:one"
        )
        is None
    )
    receipts.record_drift_verdict(
        path=None, anchor=_ANCHOR, merge="merge", spec_revision="tree:one", verdict=verdict
    )
    _seed_anchor()
    client = make_beads_client(config=_config())
    for payload in ("not json", "[]", '{"merge": 1}'):
        client.add_comment(
            issue_id=_ANCHOR,
            body=receipts.DRIFT_VERDICT_MARKER_PREFIX + payload,
        )
    receipts.record_drift_verdict(
        path=_config(), anchor=_ANCHOR, merge="merge", spec_revision="tree:one", verdict=verdict
    )

    assert (
        receipts.recorded_drift_verdict(
            path=_config(), anchor=_ANCHOR, merge="merge", spec_revision="tree:one"
        )
        == verdict
    )
    assert (
        receipts.recorded_drift_verdict(
            path=_config(), anchor=_ANCHOR, merge="different-merge", spec_revision="tree:one"
        )
        is None
    )

    def _unreadable_comments(*, path: StoreConfig, work_item_id: str) -> list[object]:
        _ = (path, work_item_id)
        raise receipts.BeadsMappingError(record_id=work_item_id, detail="unreadable")

    monkeypatch.setattr(receipts, "read_work_item_comments", _unreadable_comments)
    assert (
        receipts.recorded_drift_verdict(
            path=_config(), anchor=_ANCHOR, merge="merge", spec_revision="tree:one"
        )
        is None
    )
