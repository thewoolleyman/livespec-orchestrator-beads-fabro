"""Print a replayable causal-recovery receipt transition against the fake store."""

from __future__ import annotations

import json
import os
import runpy
import sys
import tempfile
from pathlib import Path
from typing import Any

os.environ["LIVESPEC_BEADS_FAKE"] = "1"

from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain import (
    ChainHead,
    read_chain_head,
)
from livespec_orchestrator_beads_fabro.commands._plan_recovery_receipt_write import (
    RecoveryReceiptRequest,
    RecoveryReceiptWrite,
    record_recovery_receipts,
)
from livespec_orchestrator_beads_fabro.commands._plan_recovery_receipts import (
    RECEIPTS_RECORDED,
    RECORDED_NOT_EXECUTED,
    recorded_attempt,
)

__all__: list[str] = ["main"]

_EPIC_ID = "bd-ib-receiptepic"
_ATTEMPT_ID = "attempt-0001"
_LATER_ATTEMPT_ID = "attempt-0002"
_NOW = "2026-10-20T09:00:00Z"
_UNREADABLE_CHAIN = "the seeded recovery authority chain was unreadable"
_MISSING_RECEIPTS = "the dispatched attempt did not record all receipts"
_UNEXPECTED_EXECUTION = "the later undispatched attempt was marked executed"


def main() -> None:
    """Seed executed and undispatched attempts, then print their durable results."""
    helpers = runpy.run_path(
        str(
            Path(__file__).resolve().parents[4]
            / "tests/livespec_orchestrator_beads_fabro/commands"
            / "test_plan_recovery_receipts.py"
        )
    )
    try:
        _print_executed_transition(helpers=helpers)
        _print_later_undispatched_attempt(helpers=helpers)
    finally:
        reset_fake_singleton()


def _print_executed_transition(*, helpers: dict[str, Any]) -> None:
    """Print the receipt transition and preserved authority values."""
    with tempfile.TemporaryDirectory(prefix="receipt-transition-") as temporary:
        root = Path(temporary)
        config = helpers["_seed"](tmp_path=root)
        journal = helpers["_journal"](
            tmp_path=root,
            records=(
                helpers["_dispatch_record"](),
                helpers["_run_record"](),
                helpers["_outcome_record"](),
            ),
        )
        before = read_chain_head(config=config, epic_id=_EPIC_ID)
        result = record_recovery_receipts(
            request=RecoveryReceiptRequest(
                config=config,
                epic_id=_EPIC_ID,
                attempt_id=_ATTEMPT_ID,
                journal_path=journal,
                author="receipt-transition-reproducer",
                now=_NOW,
            )
        )
        after = read_chain_head(config=config, epic_id=_EPIC_ID)
        if not isinstance(before, ChainHead) or not isinstance(after, ChainHead):
            raise TypeError(_UNREADABLE_CHAIN)
        if not isinstance(result, RecoveryReceiptWrite):
            raise TypeError(result.detail)
        attempt = recorded_attempt(authority_record=after.authority.last_recovery_attempt)
        if result.status != RECEIPTS_RECORDED or attempt is None:
            raise RuntimeError(_MISSING_RECEIPTS)
        _ = sys.stdout.write(
            json.dumps(
                {
                    "authority_invariants": {
                        "consumed_handoffs": after.authority.consumed_handoffs,
                        "epoch_advanced": after.epoch > before.epoch,
                        "item_attributable_attempts": attempt.record["item_attributable_attempts"],
                        "original_deadline": after.authority.original_deadline,
                    },
                    "executed_status": result.status,
                    "receipts": {
                        "claim": attempt.receipts.claim,
                        "execution": attempt.receipts.execution,
                        "outcome": attempt.receipts.outcome,
                    },
                },
                sort_keys=True,
            )
            + "\n"
        )


def _print_later_undispatched_attempt(*, helpers: dict[str, Any]) -> None:
    """Print that a later attempt cannot inherit the earlier executor records."""
    reset_fake_singleton()
    with tempfile.TemporaryDirectory(prefix="receipt-transition-later-") as temporary:
        root = Path(temporary)
        record = helpers["_attempt_record"]()
        record["attempt"] = {**record["attempt"], "attempt_id": _LATER_ATTEMPT_ID}
        config = helpers["_seed"](
            tmp_path=root,
            authority=helpers["_authority"](attempt=record),
        )
        journal = helpers["_journal"](
            tmp_path=root,
            records=(
                {
                    "stage": "causal-recovery-attempt",
                    "work_item_id": "bd-ib-receipttarget",
                    "attempt_id": _ATTEMPT_ID,
                },
                helpers["_dispatch_record"](),
                helpers["_run_record"](),
                helpers["_outcome_record"](),
                {
                    "stage": "causal-recovery-attempt",
                    "work_item_id": "bd-ib-receipttarget",
                    "attempt_id": _LATER_ATTEMPT_ID,
                },
            ),
        )
        result = record_recovery_receipts(
            request=RecoveryReceiptRequest(
                config=config,
                epic_id=_EPIC_ID,
                attempt_id=_LATER_ATTEMPT_ID,
                journal_path=journal,
                author="receipt-transition-reproducer",
                now=_NOW,
            )
        )
        if not isinstance(result, RecoveryReceiptWrite):
            raise TypeError(result.detail)
        if result.status != RECORDED_NOT_EXECUTED:
            raise RuntimeError(_UNEXPECTED_EXECUTION)
        _ = sys.stdout.write(
            json.dumps(
                {
                    "historical_records_not_inherited": result.receipts.claim is None,
                    "undispatched_receipts": {
                        "claim": result.receipts.claim,
                        "execution": result.receipts.execution,
                        "outcome": result.receipts.outcome,
                    },
                    "undispatched_status": result.status,
                },
                sort_keys=True,
            )
            + "\n"
        )
