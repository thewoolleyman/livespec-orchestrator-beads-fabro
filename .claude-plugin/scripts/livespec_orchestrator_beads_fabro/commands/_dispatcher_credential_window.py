"""The two figures a worker's maximum run budget is the smaller of, and which won.

WHY A SMALLER-OF-TWO RULE EXISTS AT ALL, which is the whole of this module's
reason for being. `_dispatcher_credential_requirement` derives an execution
ALLOWANCE by summing the visit caps, retry budgets and resolved node timeouts of
the selected graph. That sum is an upper bound no run reaches, and it is the
correct direction for a credential floor -- right up to the point where it
exceeds what the host can MINT. A freshly renewed Codex credential carries
864000 seconds of life; v175's recapture route took the shipped graph's
allowance to 902955 and its freshness requirement to 906555, and every
Codex-routed dispatch then refused at the gate with no run and no claim. No
configuration in the repository could buy that back, because the requirement
had passed the credential's own ceiling: a raised bound buys nothing when the
comparand is what a provider issues.

WHAT CHANGED, STATED AS A RELATION RATHER THAN AS A NUMBER. The allowance is a
sum over a GRAPH, so it grows with every cycle a ratified change adds. The
bounded credential-use window is a sum over two CONFIGURED FIGURES the factory
enforces -- the credential queue allowance and the whole-run wall budget -- so
it grows only when an operator raises one of them. Taking the smaller makes the
requirement bounded by what the factory enforces rather than by what a graph can
ask for, which is why a graph change can no longer price a fresh credential out.

AND WHY THAT IS SOUND RATHER THAN MERELY CONVENIENT, because a smaller bound on
a credential looks like a relaxation and is not. The window is not an estimate:
the whole-run wall budget is the watchdog's own cancel threshold and the queue
allowance is the interval past which the start check REFUSES a first launch, so
a run that outlives their sum has already been refused or cancelled by a
mechanism that does not depend on this figure. The figure that bounds credential
use is therefore the one the factory will actually hold the run to, and the
allowance above it describes execution the factory would never permit.

WHY THE GOVERNING FIGURE IS NAMED AND NOT JUST MEASURED. The two figures have
OPPOSITE remedies. A dispatch bounded by its execution allowance is shortened by
reducing a node timeout or a visit cap; a dispatch bounded by the window is
widened by raising `dispatcher.credential_queue_allowance_seconds` or the wall
budget. An operator handed a bare number has no route from the refusal to the
key, and the two cases are indistinguishable in the number alone -- which is why
the status and manual-renewal surfaces are required to name which governed.

THE TIE RESOLVES TO THE EXECUTION ALLOWANCE, deliberately and with nothing
riding on it beyond determinism. Equal figures are equally "the smaller", so
either name is true; naming the allowance keeps the answer stable rather than
dependent on the comparison's shape, and the allowance is the figure a reader of
the detail text is already looking at.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "CREDENTIAL_USE_WINDOW_FIGURE",
    "EXECUTION_ALLOWANCE_FIGURE",
    "GoverningRunBudget",
    "credential_use_window_seconds",
    "governing_run_budget",
]

# The two names an operator reads. Spelled once because they appear on the
# status surface, on the manual-renewal surface, in the requirement detail and
# in the deadline journal record -- and a surface naming a figure by a different
# word is a surface an operator cannot join to the key that moves it.
EXECUTION_ALLOWANCE_FIGURE = "execution allowance"
CREDENTIAL_USE_WINDOW_FIGURE = "bounded credential-use window"


@dataclass(frozen=True, kw_only=True)
class GoverningRunBudget:
    """The worker's maximum run budget, with the name of the figure that set it.

    ONE value rather than two returns, because the number and its provenance are
    only useful together: a caller handed the number alone cannot tell an
    operator which key to edit, and a caller handed the name alone has nothing
    to enforce. Every surface that reports one reports both.
    """

    seconds: int
    figure: str


def credential_use_window_seconds(
    *, queue_allowance_seconds: int, run_wall_budget_seconds: int
) -> int:
    """The bounded credential-use window: the queue allowance plus the wall budget.

    A SUM rather than a maximum, and the reason is that the two intervals are
    consecutive rather than alternative. The queue allowance bounds how long a
    run may sit between the instant its credential was projected and its first
    coding-agent launch; the wall budget bounds how long it may then RUN. A
    credential has to cover both, so a window set to either one alone would
    deadline a run that queued legitimately and then started working.
    """
    return queue_allowance_seconds + run_wall_budget_seconds


def governing_run_budget(
    *, execution_allowance_seconds: int, credential_use_window_seconds: int
) -> GoverningRunBudget:
    """The smaller of the two figures, carrying the name of whichever governed.

    STRICTLY SMALLER selects the window, so an exact tie resolves to the
    execution allowance -- see the module docstring for why nothing rides on
    that beyond determinism.
    """
    if credential_use_window_seconds < execution_allowance_seconds:
        return GoverningRunBudget(
            seconds=credential_use_window_seconds, figure=CREDENTIAL_USE_WINDOW_FIGURE
        )
    return GoverningRunBudget(
        seconds=execution_allowance_seconds, figure=EXECUTION_ALLOWANCE_FIGURE
    )
