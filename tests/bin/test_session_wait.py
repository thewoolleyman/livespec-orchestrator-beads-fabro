"""Per-wrapper coverage test for bin/session_wait.py."""

from __future__ import annotations

import runpy
import sys
import types
from collections.abc import Callable
from pathlib import Path

import pytest

_BIN_DIR = Path(__file__).resolve().parents[2] / ".claude-plugin" / "scripts" / "bin"


def _stub_module(*, name: str, **attrs: object) -> types.ModuleType:
    module = types.ModuleType(name)
    for attr, value in attrs.items():
        setattr(module, attr, value)
    return module


def test_session_wait_wrapper_threads_exit_code(
    wrapper_runner: Callable[[str, str, int], None],
) -> None:
    wrapper_runner(
        "session_wait.py",
        "livespec_orchestrator_beads_fabro.commands.session_wait",
        0,
    )


def test_session_wait_wrapper_demands_no_tenant_credential(
    *,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wait CLI opens no beads tenant, so it must not demand its password.

    Every other wrapper in this tree resolves `BEADS_DOLT_PASSWORD`, and one
    that demanded it here would re-exec through the governed project's
    credential wrapper — or fail closed when none is configured — for a
    command that never touches the tenant. The whole point of this host
    surface is that an ordinary session can call it while it waits, so the
    required set has to be empty rather than merely satisfiable.
    """
    # `get`, not `[...]`: a wrapper that passes no `required` at all is the
    # very defect under test, and indexing would report it as a KeyError
    # rather than as the credential demand it actually is.
    required: list[object] = []
    main_module = "livespec_orchestrator_beads_fabro.commands.session_wait"
    monkeypatch.setitem(
        sys.modules,
        "_bootstrap",
        _stub_module(
            name="_bootstrap",
            bootstrap=lambda **kwargs: required.append(kwargs.get("required", "<tenant-default>")),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        main_module,
        _stub_module(name=main_module, main=lambda: 0),
    )

    with pytest.raises(SystemExit) as excinfo:
        _ = runpy.run_path(str(_BIN_DIR / "session_wait.py"), run_name="__main__")

    assert excinfo.value.code == 0
    assert required == [()]
