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

import importlib
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._config import (
    resolve_fabro_bin,
    resolve_fabro_factory,
)

_COMMANDS_DIR = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
_FACTORY_BIN_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_factory_bin"
_FABRO_BIN_SHUTIL_WHICH = "livespec_orchestrator_beads_fabro.commands._fabro_bin.shutil.which"
_LEGACY_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"


def _write_config(*, cwd: Path, dispatcher: dict[str, object]) -> None:
    _ = (cwd / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
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
