"""Writing ONE operator clearance onto the participating factory itself.

The WRITE half of the factory-native clearance record; `_acp_clearance_records`
beside it owns the record's shape, and the direction of the one edge between
them is what keeps the pair acyclic. Nothing here decides what a clearance IS,
and nothing there performs IO.

A MINIMAL RECORD IS A DETERMINISTIC ONE-NODE RUN. The record has to be
factory-NATIVE -- the clause allows no sidecar file, cache or store -- so the
only thing a factory records is a run, and the smallest run that records
anything is a single script node whose recorded outcome is the clearance's own
line. It launches no adapter, spends no provider allowance, mints no credential
and clones nothing, which is what keeps an operator's clearance from costing a
dispatch slot's worth of work.

THE REFUSAL IS THE POINT, AND IT IS FAIL-CLOSED IN THE EXPENSIVE DIRECTION. A
clearance whose record cannot be written is NOT a clearance that falls back to
the journal: the factory record is the authority, the journal line is its audit
reference, and a journal-only retirement would clear the hold for this checkout
while every peer kept dispatching into it. So an undeclared factory, a factory
declaring no server, a launch that fails, and a launch whose run id cannot be
read are each returned as a refusal for the valve to surface, and the valve
writes nothing.

THE ENGINE VERSION IS MEASURED RATHER THAN ASSUMED, for the one reason it
matters here: the two engine generations take their workflow argument
differently -- the pinned build takes the materialized config FILE and the
Petri-era build takes the package DIRECTORY -- and `_fabro_client` resolves
that from the reported version. Passing none would hand a Petri-era engine a
file it refuses before any run exists, so the clearance would fail on an engine
that is perfectly able to record it.

THE PAYLOAD RIDES THE SCRIPT THROUGH TWO EXPLICIT ENCODINGS, which is the one
piece of mechanics here worth reading twice. The clearance line is ordinary
JSON, so it carries double quotes, and a `--reason` is operator prose, so it
may carry a single quote: the line is therefore shell-quoted for the script's
own shell and then DOT-escaped for the attribute that carries the script. Both
are deterministic functions of the line, so the recorded outcome is the line
itself -- plainly readable by an operator looking at the run -- rather than an
encoded form only this package can decode.
"""

from __future__ import annotations

