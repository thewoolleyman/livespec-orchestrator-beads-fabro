"""Tests for the host-side stall watchdog's configured window (bd-ib-3ugnfr).

`SPECIFICATION/contracts.md` section "ACP node timeouts" governs the run's
stall watchdog through the SAME layers as the per-node timeouts, and the
host-side watchdog used to ignore that key entirely: it read the environment
variable `LIVESPEC_DISPATCH_STALL_SECONDS` with a private 1500-second default,
so a configured `dispatcher.stall_timeout_seconds` governed the phase graph
while the host backstop cancelled against an unrelated number. Measured on
legacy hp run 01M4QGDETRJ3 (2026-10-12) that cost a run roughly four hours of
unpublished work.

The module import sits INSIDE each test body (the new-module pattern this
repo's decomposition slices use) so the Red commit fails on a genuine
assertion -- the module file's absence -- rather than at collection.
"""

from __future__ import annotations

import importlib
import threading
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_io_fabro_launcher,
    _dispatcher_stale_item_reap,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import WatchedFabroLauncher
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    REPOSITORY_LAYER,
    WORKFLOW_DEFAULT_LAYER,
)

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_stall_window"
_WATCHDOG_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog"

# The environment-only resolution this module replaces. Named here rather than
# imported, because the point of the assertion below is that none of these
# names exists any more.
_RETIRED_WATCHDOG_NAMES = (
    "DEFAULT_STALL_SECONDS",
    "STALL_SECONDS_ENV_VAR",
    "resolve_stall_seconds",
)

_WORK_ITEM_ID = "bd-ib-3ugnfr"
_RUN_ID = "01RUN"
_PS_RUNNING = (
    f'[{{"run_id": "{_RUN_ID}", "goal": "Work-item: {_WORK_ITEM_ID}",'
    ' "status": {"kind": "running"}}]'
)
# The listing above answers only the FIRST poll; once the run id is bound the
# watch loop reads it with `fabro inspect` instead (bd-ib-6pdigz).
_INSPECT_RUNNING = f'[{{"run_id": "{_RUN_ID}", "status": {{"kind": "running"}}}}]'
# One timestamp, repeated on every poll: the event stream has flatlined, which
# is the only condition `decide_stall` confirms a stall on.
_FROZEN_EVENTS = '[{"timestamp": "2026-10-12T11:28:00Z"}]'


def _module_path() -> Path:
    """Where the stall-window module lives, beside the launcher that reads it."""
    return Path(str(_dispatcher_io_fabro_launcher.__file__)).with_name(
        "_dispatcher_stall_window.py"
    )


def _stall_window_module() -> object:
    """The stall-window module, imported inside a test body rather than at top.

    The existence assertion LEADS the import so that every test here fails on
    a genuine assertion while the module is absent, rather than on a
    `ModuleNotFoundError` that would prove only unimportability.
    """
    assert _module_path().is_file()
    return importlib.import_module(_MODULE)


def _write_config(*, repo: Path, dispatcher_keys: str) -> None:
    """Write a `.livespec.jsonc` carrying a connection block and `dispatcher_keys`.

    The connection block is required rather than decorative: once the file
    exists the launcher's stale-item check resolves a store config from it.
    """
    _ = (repo / ".livespec.jsonc").write_text(
        "{\n"
        '  "livespec-orchestrator-beads-fabro": {\n'
        '    "connection": {"prefix": "bd-ib", "tenant": "t", "fake": true},\n'
        f'    "dispatcher": {{{dispatcher_keys}}}\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _ScriptedFabroRunner:
    """A CommandRunner scripting fabro's run/ps/inspect/events/rm subprocesses.

    `fabro run` BLOCKS on `run_done` so the background thread stays alive
    while the foreground watch loop runs; `fabro rm` sets it, modelling fabro
    killing the run. Never launches a real process.
    """

    events_jsons: list[str]
    run_done: threading.Event = field(default_factory=threading.Event)
    rm_calls: list[str] = field(default_factory=list)
    _poll: int = 0

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        _ = (cwd, timeout_seconds)
        verb = argv[1] if len(argv) > 1 else ""
        if verb == "run":
            _ = self.run_done.wait(timeout=10.0)
            return CommandResult(exit_code=0, stdout=f"    Run: {_RUN_ID}\n", stderr="")
        if verb == "ps":
            return CommandResult(exit_code=0, stdout=_PS_RUNNING, stderr="")
        if verb == "inspect":
            return CommandResult(exit_code=0, stdout=_INSPECT_RUNNING, stderr="")
        if verb == "events":
            index = min(self._poll, len(self.events_jsons) - 1)
            self._poll += 1
            return CommandResult(exit_code=0, stdout=self.events_jsons[index], stderr="")
        if verb == "rm":
            self.rm_calls.append(argv[-1])
            self.run_done.set()
            return CommandResult(exit_code=0, stdout="", stderr="")
        return CommandResult(exit_code=1, stdout="", stderr=f"unexpected argv {argv}")


def _advancing_clock() -> object:
    """A monotonic clock that jumps 600s per reading (one reading per poll)."""
    ticks = iter(float(tick) for tick in range(0, 6_000_000, 600))
    return lambda: next(ticks)


def _plan(*, repo: Path, stall_window: object) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id=_WORK_ITEM_ID,
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        stall_window=stall_window,
    )


