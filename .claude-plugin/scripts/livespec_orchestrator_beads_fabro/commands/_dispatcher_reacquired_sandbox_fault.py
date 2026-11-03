"""Recognition of Dispatcher helpers lost when Fabro re-acquires a sandbox.

The factory restores the worktree when it resumes a run after a store fault, but
the Dispatcher materializes these helpers outside that worktree.  A missing
helper is therefore a host fault only when the same run records the measured
re-acquisition sequence; the signal by itself remains an ordinary terminal
failure.
"""

from __future__ import annotations

__all__: list[str] = [
    "HOST_FAULT_RELEASE_CAUSE",
    "HOST_FAULT_RELEASE_STAGE",
    "HOST_FAULT_RELEASE_STATUS",
    "reacquired_sandbox_helper_absence",
]

HOST_FAULT_RELEASE_STATUS = "host-fault-release"
HOST_FAULT_RELEASE_STAGE = "host-fault-release"
HOST_FAULT_RELEASE_CAUSE = "host fault: re-acquired sandbox omitted Dispatcher helper"

_HELPER_ABSENCE_SIGNALS = (
    "LIVESPEC_PROOF_GRADE_PROGRAM_ABSENT",
    "LIVESPEC_JANITOR_PLUGIN_GATE_FAILED",
    "LIVESPEC_COMMIT_SETTLE_RUNNER_ABSENT",
)
_REACQUISITION_EVIDENCE = (
    "fencing a recorded sandbox",
    "scope environment acquired",
)


def reacquired_sandbox_helper_absence(*, text: str) -> bool:
    """Whether output proves a helper vanished after the sandbox was re-acquired."""
    return any(signal in text for signal in _HELPER_ABSENCE_SIGNALS) and all(
        evidence in text for evidence in _REACQUISITION_EVIDENCE
    )
