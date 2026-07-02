"""Shared fixtures for tests/bin/.

Provides `wrapper_runner` — a callable that exec()'s a shebang
wrapper file with stubbed `_bootstrap` + stubbed
`livespec_orchestrator_beads_fabro.<module>.main` + an expected exit code,
asserts the wrapper raises `SystemExit` with that code.
"""

import runpy
import sys
import types
from collections.abc import Callable
from pathlib import Path

import pytest

_BIN_DIR = Path(__file__).resolve().parents[2] / ".claude-plugin" / "scripts" / "bin"


def _stub_module(*, name: str, **attrs: object) -> types.ModuleType:
    module = types.ModuleType(name)
    for attr_name, attr_value in attrs.items():
        setattr(module, attr_name, attr_value)
    return module


@pytest.fixture
def wrapper_runner(*, monkeypatch: pytest.MonkeyPatch) -> Callable[[str, str, int], None]:
    """Return `(wrapper_filename, main_module, expected_exit) -> None`."""

    def _run(wrapper_filename: str, main_module: str, expected_exit: int) -> None:
        wrapper_path = _BIN_DIR / wrapper_filename
        # `**_kwargs` so wrappers that pass `extra_required=...` (the
        # Dispatcher's GitHub App env) run against the same stub.
        monkeypatch.setitem(
            sys.modules,
            "_bootstrap",
            _stub_module(name="_bootstrap", bootstrap=lambda **_kwargs: None),
        )
        monkeypatch.setitem(
            sys.modules,
            main_module,
            _stub_module(name=main_module, main=lambda: expected_exit),
        )
        with pytest.raises(SystemExit) as excinfo:
            runpy.run_path(str(wrapper_path), run_name="__main__")
        assert excinfo.value.code == expected_exit

    return _run
