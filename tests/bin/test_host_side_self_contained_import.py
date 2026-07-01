"""Regression guard: the host-side dispatcher import path is self-contained.

A flattened plugin-cache adopter host (and every fleet member that
consumes the orchestrator by *enabling the plugin*) has NO Python
site-packages for this plugin: there is no `uv sync` and no apt
`python3-typing-extensions`. Only `.claude-plugin/scripts/` and
`.claude-plugin/scripts/_vendor/` are on `sys.path`, exactly as
`bin/_bootstrap.bootstrap()` arranges them.

This test reproduces that environment faithfully — a `-S` (no-site)
subprocess on the *same* interpreter pytest runs under — invokes the
real bootstrap, and imports the host-side dispatcher surface. It
asserts the imports resolve with no `ModuleNotFoundError`, i.e. the
vendored `_vendor/` tree (not site-packages) satisfies every host-side
import. The guard exists because the dispatcher reaches
`typing_extensions.assert_never` (via `livespec_runtime.cross_repo.
resolve`) and `typing_extensions.override` (via the OTel receiver),
neither of which exists in stdlib `typing` on the Python 3.10 target —
so an unvendored dependency would silently re-enter via the dev venv
and only fail on a real cache install. Any future unvendored host-side
dependency trips this same guard.
"""

import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BIN_DIR = _REPO_ROOT / ".claude-plugin" / "scripts" / "bin"

# The host-side dispatcher import surface: the cross-repo resolver (the
# `assert_never` site), the OTel receiver (the `override` site), and the
# dispatcher module itself, which transitively imports both.
_HOST_SIDE_DISPATCHER_MODULES = (
    "livespec_runtime.cross_repo.resolve",
    "livespec_orchestrator_beads_fabro.commands._otel_receive",
    "livespec_orchestrator_beads_fabro.commands.dispatcher",
)

# Runs inside the `-S` child. argv[1] is bin/ (so `_bootstrap` resolves);
# argv[2:] are the modules to import. The real bootstrap puts scripts/ +
# scripts/_vendor/ on sys.path — nothing else. A ModuleNotFoundError
# (e.g. an unvendored typing_extensions) propagates as a non-zero exit.
_PROBE = """
import importlib
import sys

bin_dir = sys.argv[1]
if bin_dir not in sys.path:
    sys.path.insert(0, bin_dir)
import _bootstrap

_bootstrap.bootstrap()
for module_name in sys.argv[2:]:
    importlib.import_module(module_name)
"""


def test_host_side_dispatcher_imports_resolve_without_site_packages(
    tmp_path: Path,
) -> None:
    # `-S` disables site processing, so the interpreter's own (venv)
    # site-packages is excluded — the flattened-cache adopter condition.
    # Strip PYTHONPATH so no inherited path leaks site-packages back in;
    # run from an empty cwd so the implicit `-c` cwd entry masks nothing.
    # Per the `subprocess_spawn_allowlist` contract, scrub the coverage
    # subprocess hooks (COVERAGE_PROCESS_START + COV_CORE_*) so the child
    # does not self-instrument and race the parallel coverage runs.
    _scrubbed = ("PYTHONPATH", "COVERAGE_PROCESS_START")
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in _scrubbed and not key.startswith("COV_CORE_")
    }
    # The real `bootstrap()` now runs the credential self-heal, which requires
    # the tenant secret to be present (else it exits 3 before the imports run).
    # This guard is about import resolution, not credentials, so supply a
    # placeholder secret so the self-heal proceeds to the import phase.
    env["BEADS_DOLT_PASSWORD"] = "test-not-a-real-secret"
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            _PROBE,
            str(_BIN_DIR),
            *_HOST_SIDE_DISPATCHER_MODULES,
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        check=False,
    )
    assert result.returncode == 0, (
        "host-side dispatcher import path is NOT self-contained from the "
        "flattened plugin cache (scripts/ + scripts/_vendor/ on sys.path, "
        "no site-packages) — an unvendored dependency must be vendored "
        f"into .claude-plugin/scripts/_vendor/:\n{result.stderr}"
    )
