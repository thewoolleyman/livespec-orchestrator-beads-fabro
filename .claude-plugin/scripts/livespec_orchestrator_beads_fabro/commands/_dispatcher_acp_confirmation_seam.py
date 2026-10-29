"""The production confirmation-turn seam: what admission RUNS for an owed confirmation.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Availability is re-confirmed after expiry": a candidate covered by
an expired hold carries an outstanding confirmation, and "Per-node selection"
MUST NOT choose it until a successfully completed ACP prompt turn satisfies it.

THE SEAM EXISTED AND NOTHING SUPPLIED IT (`bd-ib-i4nert`). The filter
(`_acp_candidate_preflight`) takes a `confirm` callable, the probe's shape and
its performing half (`_acp_availability_probe*`) were built, and no production
caller ever handed the filter one. Expiry ends a hold but establishes nothing,
so a tenant that receives no successful dispatch -- the only other thing that
satisfies an expired observation -- refused every admission indefinitely, with
no turn attempted. Neither a configuration gate nor one entry point was at
fault: `dispatch` and `loop --item` reach the same admission valve, and the
valve supplied no seam.

THIS MODULE IS THAT SEAM, built from the evaluation's own inputs rather than
from a second read of the ledger. It is handed the `PreflightInputs` the filter
will use, so the expired observations a turn is run to satisfy, and whether a
candidate is a built-in, are the very values the filter decided from.

IT DOES NOT IMPORT THE PERFORMING HALF, and that is a requirement rather than a
tidiness: `_dispatcher_acp_preflight` imports this module, and the preflight sits
inside the engine's own import closure, which the performing half re-enters
through `_dispatcher_shell_runner` -- the cycle that leaf was split out of the
aggregate to break. The turn is therefore INJECTED as `ConfirmationTurns.perform`,
and `_dispatcher_admission_confirmation` -- which only the admission valve
imports -- is the one place that names the real performer.

WHERE THE RECORDS GO. Every turn is journaled -- its row, its attempt-cost record
charged to the one item whose admission evaluation ran it ("A shared availability
probe MUST NOT be charged in full to multiple items") and, for a refusal that
classifies as an eligible provider limit, the new occurrence-time-scoped hold.
This module appends them; the performing half only builds them, because the one
place that decides WHEN a record lands is the caller's.

A turn that could not be RUN at all -- no participating factory, an identity-less
or in-protocol candidate -- returns `None`, which the filter skips exactly as an
absent seam does: the clause's "any other probe failure", with no hold.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._acp_availability_confirmation import (
    outstanding_confirmation_holds,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_preflight_skips import PreflightInputs
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_file import JournalFile
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroRunner

__all__: list[str] = [
    "ConfirmationTurns",
    "ProbeRecords",
    "with_confirmation_seam",
]


class ProbeRecords(Protocol):
    """What one performed confirmation turn hands back: its ending and its records."""

    @property
    def ending(self) -> str:
        """The ending the turn reached."""
        ...

    @property
    def journal_record(self) -> dict[str, object]:
        """The one journal row every ending produces."""
        ...

    @property
    def attempt_cost_record(self) -> dict[str, object]:
        """The one attempt-cost record every ending produces."""
        ...

    @property
    def hold_record(self) -> dict[str, object] | None:
        """The new hold an eligible refusal mints, else `None`."""
        ...


@dataclass(frozen=True, kw_only=True)
class ConfirmationTurns:
    """Where one admission evaluation's confirmation turns run, are journaled and charged.

    `perform` is the performing half (`run_availability_probe`), injected for the
    import-cycle reason the module docstring gives. It returns the turn's records
    or the string saying why no turn could be run. `work_item_id` is the ONE item
    every turn of this evaluation is charged to. `runner` defaults to ABSENT,
    which lets the performing half open its own shell runner; it is a field so a
    caller can inject the engine.
    """

    perform: Callable[..., ProbeRecords | str]
    journal: JournalFile
    work_item_id: str
    runner: FabroRunner | None = None


def with_confirmation_seam(
    *,
    inputs: PreflightInputs,
    turns: ConfirmationTurns | None,
    repo: Path,
    now_iso: str,
    timeout_seconds: int,
) -> PreflightInputs:
    """These inputs with the confirmation seam supplied, or unchanged when `turns` is absent."""
    if turns is None:
        return inputs
    return replace(
        inputs,
        confirm=_ConfirmationTurn(
            turns=turns,
            repo=repo,
            now_iso=now_iso,
            timeout_seconds=timeout_seconds,
            inputs=inputs,
        ),
    )


@dataclass(frozen=True, kw_only=True)
class _ConfirmationTurn:
    """The callable the filter runs for each candidate that owes a confirmation.

    A class with `__call__` rather than a closure because the filter calls its
    seam with the candidate POSITIONALLY, and a keyword-only closure would not
    accept that call while a positional one would be a keyword-only violation.

    It returns the turn's ENDING, or `None` when no turn could be run. The
    expired observations a turn names, and whether the candidate is a built-in,
    are read off `inputs` -- the evaluation's own values -- so the journal row's
    provenance describes the records the filter is skipping the candidate for.
    """

    turns: ConfirmationTurns
    repo: Path
    now_iso: str
    timeout_seconds: int
    inputs: PreflightInputs

    def __call__(self, candidate: AcpCandidate) -> str | None:
        identity = candidate.identity
        owed = outstanding_confirmation_holds(
            expired_holds=self.inputs.expired_holds,
            confirmations=self.inputs.confirmations,
            candidate=candidate,
        )
        result = self.turns.perform(
            repo=self.repo,
            candidate=candidate,
            builtin=identity is not None and identity.pair in self.inputs.builtin_pairs,
            work_item_id=self.turns.work_item_id,
            observation_ids=tuple(hold.observation_id for hold in owed),
            now_iso=self.now_iso,
            timeout_seconds=self.timeout_seconds,
            runner=self.turns.runner,
        )
        if isinstance(result, str):
            return None
        self.turns.journal.append(record=result.journal_record)
        self.turns.journal.append(record=result.attempt_cost_record)
        if result.hold_record is not None:
            self.turns.journal.append(record=result.hold_record)
        return result.ending
