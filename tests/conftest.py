"""Top-level fixtures shared across every test tree.

The dispatch path projects a freshness-gated snapshot of the host Codex
credential into the sandbox (scenarios.md Scenario 18 / 19), reading the
host `auth.json` under `$CODEX_HOME` (default `~/.codex`). EVERY test tree
that exercises a dispatch — the unit command tests under
`tests/livespec_orchestrator_beads_fabro/` AND the integration scenario
tests under `tests/integration/` — must therefore see a fresh, fake
credential rather than the real host one, so the suite is hermetic and
never depends on whether the runner is `codex login`'d (an unguarded read
of a missing `~/.codex` refuses the dispatch and fails every dispatch
test, which is exactly what happens on CI). This autouse fixture lives at
the top level so it reaches every subtree; it points `CODEX_HOME` at a
per-test scratch dir carrying a far-future-`exp` fake credential. Tests
asserting the missing/stale paths override it explicitly (delenv / point
at an empty dir / monkeypatch the read).
"""

from __future__ import annotations

import base64
import json
import shutil
import time
from pathlib import Path

import pytest


def _fresh_codex_auth_json() -> str:
    """A host Codex `auth.json` whose access-token JWT `exp` is a century out.

    A far-future `exp` keeps every dispatch test past the freshness gate
    against the real clock the dispatch path reads. The refresh token is a
    placeholder — `project_codex_auth_snapshot` replaces it with the inert
    sentinel before the snapshot reaches the overlay.
    """
    exp = int(time.time()) + 100 * 365 * 24 * 3600
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    access_token = f"header.{payload}.sig"
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": access_token,
                "refresh_token": "host-refresh-token",
                "id_token": "id-token-value",
                "account_id": "acct-123",
            },
        }
    )


@pytest.fixture(autouse=True)
def _hermetic_codex_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    codex_home = tmp_path_factory.mktemp("codex-home")
    _ = (codex_home / "auth.json").write_text(_fresh_codex_auth_json(), encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))


@pytest.fixture(autouse=True)
def _clear_dispatch_surface_bytecode(request: pytest.FixtureRequest) -> None:
    if request.node.path.name != "test_fleet_pat_dispatch_surface.py":
        return
    scripts_root = Path(__file__).resolve().parents[1] / ".claude-plugin" / "scripts"
    for cache_dir in scripts_root.rglob("__pycache__"):
        shutil.rmtree(cache_dir)


@pytest.fixture(scope="session")
def _fabro_stub_bin(tmp_path_factory: pytest.TempPathFactory) -> str:
    """A real, executable throwaway `fabro` binary shared across the suite.

    The Dispatcher preflight (`_fabro_preflight_error`) refuses BEFORE
    admission when the resolved `fabro` engine binary is not an existing
    executable. The real default is the host's `$HOME/.fabro/bin/fabro`, which
    is absent on CI — so without a hermetic override EVERY dispatch/loop test
    that omits an explicit `--fabro-bin` would refuse at preflight. This
    session-scoped stub is a genuine chmod-0o755 file so the preflight's
    is_file + X_OK check passes.
    """
    stub_dir = tmp_path_factory.mktemp("fabro-stub-bin")
    stub = stub_dir / "fabro"
    _ = stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)
    return str(stub)


@pytest.fixture(autouse=True)
def _hermetic_fabro_bin(monkeypatch: pytest.MonkeyPatch, _fabro_stub_bin: str) -> None:
    """Point `LIVESPEC_FABRO_BIN` at a resolvable stub for every test.

    Keeps the dispatch/loop suite hermetic against the new engine-binary
    preflight: dispatch/loop tests that omit `--fabro-bin` resolve to this
    absolute stub and pass preflight rather than refusing on a machine without
    the real `$HOME/.fabro/bin/fabro`. Tests asserting the refusal / default
    paths override it explicitly (an explicit `--fabro-bin`, or `delenv`).
    """
    monkeypatch.setenv("LIVESPEC_FABRO_BIN", _fabro_stub_bin)
