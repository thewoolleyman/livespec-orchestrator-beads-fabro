"""The targeted dispatch's admit-and-launch step is its own cohesive module.

The same seam `_dispatcher_loop_wave` is to `_dispatcher_loop_command`: the
command module owns the INVOCATION — the preamble, the store preparation, the
size and ledger preconditions, the selection, the shared pre-dispatch wall and
the post-verdict tail — while the launch module owns the one thing that happens
between them, which is admitting the chosen target and launching it.

WHY THIS IS ASSERTED AT ALL RATHER THAN LEFT TO THE SIZE CHECK. A file LLOC
reading is a number, and the honest ways to lower it and the dishonest ones
produce the same number: a re-export shim, an exemption marker, or a cosmetic
line-pack each satisfy the ceiling while leaving one module doing two jobs. The
claims below are about the SEAM instead — that the step moved, that it moved as
a PUBLIC entry point rather than a privately-imported helper, and that the
command module genuinely gave up the valve and the launch rather than keeping
them beside a forwarding call.

WHY THE MODULE IS REACHED THROUGH `importlib` RATHER THAN A MODULE-TOP IMPORT.
A top-level import of a module that does not exist yet dies at COLLECTION, so
the Red would prove only unimportability — zero assertions run — rather than
proving the step had not moved. The first assertion is therefore a genuine check
on the expected path, which fails as an assertion before any import is reached.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_LAUNCH_MODULE = f"{_PACKAGE}._dispatcher_run_launch"
_COMMAND_MODULE = f"{_PACKAGE}._dispatcher_run_commands"

_COMMANDS_DIR = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_LAUNCH_PATH = _COMMANDS_DIR / "_dispatcher_run_launch.py"


def test_the_targeted_admit_and_launch_step_lives_in_its_own_module() -> None:
    """It exists, it is PUBLIC, and it is the module's whole declared surface.

    Public is the load-bearing half. Only public names may cross a module
    boundary here — pyright strict's `reportPrivateUsage` and the
    `private_calls` gate both reject importing a `_`-prefixed name defined
    elsewhere — so a split that moved the step and left it private would be the
    usual way this refactor fails, and it would fail at the gate rather than
    here if nothing asserted the surface.
    """
    assert _LAUNCH_PATH.is_file()
    module = importlib.import_module(_LAUNCH_MODULE)

    assert module.__all__ == ["admit_and_dispatch_target"]
    assert inspect.isfunction(module.admit_and_dispatch_target)


def test_the_command_module_gave_up_the_valve_and_the_launch() -> None:
    """The step MOVED; it was not copied, re-exported, or left behind a shim.

    The private twin being gone is the weakest of the three claims — a file can
    drop a name and keep doing the work. The other two are what make the split
    real: `admit_and_select` is the valve that writes `ready -> active`, and
    `dispatch_one` is what creates the factory run, so a command module still
    holding either is still the module that claims and launches, whatever its
    line count now reads.
    """
    command = importlib.import_module(_COMMAND_MODULE)

    assert not hasattr(command, "_admit_and_dispatch_target")
    assert not hasattr(command, "admit_and_select")
    assert not hasattr(command, "dispatch_one")


def test_the_launch_module_carries_the_step_with_its_design_record() -> None:
    """The body moved VERBATIM, docstrings and comments included.

    A decomposition relocates code; it does not re-golf it. The comment this
    looks for is the one that records WHY the targeted path passes
    `enforce_cap=False` while the drain enforces the cap — the single most
    load-bearing line in the step, and precisely the kind of rationale a
    "clean up while moving" pass deletes. Stripping it would buy zero LLOC,
    because the counter already excludes comments.
    """
    assert _LAUNCH_PATH.is_file()
    source = _LAUNCH_PATH.read_text(encoding="utf-8")

    assert "does NOT enforce the per-repo WIP cap" in source
    assert "bd-ib-huoyk7" in source
