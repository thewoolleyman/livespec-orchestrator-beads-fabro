"""Pre-run dispatch claim release helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import terminal_claim
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_writes import (
    claim_status_write,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.store import update_work_item_status
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["release_pre_run_claim_if_needed"]

_PRE_RUN_FAILURE_STAGES = frozenset(
    (
        "fabro-run",
        "github-app-auth",
        "goal-minijinja-preflight",
        "ledger-comments",
        "ledger-labels",
        "run-config-overlay",
        # Node-timeout resolution and workflow-payload materialization both
        # refuse BEFORE any Fabro run exists, so a refusal here is a pre-run
        # failure by construction — leaving the claim on would strand the
        # item `active` with no run behind it.
        "workflow-payload",
    )
)


def release_pre_run_claim_if_needed(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
) -> None:
    if not _should_release_pre_run_claim(item=item, outcome=outcome, journal=journal):
        return
    refusal = claim_status_write(
        repo=repo,
        path=store_config(repo=repo),
        intent="pre-run-release",
        write=update_work_item_status,
        item_id=item.id,
        status="ready",
        clear_assignee=True,
        journal=journal,
        # No run was ever learned, so the decision rests on the claim alone.
        still_as_decided=terminal_claim(item=item, run_id=None),
    )
    if refusal is not None:
        return
    journal.append(
        record={
            "stage": "ledger-admit-release",
            "work_item_id": item.id,
            "status": "ready",
            "reason": "pre-run-failure-without-fabro-run-id",
            "outcome_stage": outcome.stage,
        }
    )


def _should_release_pre_run_claim(
    *,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
) -> bool:
    if outcome.stage == "fabro-run" and not _journal_has_fabro_run_failure(
        journal=journal,
        item=item,
    ):
        return False
    return (
        item.status == "active"
        and outcome.status == "failed"
        and outcome.fabro_run_id is None
        and outcome.stage in _PRE_RUN_FAILURE_STAGES
    )


def _journal_has_fabro_run_failure(*, journal: JournalFile, item: WorkItem) -> bool:
    read = attempt(action=lambda: journal.path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(read, AttemptFailure):
        return False
    parsed = attempt(
        action=lambda: [json.loads(line) for line in read.splitlines()], exceptions=(ValueError,)
    )
    if isinstance(parsed, AttemptFailure):
        return False
    records = cast("list[object]", parsed)
    return any(_is_fabro_run_failure_record(record=record, item=item) for record in records)


def _is_fabro_run_failure_record(*, record: object, item: WorkItem) -> bool:
    if not isinstance(record, dict):
        return False
    values = cast("Mapping[str, object]", record)
    return (
        values.get("stage") == "fabro-run"
        and values.get("work_item_id") == item.id
        and values.get("exit_code") != 0
    )
