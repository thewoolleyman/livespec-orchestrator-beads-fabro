"""Scenario 228 — the freshness requirement is the SMALLER of two figures.

Binds `SPECIFICATION/scenarios.md` "Scenario 228 — The credential freshness
requirement is the smaller of the execution allowance and the bounded
credential-use window", and the worker-credential-projection paragraph of
`SPECIFICATION/contracts.md` that states the worker's maximum run budget.

WHY THIS HEADING NEEDED A TEST AT ALL, stated here because it is the whole
point of the clause. The execution allowance is derived by SUMMING the visit
caps, retry budgets and resolved node timeouts of the selected graph, so a
ratified graph change that adds one cycle through an existing loop multiplies
into it: v175's recapture route took the shipped graph's allowance to 902955
seconds and its freshness requirement to 906555, which is MORE than the 864000
seconds a freshly renewed Codex credential carries. Every Codex-routed dispatch
then refused at the gate with no run and no claim, and no configuration in the
repository could buy it back — the requirement exceeded what the host can mint.
That is the defect the smaller-of-two rule retires: the requirement is now
bounded by limits the FACTORY enforces (the credential queue allowance plus the
whole-run wall budget) rather than by a sum over a graph.

WHY THE MODULE PATH IS ASSERTED BEFORE THE IMPORT. A top-level import of a
module that does not exist yet dies at COLLECTION, which proves only that the
module is unimportable and runs no assertion at all. Asserting the path first
makes the Red a genuine assertion failure about the behaviour being absent, and
the import then happens inside the test body where the module exists.
"""

from __future__ import annotations

import importlib
from pathlib import Path

_COMMANDS = (
    Path(__file__).resolve().parents[2]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_WINDOW_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_credential_window"
_QUEUE_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_credential_queue_allowance"

# Scenario 228's own figures, kept as named constants so a reader can check each
# against the Gherkin rather than against an arithmetic expression.
_EXECUTION_ALLOWANCE_SECONDS = 902_955
_QUEUE_ALLOWANCE_SECONDS = 86_400
_RUN_WALL_BUDGET_SECONDS = 21_600
_MARGIN_SECONDS = 3_600
_REQUIRED_LIFETIME_SECONDS = 111_600
_FRESH_CREDENTIAL_LIFETIME_SECONDS = 864_000


def test_scenario228_the_bounded_window_governs_when_it_is_smaller() -> None:
    """The window is 108000, so 111600 is required and the window is named.

    Both halves are asserted, and the second is why the first is evidence: a
    figure alone does not say which of the two produced it, and an operator
    reading a refusal needs to know whether to shorten a node timeout or to
    raise the queue allowance. The credential comparison closes the loop on the
    defect — the same graph that priced a fresh credential out now fits inside
    one with 752400 seconds to spare.
    """
    assert (_COMMANDS / "_dispatcher_credential_window.py").is_file(), (
        "the governing-figure arithmetic has no module yet, so the freshness "
        "requirement is still the raw execution allowance"
    )
    window_module = importlib.import_module(_WINDOW_MODULE)

    window = window_module.credential_use_window_seconds(
        queue_allowance_seconds=_QUEUE_ALLOWANCE_SECONDS,
        run_wall_budget_seconds=_RUN_WALL_BUDGET_SECONDS,
    )
    assert window == _QUEUE_ALLOWANCE_SECONDS + _RUN_WALL_BUDGET_SECONDS

    governing = window_module.governing_run_budget(
        execution_allowance_seconds=_EXECUTION_ALLOWANCE_SECONDS,
        credential_use_window_seconds=window,
    )
    assert governing.seconds == window
    assert governing.figure == window_module.CREDENTIAL_USE_WINDOW_FIGURE
    assert governing.seconds + _MARGIN_SECONDS == _REQUIRED_LIFETIME_SECONDS
    assert _REQUIRED_LIFETIME_SECONDS < _FRESH_CREDENTIAL_LIFETIME_SECONDS


def test_scenario228_the_execution_allowance_governs_when_it_is_smaller() -> None:
    """A 60000-second allowance under a 108000-second window governs at 60000.

    The MIRROR of the case above, and it is not redundant: a derivation that
    returned the window unconditionally would satisfy the first case exactly and
    would bound every dispatch at the queue window however short its graph.
    """
    assert (_COMMANDS / "_dispatcher_credential_window.py").is_file()
    window_module = importlib.import_module(_WINDOW_MODULE)

    governing = window_module.governing_run_budget(
        execution_allowance_seconds=60_000,
        credential_use_window_seconds=window_module.credential_use_window_seconds(
            queue_allowance_seconds=_QUEUE_ALLOWANCE_SECONDS,
            run_wall_budget_seconds=_RUN_WALL_BUDGET_SECONDS,
        ),
    )
    assert governing.seconds == 60_000
    assert governing.figure == window_module.EXECUTION_ALLOWANCE_FIGURE
    assert governing.seconds + _MARGIN_SECONDS == 63_600


def test_scenario228_the_queue_allowance_defaults_to_one_day() -> None:
    """A repository declaring nothing resolves the documented 86400 seconds.

    Asserted through the RESOLUTION rather than against the constant, because
    the constant is what a reader of this module would check and the resolution
    is what a dispatch receives: a default declared and never read is the one
    shape a constant-only assertion cannot tell from a working one.
    """
    assert (_COMMANDS / "_dispatcher_credential_queue_allowance.py").is_file(), (
        "the credential queue allowance has no module yet, so no dispatch can "
        "resolve the bounded credential-use window"
    )
    queue_module = importlib.import_module(_QUEUE_MODULE)

    resolved = queue_module.credential_queue_allowance_from_block(block={})
    assert resolved.seconds == _QUEUE_ALLOWANCE_SECONDS
    assert resolved.seconds == queue_module.DEFAULT_CREDENTIAL_QUEUE_ALLOWANCE_SECONDS