def test_host_stall_watchdog_window_resolves_from_the_repository_stall_timeout_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The configured key governs the window the watchdog cancels against.

    End to end through the layers the node timeouts already use: the dispatch
    target's `.livespec.jsonc` declares 3000 seconds, the resolution reports
    that value and names the repository layer that supplied it, and the watch
    loop grades its confirmed quiet window against THAT number rather than
    against a literal of its own.
    """
    stall_window = _stall_window_module()
    _write_config(repo=tmp_path, dispatcher_keys='"stall_timeout_seconds": 3000')

    window = stall_window.resolve_stall_window(cwd=tmp_path)  # pyright: ignore[reportAttributeAccessIssue]

    assert (window.seconds, window.layer) == (3000.0, REPOSITORY_LAYER)

    monkeypatch.setattr(_dispatcher_stale_item_reap, "read_work_items", lambda **_: [])
    runner = _ScriptedFabroRunner(events_jsons=[_FROZEN_EVENTS])
    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(sleep=lambda _seconds: None, clock=_advancing_clock())

    result = launcher.launch(
        plan=_plan(repo=tmp_path, stall_window=window), runner=runner, journal=journal
    )

    assert result.stalled_run_id == _RUN_ID
    assert runner.rm_calls == [_RUN_ID]
    cancels = [r for r in journal.records if r.get("stage") == "watchdog-stall-cancel"]
    assert [record.get("stall_seconds") for record in cancels] == [3000.0]


def test_no_configured_value_leaves_the_host_stall_window_at_7200_seconds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A target configuring no stall timeout resolves the 7200-second default.

    Asserted together with the RETIREMENT of the environment-only resolution,
    because the two are one claim: while a second resolver with a private
    1500-second default survives in the tree, "the host stall window with no
    configured value" has two answers — and the two post-run surfaces that
    report which cap a bounce tripped still read the other one.
    """
    watchdog = importlib.import_module(_WATCHDOG_MODULE)

    surviving = [name for name in _RETIRED_WATCHDOG_NAMES if hasattr(watchdog, name)]

    assert surviving == []

    stall_window = _stall_window_module()
    # A dispatcher block that configures NODE timeouts and no stall timeout:
    # the block is present and read, so an absent window is a resolution
    # rather than an unread file.
    _write_config(repo=tmp_path, dispatcher_keys='"node_timeouts": {"implement": 14400}')
    window = stall_window.resolve_stall_window(cwd=tmp_path)  # pyright: ignore[reportAttributeAccessIssue]

    assert (window.seconds, window.layer) == (7200.0, WORKFLOW_DEFAULT_LAYER)

    monkeypatch.setattr(_dispatcher_stale_item_reap, "read_work_items", lambda **_: [])
    runner = _ScriptedFabroRunner(events_jsons=[_FROZEN_EVENTS])
    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(sleep=lambda _seconds: None, clock=_advancing_clock())

    result = launcher.launch(
        plan=_plan(repo=tmp_path, stall_window=window), runner=runner, journal=journal
    )

    assert result.stalled_run_id == _RUN_ID
    cancels = [r for r in journal.records if r.get("stage") == "watchdog-stall-cancel"]
    assert [record.get("stall_seconds") for record in cancels] == [7200.0]


