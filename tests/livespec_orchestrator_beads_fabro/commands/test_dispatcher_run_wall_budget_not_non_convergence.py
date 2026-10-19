"""A wall-budget cancel is not factory non-convergence (bd-ib-sdxfsn).

`SPECIFICATION/contracts.md` section "Dispatcher progress watchdog" -> "The
whole-run wall budget": "A budget cancel is not non-convergence, under the same
rule as a `stalled-no-progress` outcome above: no `backlog` bounce, no
`non-convergence-bounce` record, and no non-convergence observation in the
calibration pass."

THE THREE ARE ONE CLAIM BUT THREE MECHANISMS, which is why they are asserted
together here. The bounce is keyed on a `failed` status carrying the
non-converged marker, so a budget cancel's own status declines it; the record is
written only by that bounce; and the CALIBRATION pass is the one that does not
follow from either, because its non-convergence signal is `converged is not
True` -- which a budget-cancelled run satisfies while saying nothing at all
about whether the slice was too big.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.calibration_analysis import analyze_calibration
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion import (
    NON_CONVERGENCE_BOUNCE_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records import (
    RUN_WALL_BUDGET_EXCEEDED_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_terminal_routing import (
    dispose_terminal_routing,
)
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-budgetnonconv"
_RUN_ID = "01BUDGETRUN"
_NOW_ISO = "2026-10-13T18:00:00Z"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    """The hermetic in-memory tenant, flipped on through its one env seam."""
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="active",
        title="A dispatched slice that outran its wall budget",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-13T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )


def test_a_budget_cancel_neither_bounces_to_backlog_nor_journals_one(
    tmp_path: Path,
) -> None:
    """The item rests for a human instead of returning to intake."""
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())
    path = tmp_path / "journal.jsonl"
    _ = path.write_text(
        json.dumps(
            {
                "stage": RUN_WALL_BUDGET_EXCEEDED_STAGE,
                "work_item_id": _ITEM_ID,
                "run_id": _RUN_ID,
                "factory": "hp",
                "executing_stage": "implement",
                "elapsed_seconds": 25200.0,
                "budget_seconds": 21600.0,
                "budget_layer": "repository",
                "preserved_pointer": "comment-9173",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    journal = JournalFile(path=path)
    dispose_terminal_routing(
        repo=repo,
        item=_item(),
        outcome=DispatchOutcome(
            work_item_id=_ITEM_ID,
            status=RUN_WALL_BUDGET_EXCEEDED_STAGE,
            stage="fabro-run",
            pr_number=None,
            merge_sha=None,
            detail="",
            fabro_run_id=_RUN_ID,
        ),
        journal=journal,
        now_iso=_NOW_ISO,
    )
    rested = [item for item in read_work_items(path=_config()) if item.id == _ITEM_ID][-1]
    assert rested.status == "blocked"
    assert rested.status != "backlog"
    stages = [
        json.loads(line).get("stage") for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert NON_CONVERGENCE_BOUNCE_STAGE not in stages


def test_the_calibration_pass_declines_a_budget_cancelled_run() -> None:
    """A budget cancel is not a non-convergence observation.

    Its `converged` flag is false and its bounce flag is false, so the pass's
    own disjunct would carry it in as a slice that would not converge -- which
    is a claim about the SLICE's size, and a budget cancel makes no such claim.
    The record's `outcome_class` is built from the stage constant itself, so a
    local literal in the pass that no longer matched it would fail here rather
    than quietly skew every proposed ceiling.

    The converged row beside it is the control: a pass that declined every
    record would satisfy the first assertion exactly as a correct one does.
    """
    budget_cancelled: dict[str, object] = {
        "converged": False,
        "outcome_class": f"{RUN_WALL_BUDGET_EXCEEDED_STAGE}:fabro-run",
        "acceptance_count": 7,
    }
    converged: dict[str, object] = {
        "converged": True,
        "outcome_class": "green",
        "acceptance_count": 1,
    }

    proposal = analyze_calibration(records=(budget_cancelled, converged))

    assert (proposal.total_runs, proposal.non_converged_runs) == (1, 0)


def test_an_ordinary_non_green_run_is_still_correlated() -> None:
    """The exclusion is narrow: only the two watchdog cancel classes decline.

    Without this control an exclusion that matched any non-green terminal would
    satisfy the case above while discarding the very signal the pass exists to
    correlate.
    """
    failed: dict[str, object] = {
        "converged": False,
        "outcome_class": "failed:janitor-post-merge",
        "acceptance_count": 9,
    }
    converged: dict[str, object] = {
        "converged": True,
        "outcome_class": "green",
        "acceptance_count": 1,
    }

    proposal = analyze_calibration(records=(failed, converged))

    assert (proposal.total_runs, proposal.non_converged_runs) == (2, 1)