import shlex
import tempfile
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_clearance_records import (
    AcpHoldClearance,
    clearance_outcome_text,
    clearance_run_labels,
)
from livespec_orchestrator_beads_fabro.commands._config import (
    resolve_fabro_bin,
    resolve_fabro_factory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_binary_record import (
    engine_binary,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_bin import factory_fabro_bin

# The LEAF rather than the `_dispatcher_io` aggregate that re-exports it, for
# the reason `_acp_factory_run_reader` states beside its own import: the
# aggregate's import closure reaches the ledger resolution this module's caller
# sits inside, and taking it would close the cycle the runner leaf exists to
# break.
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import (
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroRunner

__all__: list[str] = [
    "CLEARANCE_GRAPH_FILE",
    "CLEARANCE_NODE",
    "FactoryClearanceRecord",
    "clearance_workflow_graph",
    "record_factory_clearance",
]

# The one node whose recorded outcome IS the record. Named for what it does
# rather than for the clearance it carries, so a reader of a run row sees the
# same node id whatever was cleared.
CLEARANCE_NODE = "record"
CLEARANCE_GRAPH_FILE = "clearance.fabro"

_MANIFEST = f'[workflow]\ngraph = "{CLEARANCE_GRAPH_FILE}"\n'
_GOAL = "Record one operator ACP availability clearance.\n"
# Generous for a single `printf`, and bounded so an unreachable factory refuses
# the clearance instead of parking the operator's terminal indefinitely.
_LAUNCH_TIMEOUT_SECONDS = 300.0


@dataclass(frozen=True, kw_only=True)
class FactoryClearanceRecord:
    """The factory-native record one accepted clearance wrote.

    `reference` is the shape `_acp_factory_hold_records` gives an observation's
    own audit reference minus its node half: a clearance record has exactly one
    node, so naming it would add nothing a reader could join on.
    """

    factory: str
    run_id: str

    @property
    def reference(self) -> str:
        """The factory run this clearance is reconstructible from."""
        return f"{self.factory}:{self.run_id}"


def clearance_workflow_graph(*, clearance: AcpHoldClearance) -> str:
    """The one-node deterministic graph whose outcome records this clearance.

    The two encodings are applied in this order and no other: the line is
    shell-quoted first, because that is the string the script must contain, and
    the RESULT is then DOT-escaped, because that is the string the attribute
    must contain. Escaping first would quote the escapes.
    """
    script = f"printf %s {shlex.quote(clearance_outcome_text(clearance=clearance))}"
    return (
        "digraph AcpAvailabilityClearance {\n"
        "    start [shape=Mdiamond]\n"
        f'    {CLEARANCE_NODE} [shape=parallelogram, script="{_dot_escaped(text=script)}"]\n'
        "    exit [shape=Msquare]\n"
        f"    start -> {CLEARANCE_NODE} -> exit\n"
        "}\n"
    )


def record_factory_clearance(
    *, repo: Path, clearance: AcpHoldClearance, runner: FabroRunner | None = None
) -> FactoryClearanceRecord | str:
    """Record one clearance on the participating factory, or refuse saying why.

    The factory is the one this repository's own configuration resolves, which
    is the same resolution a dispatch takes: a clearance has to land where the
    evidence it retires is read from, and that is the factory this repository
    participates on rather than a name an operator could pass separately.
    """
    target = resolve_fabro_factory(cwd=repo)
    if target.server is None:
        return (
            f"no participating factory to record the clearance on: factory "
            f"{target.name!r} declares no server, so no peer repository could "
            f"read this clearance"
        )
    command = ShellCommandRunner() if runner is None else runner
    fabro_bin = factory_fabro_bin(factory=target, fallback=resolve_fabro_bin(cwd=repo))
    return _launched(
        clearance=clearance,
        factory=target.name,
        port=FabroPort(
            fabro_bin=fabro_bin,
            target=FabroTarget(server_url=target.server, dev_token=target.dev_token),
            runner=command,
            cwd=repo,
            fabro_version=engine_binary(fabro_bin=fabro_bin, runner=command, cwd=repo).version,
        ),
    )


def _launched(
    *, clearance: AcpHoldClearance, factory: str, port: FabroPort
) -> FactoryClearanceRecord | str:
    """Materialize the one-run payload, launch it, and read its run id back.

    The payload lives in a temporary directory that is removed as the launch
    returns: it is an argument to one invocation rather than state, and the
    record it produces is on the factory. `fabro run` is synchronous, so the
    run has recorded its outcome by the time the id is read.
    """
    with tempfile.TemporaryDirectory(prefix="livespec-acp-clearance-") as staging:
        package = Path(staging)
        graph = package / CLEARANCE_GRAPH_FILE
        _ = graph.write_text(clearance_workflow_graph(clearance=clearance), encoding="utf-8")
        manifest = package / "workflow.toml"
        _ = manifest.write_text(_MANIFEST, encoding="utf-8")
        goal = package / "goal.md"
        _ = goal.write_text(_GOAL, encoding="utf-8")
        result = port.run(
            workflow_toml=manifest,
            goal_file=goal,
            inputs=(),
            timeout_seconds=_LAUNCH_TIMEOUT_SECONDS,
            labels=clearance_run_labels(),
        )
    if result.command.exit_code != 0:
        return (
            f"the clearance record could not be written on factory {factory!r}: "
            f"the launch exited {result.command.exit_code}"
        )
    if result.run_id is None:
        return (
            f"the clearance record's run id could not be read back from factory "
            f"{factory!r}, so the record cannot be referenced"
        )
    return FactoryClearanceRecord(factory=factory, run_id=result.run_id)


def _dot_escaped(*, text: str) -> str:
    """One attribute value as a DOT quoted string's contents.

    Backslashes first and quotes second, because escaping the quotes first
    would then have their new backslashes escaped in turn.
    """
    return text.replace("\\", "\\\\").replace('"', '\\"')
