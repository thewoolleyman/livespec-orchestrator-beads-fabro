"""Regression locks for tenant-safe destructive run attribution."""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    FactoryRunInventory,
    JournaledRuns,
    attributed_runs,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroRunSummary


@pytest.mark.parametrize(
    ("tenant_prefix", "foreign_work_item_id"),
    [
        ("livespec", "livespec-console-beads-fabro-x.1"),
        ("bd-ib", "livespec-console-beads-fabro-x.1"),
    ],
)
def test_goal_text_alone_never_claims_a_foreign_run_for_destruction(
    tenant_prefix: str,
    foreign_work_item_id: str,
) -> None:
    rows = attributed_runs(
        inventory=FactoryRunInventory(
            runs=(
                FabroRunSummary(
                    run_id="01FOREIGN",
                    status_kind="running",
                    goal=f"Work-item: {foreign_work_item_id}",
                    total_usd_micros=None,
                    work_item_id=foreign_work_item_id,
                ),
            ),
            item_statuses={},
            journaled=JournaledRuns(newest_run_id_by_item={}, item_id_by_run={}),
            id_prefix=tenant_prefix,
            factory_name="shared",
            factory_server_url="https://factory.example:32276",
        )
    )

    assert rows == ()