def test_the_cancel_row_names_the_layer_that_supplied_the_stall_window(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A cancellation record says WHICH layer the window it graded came from.

    Driven twice, with a repository override and with the fleet default,
    because one arm alone is satisfied by a record carrying a constant — and a
    constant is exactly what this row would then be mistaken for. The layer is
    the first question asked of any cancellation: an operator who cannot tell
    an override from the built-in default cannot tell whether raising the key
    would have saved the run.
    """
    monkeypatch.setattr(_dispatcher_stale_item_reap, "read_work_items", lambda **_: [])
    stall_window = _stall_window_module()
    configured = tmp_path / "configured"
    defaulted = tmp_path / "defaulted"
    for repo, keys in ((configured, '"stall_timeout_seconds": 1800'), (defaulted, "")):
        repo.mkdir()
        _write_config(repo=repo, dispatcher_keys=keys)

    rows: list[dict[str, object]] = []
    for repo in (configured, defaulted):
        window = stall_window.resolve_stall_window(cwd=repo)  # pyright: ignore[reportAttributeAccessIssue]
        journal = _RecordingJournal()
        launcher = WatchedFabroLauncher(sleep=lambda _seconds: None, clock=_advancing_clock())
        result = launcher.launch(
            plan=_plan(repo=repo, stall_window=window),
            runner=_ScriptedFabroRunner(events_jsons=[_FROZEN_EVENTS]),
            journal=journal,
        )
        assert result.stalled_run_id == _RUN_ID
        rows.extend(r for r in journal.records if r.get("stage") == "watchdog-stall-cancel")

    assert [row.get("stall_layer") for row in rows] == [REPOSITORY_LAYER, WORKFLOW_DEFAULT_LAYER]
    assert [row.get("stall_seconds") for row in rows] == [1800.0, 7200.0]


def test_a_refused_stall_timeout_value_falls_soft_onto_the_default_window(
    tmp_path: Path,
) -> None:
    """A value the node-timeout validator refuses reports the default, not a crash.

    Zero seconds is refused — a window that fires instantly would disable the
    backstop by cancelling every run — and the refusal belongs to the
    dispatch-time validation that names the key before any run exists. The
    post-run reporting surfaces this resolution serves run after the verdict is
    already final, so a refusal raised here would crash an escalation write.
    """
    stall_window = _stall_window_module()
    _write_config(repo=tmp_path, dispatcher_keys='"stall_timeout_seconds": 0')

    assert stall_window.resolve_stall_window(cwd=tmp_path) == stall_window.DEFAULT_STALL_WINDOW  # pyright: ignore[reportAttributeAccessIssue]


def test_an_unreadable_config_falls_soft_onto_the_default_window(tmp_path: Path) -> None:
    """An unreadable `.livespec.jsonc` reports the default rather than raising.

    The second of the two fail-soft arms, and a distinct one: the refused value
    above comes back as a message on the success track, while an unparseable
    file raises out of the config reader.
    """
    stall_window = _stall_window_module()
    _ = (tmp_path / ".livespec.jsonc").write_text("{ not json at all", encoding="utf-8")

    assert stall_window.resolve_stall_window(cwd=tmp_path) == stall_window.DEFAULT_STALL_WINDOW  # pyright: ignore[reportAttributeAccessIssue]


def test_the_scripted_runner_rejects_a_verb_the_launcher_never_issues(tmp_path: Path) -> None:
    """Exercise the fake's defensive fallback directly.

    The launcher issues exactly four verbs; anything else means the fake is
    standing in for a call it was never written to model, so it reports a
    failure rather than a plausible success.
    """
    runner = _ScriptedFabroRunner(events_jsons=["[]"])

    bogus = runner.run(argv=["fabro", "bogus"], cwd=tmp_path, timeout_seconds=1.0)
    verbless = runner.run(argv=["fabro"], cwd=tmp_path, timeout_seconds=1.0)

    assert (bogus.exit_code, verbless.exit_code) == (1, 1)
