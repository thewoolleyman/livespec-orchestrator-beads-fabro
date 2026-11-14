"""A run that ended at `proof_verify` posting no record is recognised from its own stage map.

Work-item `bd-ib-bwwkne`. `SPECIFICATION/contracts.md` section "Resume from a
published pull request (`resume --item`)" paragraph "A resume after an ended
`proof_verify` re-enters at `proof_verify`" reads the earlier run's factory
record for three facts: a `review` visit after the `proof_capture` visit whose
outcome selected `approve`, a later `proof_verify` visit that ended without a
record, and no stage after it other than a terminal node.

THE SHAPE BELOW IS MEASURED. Run `01M7A2P35VZH8WYX5VBVJ3YH9R` of
`livespec-dev-tooling-5wybjq` carried `proof_capture@2`, `review@2` (clean) and
`proof_verify@1` (failed twice on "Authentication required") in its top-level
`stages` map, keyed `<node>@<visit>` in the engine's own order, and then took
`needs_human`. The Petri engine writes no per-edge record, so the `approve`
selection is read off the sequence: `review -> proof_verify` is the graph's
only edge into `proof_verify` from `review`, and it is the `approve` one.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_verify_ending"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_resume_verify_ending.py"
)


def _ended(*, stages: dict[str, str] | None) -> bool:
    """The reader's answer for one run record whose stages carry the given states."""
    assert _MODULE_PATH.is_file()
    module: Any = importlib.import_module(_MODULE_NAME)
    record: dict[str, object] = {"status": "failed"}
    if stages is not None:
        record["stages"] = {
            key: {"handler": "agent", "state": state} for key, state in stages.items()
        }
    return bool(module.proof_verify_ended_from_payload(payload=[record]))


def test_the_measured_credential_fault_ending_is_recognised() -> None:
    """capture, a clean review, a failed verify, then the needs_human terminal."""
    assert _ended(
        stages={
            "implement@1": "succeeded",
            "proof_capture@1": "succeeded",
            "review@1": "succeeded",
            "proof_capture@2": "succeeded",
            "review@2": "succeeded",
            "proof_verify@1": "failed",
            "needs_human@1": "succeeded",
        }
    )


def test_a_verify_that_succeeded_without_a_verdict_is_an_ended_verify() -> None:
    """The clause counts a turn that emitted no verdict label as ending without a record."""
    assert _ended(
        stages={
            "proof_capture@1": "succeeded",
            "review@1": "succeeded",
            "proof_verify@1": "succeeded",
            "exit@1": "succeeded",
        }
    )


def test_a_verify_that_is_the_last_stage_is_recognised_without_a_terminal_entry() -> None:
    """No terminal entry is required: the clause forbids only a LATER non-terminal stage."""
    assert _ended(
        stages={
            "proof_capture@1": "succeeded",
            "review@1": "succeeded",
            "proof_verify@1": "failed",
        }
    )


def test_a_run_that_ended_at_review_is_not_an_ended_verify() -> None:
    """Without a `proof_verify` visit nothing says the replay was ever tried."""
    assert not _ended(
        stages={
            "proof_capture@1": "succeeded",
            "review@1": "failed",
            "needs_human@1": "succeeded",
        }
    )


def test_a_review_that_did_not_succeed_is_not_an_approval() -> None:
    """A failed review visit selected no `approve` edge, whatever stage follows it."""
    assert not _ended(
        stages={
            "proof_capture@1": "succeeded",
            "review@1": "failed",
            "proof_verify@1": "failed",
            "needs_human@1": "succeeded",
        }
    )


def test_a_stage_after_the_verify_other_than_a_terminal_defeats_the_anchor() -> None:
    """A `proof_grade` or `fix` visit after the verify means it did reach a verdict."""
    assert not _ended(
        stages={
            "proof_capture@1": "succeeded",
            "review@1": "succeeded",
            "proof_verify@1": "succeeded",
            "proof_grade@1": "failed",
            "needs_human@1": "succeeded",
        }
    )
    assert not _ended(
        stages={
            "proof_capture@1": "succeeded",
            "review@1": "succeeded",
            "proof_verify@1": "failed",
            "fix@1": "succeeded",
        }
    )


def test_a_verify_not_preceded_by_a_review_of_a_capture_is_not_recognised() -> None:
    """The review that approved must have followed the capture it approved."""
    assert not _ended(
        stages={
            "proof_capture@1": "succeeded",
            "proof_verify@1": "failed",
            "needs_human@1": "succeeded",
        }
    )
    assert not _ended(
        stages={
            "review@1": "succeeded",
            "proof_verify@1": "failed",
            "needs_human@1": "succeeded",
        }
    )


def test_a_record_that_cannot_be_read_names_no_ended_verify() -> None:
    """Every unusable shape answers False, so the verdict fallback decides instead."""
    assert _MODULE_PATH.is_file()
    module: Any = importlib.import_module(_MODULE_NAME)
    assert not module.proof_verify_ended_from_payload(payload=None)
    assert not module.proof_verify_ended_from_payload(payload=[])
    assert not module.proof_verify_ended_from_payload(payload=[{"status": "failed"}])
    assert not module.proof_verify_ended_from_payload(payload=[{"stages": ["proof_verify@1"]}])
    assert not _ended(stages=None)
    assert not _ended(stages={})
