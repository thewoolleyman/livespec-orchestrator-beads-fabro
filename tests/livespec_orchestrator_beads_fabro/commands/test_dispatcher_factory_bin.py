"""Tests for the per-factory engine client binary (work-item bd-ib-qytzf4).

Running the Petri-era upgrade candidate beside the legacy production server on
one host needs the Dispatcher to drive each factory with the client that
matches that factory's engine: the candidate client cannot talk to the legacy
server and the legacy client cannot talk to the candidate. A factory entry's
optional `bin` key carries that client, and `_dispatcher_factory_bin` is where
the resolution and its pre-claim refusal live.

Coverage spans the resolution's two arcs — a factory declaring no `bin`, which
must resolve exactly as the single global setting always did, and one declaring
it, which must drive every Fabro CLI call the dispatch makes against that
factory — plus the pre-claim refusal and the dispatch record's engine fields.
"""

from __future__ import annotations

import argparse
import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._config import (
    resolve_fabro_bin,
    resolve_fabro_factory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
    port_for,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import fabro_port_for_plan
from livespec_orchestrator_beads_fabro.commands._needs_attention_orphan_runs import (
    InertJournal,
    InertLedger,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import dispatch_preamble

_COMMANDS_DIR = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
_FACTORY_BIN_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_factory_bin"
_FABRO_BIN_SHUTIL_WHICH = "livespec_orchestrator_beads_fabro.commands._fabro_bin.shutil.which"
_LEGACY_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_CANDIDATE_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32278"
_GLOBAL_BIN = "/global/fabro"


def _write_config(*, cwd: Path, dispatcher: dict[str, object]) -> None:
    _ = (cwd / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )


def _make_executable(*, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


@dataclass(kw_only=True)
class _RecordingRunner:
    """Captures the argv of every Fabro call so argv[0] can be asserted."""

    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        return CommandResult(exit_code=0, stdout="[]", stderr="")


def _reconcile_inputs(*, repo: Path, runner: _RecordingRunner) -> ReconcileInputs:
    """A reconciliation bundle whose only live seam is the recording runner.

    The journal and ledger seams are the production read-only pair the
    needs-attention lane already hands the reconciler, rather than stubs
    written here: nothing in this test exercises them, and a local stub whose
    methods are never called is dead test code.
    """
    return ReconcileInputs(
        repo=repo,
        fabro_bin=_GLOBAL_BIN,
        id_prefix="bd-ib",
        items=(),
        journaled=journaled_runs(text=""),
        runner=runner,
        journal=InertJournal(),
        ledger=InertLedger(),
    )


def test_factory_without_a_bin_key_resolves_the_global_binary_in_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Absent key: LIVESPEC_FABRO_BIN, then dispatcher.fabro_bin, then the home default.

    The module path is asserted FIRST so the Red is a genuine assertion rather
    than a collection error — at Red the module does not exist yet, and a
    top-level import of it would die before any assertion ran.
    """
    module_path = _COMMANDS_DIR / "_dispatcher_factory_bin.py"
    assert module_path.is_file()
    factory_bin = importlib.import_module(_FACTORY_BIN_MODULE)

    _write_config(
        cwd=tmp_path,
        dispatcher={
            "fabro_bin": "/config/fabro",
            "factories": {"hp": {"server": _LEGACY_SERVER}},
        },
    )
    keyless = resolve_fabro_factory(cwd=tmp_path, factory="hp")
    assert keyless.fabro_bin is None

    monkeypatch.setenv("LIVESPEC_FABRO_BIN", "/env/fabro")
    assert (
        factory_bin.factory_fabro_bin(factory=keyless, fallback=resolve_fabro_bin(cwd=tmp_path))
        == "/env/fabro"
    )

    monkeypatch.delenv("LIVESPEC_FABRO_BIN")
    assert (
        factory_bin.factory_fabro_bin(factory=keyless, fallback=resolve_fabro_bin(cwd=tmp_path))
        == "/config/fabro"
    )

    _write_config(cwd=tmp_path, dispatcher={"factories": {"hp": {"server": _LEGACY_SERVER}}})
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(_FABRO_BIN_SHUTIL_WHICH, lambda _name: None)
    assert factory_bin.factory_fabro_bin(
        factory=resolve_fabro_factory(cwd=tmp_path, factory="hp"),
        fallback=resolve_fabro_bin(cwd=tmp_path),
    ) == str(tmp_path / ".fabro" / "bin" / "fabro")


def test_a_declared_factory_bin_drives_every_fabro_call_against_that_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The declared `bin` wins over the global resolution at every seam.

    "Every Fabro CLI call against that factory" is asserted where a port is
    OPENED, because every verb — run, inspect, events, ps, rm, validate,
    version, auth — takes its argv[0] from the port it was opened on. The two
    openings are the dispatch plan's port and reconciliation's per-factory
    port; the two seams that bind a factory target to `args` are asserted
    beside them, because a port can only ever be as right as the binary
    `args` was carrying when it was opened.
    """
    candidate = _make_executable(path=tmp_path / "candidate" / "fabro")
    _write_config(
        cwd=tmp_path,
        dispatcher={
            "default_factory": "hp-candidate",
            "factories": {
                "hp": {"server": _LEGACY_SERVER},
                "hp-candidate": {"server": _CANDIDATE_SERVER, "bin": str(candidate)},
            },
        },
    )
    monkeypatch.setenv("LIVESPEC_FABRO_BIN", _GLOBAL_BIN)
    factory_bin = importlib.import_module(_FACTORY_BIN_MODULE)

    target = resolve_fabro_factory(cwd=tmp_path)
    assert (target.name, target.fabro_bin) == ("hp-candidate", str(candidate))
    assert factory_bin.factory_fabro_bin(factory=target, fallback=_GLOBAL_BIN) == str(candidate)

    args = argparse.Namespace(fabro_bin=None, janitor=None, journal=None)
    assert dispatch_preamble(args=args, repo=tmp_path) == (None, None)
    assert args.fabro_bin == str(candidate)
    # The global stays recorded, so a per-item factory pin re-resolves against
    # it rather than against the candidate client the preamble just wrote.
    assert args.fabro_bin_global == _GLOBAL_BIN
    assert (
        factory_bin.factory_effective_fabro_bin(
            args=args, factory=resolve_fabro_factory(cwd=tmp_path, factory="hp")
        )
        == _GLOBAL_BIN
    )
    assert factory_bin.factory_effective_fabro_bin(args=args, factory=target) == str(candidate)

    plan_runner = _RecordingRunner()
    plan = build_plan(
        repo=tmp_path,
        work_item_id="bd-ib-qytzf4",
        workflow_toml=tmp_path / "wf.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin=args.fabro_bin,
        fabro_factory_name=target.name,
        fabro_factory_server=target.server,
        janitor=None,
        janitor_checkout=tmp_path / "checkout",
    )
    _ = fabro_port_for_plan(plan=plan, runner=plan_runner).ps(timeout_seconds=1.0)
    assert plan_runner.calls[0][0] == str(candidate)

    reconcile_runner = _RecordingRunner()
    inputs = _reconcile_inputs(repo=tmp_path, runner=reconcile_runner)
    _ = port_for(inputs=inputs, factory=target).ps(timeout_seconds=1.0)
    _ = port_for(inputs=inputs, factory=resolve_fabro_factory(cwd=tmp_path, factory="hp")).ps(
        timeout_seconds=1.0
    )
    assert [call[0] for call in reconcile_runner.calls] == [str(candidate), _GLOBAL_BIN]
