"""Public path-helper surface extracted from the Dispatcher."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Protocol, cast

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_paths
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult


class _RunnerLike(Protocol):
    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult: ...


class _RunnerFactory(Protocol):
    def __call__(self) -> _RunnerLike: ...


def test_dispatcher_paths_exports_promoted_public_helpers() -> None:
    assert _dispatcher_paths.__all__ == [
        # The launcher's installed-root record, public because
        # `test_installed_root_env_name_matches_the_launchers_writer_constant`
        # pins it against the writer's own constant across a module boundary.
        "INSTALLED_ROOT_ENV",
        "calibration_spans_path",
        "cost_report_spans_path",
        "cost_sink_path",
        "executing_payload_root",
        "heartbeat_path",
        "journal_path",
        "plugin_root",
        "reflector_oob_spans_path",
        "run_turn_sink_path",
        "spans_path",
        "state_root",
        "store_config",
        "tdd_order_sink_path",
        "workflow_toml",
    ]


def test_state_root_falls_back_to_the_home_local_state_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no `XDG_STATE_HOME`, the root is the freedesktop default under HOME.

    The suite sets `XDG_STATE_HOME` per test for hermeticity, so this arm needs
    its own control: without it the fallback would be dead code the suite never
    reaches while the real deploy path runs nothing else.
    """
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)

    assert _dispatcher_paths.state_root() == Path.home() / ".local" / "state"


def test_plugin_root_prefers_the_launchers_record_over_its_file_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With no harness export, the launcher's record names the installation.

    The end-to-end case lives in
    `tests/bin/test_payload_candidate_root_without_claude_env.py`, which spawns
    a real child through the real launcher — and must, because the question is
    what a SECOND process resolves after its code was copied aside. That child
    scrubs the coverage subprocess hooks as an allowlisted spawn has to, so this
    arm needs an in-process case too or the branch reads as dead code while the
    only path that exercises it is unmeasured.
    """
    install_root = tmp_path / "0123abc"
    install_root.mkdir()
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.setenv(_dispatcher_paths.INSTALLED_ROOT_ENV, str(install_root))

    assert _dispatcher_paths.plugin_root() == install_root


def test_an_exported_claude_plugin_root_outranks_the_launchers_record(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Precedence control: the harness export still wins where both are set."""
    exported = tmp_path / "exported"
    exported.mkdir()
    recorded = tmp_path / "recorded"
    recorded.mkdir()
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(exported))
    monkeypatch.setenv(_dispatcher_paths.INSTALLED_ROOT_ENV, str(recorded))

    assert _dispatcher_paths.plugin_root() == exported


def test_plugin_root_falls_back_to_its_own_tree_when_nothing_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unretained path: no export, no record, so walk up from `__file__`.

    This is what an in-repo CLI run and a source checkout both take, and it
    must stay the plugin root rather than becoming an error when the new
    record is absent.
    """
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv(_dispatcher_paths.INSTALLED_ROOT_ENV, raising=False)

    assert _dispatcher_paths.plugin_root().name == ".claude-plugin"


def test_installed_root_env_name_matches_the_launchers_writer_constant() -> None:
    """The reader's name and the launcher's WRITER name must be one string.

    `_dispatcher_paths` restates `INSTALLED_ROOT_ENV` rather than importing it:
    the writer is `bin/_payload.py`, a pre-import launcher module that runs
    before this package is on `sys.path`, so a dependency in either direction
    is wrong. That leaves two literals, and two literals drift — silently, in
    the direction that matters, because a reader looking for a name nobody
    writes just falls through to the `__file__` fall-through and resolves the
    PAYLOAD as the installed root, which is the whole defect.

    Pinned the same way the unattended-resume marker's writer and reader
    already are, by loading the launcher BY PATH so no import edge is created.
    """
    bin_dir = Path(__file__).resolve().parents[3] / ".claude-plugin" / "scripts" / "bin"
    launcher_path = bin_dir / "_payload.py"
    assert launcher_path.is_file(), f"the launcher is not where expected: {launcher_path}"
    if str(bin_dir) not in sys.path:
        sys.path.insert(0, str(bin_dir))
    _ = sys.modules.pop("_payload", None)
    launcher = importlib.import_module("_payload")

    assert _dispatcher_paths.INSTALLED_ROOT_ENV == launcher.INSTALLED_ROOT_ENV, (
        "the reader and the launcher disagree on the installed-root variable "
        "name, so the record is written under one name and read under another"
    )


def test_nf39_fake_runner_helper_is_covered(tmp_path: Path) -> None:
    test_path = Path(__file__).with_name("test_dispatcher_nf39.py")
    spec = importlib.util.spec_from_file_location("test_dispatcher_nf39_for_coverage", test_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    runner_factory = cast("_RunnerFactory", vars(module)["_FakeRunner"])
    runner = runner_factory()

    result = runner.run(argv=["gh"], cwd=tmp_path, timeout_seconds=1)

    assert isinstance(result, CommandResult)
    assert result.stdout == "{}"
