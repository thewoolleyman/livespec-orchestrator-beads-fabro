"""The in-memory append step a reconcile pass keeps its warning ledger current with.

`ledger_with_appended` replaced re-reading the whole dispatch journal once per
warning and per attempt (bd-ib-6bbcda), so its one claim is equivalence: the
ledger after an append must be the ledger a full re-fold of the journal plus
that record produces. Each case appends one record of a different shape to the
SAME base journal, which holds one live warning and one already retired, and
compares against the re-fold rather than against a hand-written ledger, so a
case cannot pass by agreeing with a mistaken expectation.
"""

from __future__ import annotations

from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._acp_fallback_warning_ledger import (
    fold_model_fallback_warnings,
    ledger_with_appended,
)


def _warning(*, warning_id: str) -> dict[str, Any]:
    """One warning record, in the shape the selection replay mints."""
    return {
        "at": "2026-10-22T08:00:00Z",
        "stage": "acp-model-fallback-observed",
        "schema_version": 1,
        "warning_id": warning_id,
        "node": "implement",
        "occurred_at": "2026-10-22T08:00:00Z",
        "candidate_display_name": "GLM 5.1",
        "candidate_key": "glm-acp-agent/zai/glm-5.1",
        "candidate_index": 1,
        "availability_key": "zai",
        "hold_key": "zai",
        "cause": "dispatcher-selection",
        "scope": "node",
        "primary_generation": "primary-1",
        "full_chain": "chain-1",
        "event_id": f"selection:{warning_id}",
        "work_item_id": "bd-ib-6bbcda",
    }


def _cleared(*, warning_id: str) -> dict[str, Any]:
    return {
        "stage": "acp-model-fallback-cleared",
        "node": "implement",
        "warning_ids": [warning_id],
        "primary_generation": "primary-1",
        "cleared_by_attempt_started_at": "2026-10-22T09:00:00Z",
    }


_BASE = (
    _warning(warning_id="acpwarn-live"),
    _warning(warning_id="acpwarn-retired"),
    _cleared(warning_id="acpwarn-retired"),
)


@pytest.mark.parametrize(
    "appended",
    [
        pytest.param(_warning(warning_id="acpwarn-new"), id="a-new-warning"),
        pytest.param(_warning(warning_id="acpwarn-live"), id="a-warning-already-live"),
        pytest.param(_warning(warning_id="acpwarn-retired"), id="a-warning-already-retired"),
        pytest.param(_cleared(warning_id="acpwarn-live"), id="a-clearance-of-the-live-one"),
        pytest.param(
            {**_cleared(warning_id="acpwarn-live"), "stage": "acp-model-fallback-superseded"},
            id="a-supersede-of-the-live-one",
        ),
        pytest.param(
            {"stage": "acp-model-fallback-observed", "warning_id": "acpwarn-broken"},
            id="an-unparseable-warning",
        ),
        pytest.param({"stage": "dispatch-run-stamp", "run_id": "01RUN"}, id="an-unrelated-stage"),
    ],
)
def test_an_append_equals_a_full_re_fold(appended: dict[str, Any]) -> None:
    expected = fold_model_fallback_warnings(records=(*_BASE, appended))

    actual = ledger_with_appended(
        ledger=fold_model_fallback_warnings(records=_BASE), record=appended
    )

    assert actual == expected


def test_the_base_journal_holds_one_live_and_one_retired_warning() -> None:
    """The control: without both, half the cases above compare two empty ledgers."""
    ledger = fold_model_fallback_warnings(records=_BASE)

    assert [warning.warning_id for warning in ledger.warnings] == ["acpwarn-live"]
    assert ledger.retired_ids == frozenset({"acpwarn-retired"})
