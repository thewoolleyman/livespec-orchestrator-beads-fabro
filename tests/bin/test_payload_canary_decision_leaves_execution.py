"""A canary DECISION, passing or failing, never moves the running Dispatcher.

Work-item `bd-ib-mtuqxb`'s fifth assertion requires the retained execution
path to preserve "candidate canary outcomes without moving a running
Dispatcher to another payload". Cycle 12's control asserted where a
CONSTRUCTED asset path sits, and a path is not a decision — so that half of
the assertion had no evidence behind it.

This supplies the DECISION-TO-EXECUTION relationship. `canary_verdict` turns a
candidate self-check exit code into the verdict the Dispatcher acts on, so a
PASSING and a FAILING canary are both drivable directly, and the question that
matters is what each one does to the tree this process is executing from.

SCOPE, corrected 2026-10-06: this is a PURE MAPPING control and NOT candidate
canary proof. `canary_verdict` is a one-line total function of one integer, and
the cases below call it with the literal constants `0` and `1` -- so nothing
here launches a candidate process, observes an actual candidate result, or
drives a self-update journal decision; the exit codes it maps were written by
this test. An earlier revision described this file as supplying the half of the
fifth assertion that had no evidence, which overclaims and is withdrawn. That
leg is discharged only by driving the exported `self_update_after_release`
boundary with a real bounded subprocess and a recording journal, which belongs
to the downstream `proof_capture` node and its independent `proof_verify`
replay. See
`plan/dispatcher-cache-lifetime/research/003-red-provenance-cycles-9-to-11-2026-10-06.md`
section "CORRECTION, 2026-10-06". No product defect is inferred from the gap.

NOT a Red, and it must not be cited as one. The behaviour was already correct
when this was written and it passed on the first run; the reason it is here is
that nothing else in the work-item observed an actual verdict. Measured
2026-10-06: exit 0 yields `pass`, exit 1 yields `fail`, the two are distinct,
and across both `executing_payload_root()` and the loaded module's own
`__file__` are unchanged.

Why that is the right pair of observables rather than one. `executing_payload_root()`
is derived from `__file__`, so asking only for it could in principle agree with
itself while the module had been reloaded from elsewhere; asserting the loaded
module's resolved path alongside it pins the tree AND the module that answered.
Both must hold, and a verdict that changed either would be the running
Dispatcher moving mid-decision.

Scope is the decision-to-execution relationship only. This observes no update
being applied, no install being promoted and no restart: the running Dispatcher
is read-only about its own artifact by contract, and a test that promoted
anything would be asserting the opposite of the contract.
"""

import importlib
from pathlib import Path
from typing import Any

_PATHS_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_paths"
_DECISION_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_self_update_decision"

_PASSING_EXIT = 0
_FAILING_EXIT = 1


def _module(*, name: str) -> Any:
    return importlib.import_module(name)


def test_a_passing_and_a_failing_canary_verdict_are_distinct_and_move_nothing() -> None:
    """Both verdicts are reachable, they differ, and neither relocates execution."""
    paths = _module(name=_PATHS_MODULE)
    decision = _module(name=_DECISION_MODULE)

    before_root = paths.executing_payload_root()
    before_module = Path(paths.__file__).resolve()

    passing = decision.canary_verdict(exit_code=_PASSING_EXIT)
    failing = decision.canary_verdict(exit_code=_FAILING_EXIT)

    assert passing != failing, (
        "a passing and a failing candidate self-check produced the same verdict, "
        f"so the canary cannot distinguish them: {passing!r}"
    )

    after_root = paths.executing_payload_root()
    after_module = Path(paths.__file__).resolve()

    assert after_root == before_root, (
        "reaching a canary verdict moved the tree this Dispatcher executes from, "
        f"which the fifth assertion forbids: {before_root} -> {after_root}"
    )
    assert after_module == before_module, (
        "the module that answered was reloaded from a different tree across the "
        f"decision: {before_module} -> {after_module}"
    )


def test_the_executing_payload_root_is_derived_from_the_loaded_module() -> None:
    """The two observables above are not the same assertion twice.

    `executing_payload_root()` walks up from the resolving module's own
    `__file__`, so it is pinned to wherever that module was loaded. Stating
    the relationship here is what makes the pair above meaningful rather than
    one fact asserted in two spellings.
    """
    paths = _module(name=_PATHS_MODULE)

    assert paths.executing_payload_root() == Path(paths.__file__).resolve().parents[3], (
        "the executing payload root is no longer derived from the loaded "
        "module, so the pair of observables in this file no longer pins the "
        "tree and the module together"
    )
