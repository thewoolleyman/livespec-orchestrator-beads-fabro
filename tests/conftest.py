"""Top-level fixtures shared across every test tree.

These fixtures exist for one reason: the suite must answer the same way on
every machine it runs on. Each one replaces an AMBIENT host dependency the
dispatch path would otherwise read — the host Codex credential, the host
`fabro` engine binary, the host `gh` — with a hermetic stand-in, so the
suite never depends on whether the runner is logged in, has the engine
installed, or ships `gh` on the step-subprocess PATH.

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
import os
import shutil
import time
from dataclasses import dataclass
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


GH_STUB_EXIT_ENV = "LIVESPEC_TEST_GH_EXIT"
GH_STUB_STDOUT_ENV = "LIVESPEC_TEST_GH_STDOUT"
GH_STUB_LOG_ENV = "LIVESPEC_TEST_GH_LOG"

# A real, executable `gh` stand-in. It never touches the network: it records
# its argv when asked, replays a scripted stdout, and exits a scripted code
# (default 1 — the "no observable PR" answer the real `gh` gives in the
# throwaway repos the dispatch tests build).
_GH_STUB_SOURCE = f"""#!/bin/sh
if [ -n "${{{GH_STUB_LOG_ENV}:-}}" ]; then
  printf '%s\\n' "$*" >> "${GH_STUB_LOG_ENV}"
fi
if [ -n "${{{GH_STUB_STDOUT_ENV}:-}}" ]; then
  printf '%s' "${GH_STUB_STDOUT_ENV}"
fi
exit "${{{GH_STUB_EXIT_ENV}:-1}}"
"""


@pytest.fixture(scope="session")
def _gh_stub_bin(tmp_path_factory: pytest.TempPathFactory) -> str:
    """A real, executable throwaway `gh` shared across the suite.

    Several production paths shell out to `gh` through the REAL
    `ShellCommandRunner` rather than an injected one — the post-verdict
    self-update's `resolve_merged_paths` (`gh pr view <branch> --json
    files`), the janitor's `gh repo view`, the reflector's `gh pr create`,
    the fleet-manifest fetch. Letting those reach the host's `gh` makes the
    suite non-hermetic (an ambient login, a real network call, and an
    answer that differs per machine); letting them reach NO `gh` at all
    used to crash the dispatch outright. This stub removes both: it is a
    genuine chmod-0o755 file at the head of PATH, so `subprocess.run`
    resolves it and the runner's real spawn path is still exercised.
    """
    stub_dir = tmp_path_factory.mktemp("gh-stub-bin")
    stub = stub_dir / "gh"
    _ = stub.write_text(_GH_STUB_SOURCE, encoding="utf-8")
    stub.chmod(0o755)
    return str(stub_dir)


@pytest.fixture(autouse=True)
def _hermetic_gh_bin(monkeypatch: pytest.MonkeyPatch, _gh_stub_bin: str) -> None:
    """Shadow any host `gh` with the scriptable stub for EVERY test.

    Prepending the stub dir to PATH reaches every caller uniformly — the
    injected-runner unit tier and the production-runner dispatch tiers
    alike — so no test depends on whether the runner image ships `gh`.
    Tests drive a specific `gh` outcome by setting `LIVESPEC_TEST_GH_EXIT`
    / `LIVESPEC_TEST_GH_STDOUT`, or assert the argv by pointing
    `LIVESPEC_TEST_GH_LOG` at a scratch file; the absent-`gh` path is
    driven by putting a PATH with no `gh` on it back in place.
    """
    monkeypatch.setenv("PATH", f"{_gh_stub_bin}{os.pathsep}{os.environ['PATH']}")
    for name in (GH_STUB_EXIT_ENV, GH_STUB_STDOUT_ENV, GH_STUB_LOG_ENV):
        monkeypatch.delenv(name, raising=False)


@dataclass(frozen=True, kw_only=True)
class ScriptedGh:
    """Control surface for the hermetic `gh` stand-in, handed to a test.

    Keeps the stub's env contract in ONE place: a test scripts an outcome
    with `script(...)` and reads back the argvs the code under test
    actually spawned with `argv_lines()`, instead of restating the
    `LIVESPEC_TEST_GH_*` variable names and risking drift from the stub.
    """

    monkeypatch: pytest.MonkeyPatch
    log_path: Path

    def script(self, *, exit_code: int, stdout: str = "") -> None:
        """Make every later `gh` call exit `exit_code` and print `stdout`."""
        self.monkeypatch.setenv(GH_STUB_EXIT_ENV, str(exit_code))
        self.monkeypatch.setenv(GH_STUB_STDOUT_ENV, stdout)

    def argv_lines(self) -> list[str]:
        """Every `gh` argv spawned so far, one space-joined line each."""
        return self.log_path.read_text(encoding="utf-8").splitlines()


@pytest.fixture
def scripted_gh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ScriptedGh:
    """Script the PATH `gh` stub and capture the argvs it is called with."""
    log_path = tmp_path / "gh-argv.log"
    log_path.touch()
    monkeypatch.setenv(GH_STUB_LOG_ENV, str(log_path))
    return ScriptedGh(monkeypatch=monkeypatch, log_path=log_path)


@pytest.fixture
def absent_gh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Put a PATH carrying NO `gh` at all in place (the baked-image shape).

    The fabro-sandbox image resolves `gh` through a mise shim that is not
    on the step-subprocess PATH, so production code there spawns an
    executable that does not exist. This fixture reproduces exactly that.
    """
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))


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
