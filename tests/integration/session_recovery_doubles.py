"""The two seams the recovery consumer leaves to its caller, as recording doubles.

Shared by `test_session_recovery_receipt_scenario162` and
`test_session_recovery_reconciliation_scenario163`, which bind two scenarios of
ONE clause and need the same two seams. One pair of doubles rather than two
copies, for the reason the sibling `governed_repo_fixtures` gives: a second copy
drifts, and the direction it drifts in is invisible — both modules keep passing
while they stop agreeing about what a command or a lookup is.

BOTH DOUBLES RECORD RATHER THAN MERELY ANSWER, and that is what the two bindings
rest on. "One command effect however many triggers arrive" is a claim about the
number of real INVOCATIONS, which no returned value can carry; and "the
replacement looked the effect up before retrying" is a claim about a call that
DID happen beside one that did not. A double that only answered would make both
assertions true of a build that ran the command three times.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._session_recovery_effect import RecoveryEffect

__all__: list[str] = [
    "RecordingCommand",
    "RecordingLookup",
]


class RecordingCommand:
    """A sanctioned command that records every invocation it was asked to make.

    `effect=None` is the AMBIGUOUS outcome rather than a failure: a command that
    ran and could not say what it did is indistinguishable from one that never
    started, which is the state the durable-effect lookup exists to resolve.
    """

    def __init__(self, *, effect: RecoveryEffect | None) -> None:
        self.calls: list[str] = []
        self._effect = effect

    def __call__(self, *, attempt_id: str, operation: str) -> RecoveryEffect | None:
        self.calls.append(f"{attempt_id}:{operation}")
        return self._effect


class RecordingLookup:
    """The durable-effect lookup, and a record of every attempt it was asked about."""

    def __init__(self, *, effect: RecoveryEffect | None = None) -> None:
        self.calls: list[str] = []
        self._effect = effect

    def observe(self, *, attempt_id: str) -> RecoveryEffect | None:
        self.calls.append(attempt_id)
        return self._effect
