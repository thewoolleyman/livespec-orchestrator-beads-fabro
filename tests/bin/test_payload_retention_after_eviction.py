"""Regression guard: one retained payload survives plugin-cache eviction mid-invocation.

The host incident this guards (work-item `bd-ib-mtuqxb`): PID 1894716 was
still running an installed Codex cache's `scripts/bin/drive.py` while that
cache directory had already disappeared, and `bd-ib-3ftj` records the real
`_dispatcher_cost_wave` `ModuleNotFoundError` that shape produces. A plugin
launcher that leaves `sys.path` and `CLAUDE_PLUGIN_ROOT` pointing INTO the
harness-managed cache loses its deferred code, its packaged assets and its
`scripts/bin/` helpers the moment the harness evicts that cache — hours into
a dispatch, long after any startup-completeness check has passed.

This test reproduces the eviction faithfully rather than simulating it. It
copies the real plugin root into a DISPOSABLE fixture installation, launches
a real child process that calls the real `bin/_bootstrap.bootstrap()` from
that installation, waits for the child to signal that the launcher finished,
then DELETES the whole fixture installation. Only then does it release the
child to do the deferred work an invocation does hours in:

- import the packaged drive implementation route
  (`livespec_orchestrator_beads_fabro.commands.drive`) and the packaged
  Dispatcher entry route (`...commands.dispatcher`) for the first time;
- read a packaged asset through the public bundled-workflow resolution
  (`_dispatcher_paths.workflow_toml`);
- execute a `scripts/bin/` helper as a real subprocess.

Nothing here is importable in-process: the question is definitionally about
what a SECOND process sees after its source tree is gone, so the spawn is
listed in `pyproject.toml`'s `subprocess_spawn_allowlist` and scrubs the
coverage subprocess hooks exactly as an allowlisted spawn must.
"""

import json
import os
import select
import shutil
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLUGIN_ROOT = _REPO_ROOT / ".claude-plugin"

# Failure bounds, never assertions: how long the parent blocks for the child's
# startup handshake, and how long it then allows the deferred work to finish. A
# wedged child fails the test instead of hanging the suite.
_HANDSHAKE_TIMEOUT_SECONDS = 120.0
_DEFERRED_TIMEOUT_SECONDS = 180.0

# Runs inside the spawned child. argv is
# [install_root, ready_fd, go_fd, result_path]: the child WRITES a byte down the
# ready pipe once the launcher has finished, then BLOCKS reading the go pipe
# until the parent has deleted the installation.
#
# The launcher under test is `bin/_bootstrap.bootstrap()` — the one chokepoint
# every `bin/*.py` wrapper calls before any packaged import. Everything after
# the handshake is DEFERRED work: none of these modules, assets or helpers has
# been touched while the fixture installation still existed.
_PROBE = """
import argparse
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

install_root, ready_fd, go_fd, result_path = sys.argv[1:5]

bin_dir = str(Path(install_root) / "scripts" / "bin")
if bin_dir not in sys.path:
    sys.path.insert(0, bin_dir)
import _bootstrap

_bootstrap.bootstrap()

os.write(int(ready_fd), b"ready")
if not os.read(int(go_fd), 1):
    raise SystemExit("the parent closed the eviction handshake without releasing the child")

drive = importlib.import_module("livespec_orchestrator_beads_fabro.commands.drive")
dispatcher = importlib.import_module("livespec_orchestrator_beads_fabro.commands.dispatcher")
paths = importlib.import_module(
    "livespec_orchestrator_beads_fabro.commands._dispatcher_paths"
)

manifest = paths.workflow_toml(args=argparse.Namespace(workflow=None))
manifest_text = manifest.read_text(encoding="utf-8")

helper = Path(drive.__file__).resolve().parents[2] / "bin" / "next.py"
completed = subprocess.run(
    [sys.executable, str(helper), "--help"],
    capture_output=True,
    text=True,
    check=False,
)

Path(result_path).write_text(
    json.dumps(
        {
            "drive_file": drive.__file__,
            "dispatcher_file": dispatcher.__file__,
            "manifest": str(manifest),
            "manifest_length": len(manifest_text),
            "helper": str(helper),
            "helper_returncode": completed.returncode,
            "helper_stdout_length": len(completed.stdout),
        }
    ),
    encoding="utf-8",
)
"""


def _child_env(*, install_root: Path) -> dict[str, str]:
    """The child's environment: the fixture installation as the plugin cache.

    `CLAUDE_PLUGIN_ROOT` is what a native plugin install exports, so the
    fixture sets it to the disposable installation — the tree this test
    deletes mid-invocation. The coverage subprocess hooks are scrubbed per
    the `subprocess_spawn_allowlist` contract, `PYTHONPATH` so no inherited
    path leaks the repo's own tree back in, and a placeholder tenant secret
    keeps the credential self-heal on its `Proceed` arm (this guard is about
    payload lifetime, not credentials).
    """
    scrubbed = ("PYTHONPATH", "COVERAGE_PROCESS_START")
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in scrubbed and not key.startswith("COV_CORE_")
    }
    env["CLAUDE_PLUGIN_ROOT"] = str(install_root)
    env["BEADS_DOLT_PASSWORD"] = "test-not-a-real-secret"
    return env


def _wait_for(*, ready_fd: int, timeout: float, process: subprocess.Popen[str]) -> None:
    """Block until the child signals readiness down `ready_fd`, or fail.

    The signal is a byte the child writes into a pipe, so the wait is a single
    blocking `select` on that pipe: nothing is polled and no clock is read. A
    child that DIES closes its end of the pipe, which this side reads as EOF,
    so an early exit is reported as the child's own output rather than as a
    timeout. The `timeout` is only the bound that keeps a silent child from
    hanging the suite.
    """
    readable, _, _ = select.select([ready_fd], [], [], timeout)
    if not readable:
        raise AssertionError(f"timed out after {timeout}s waiting for the child's readiness signal")
    if not os.read(ready_fd, 16):
        stdout, stderr = process.communicate(timeout=timeout)
        message = f"child exited early (rc={process.returncode})\n{stdout}\n{stderr}"
        raise AssertionError(message)


def _launch_probe(
    *, install_root: Path, result_path: Path, cwd: Path
) -> tuple[subprocess.Popen[str], int, int]:
    """Start the probe child; return it with this side's ends of the two handshake pipes.

    The child's ends are closed here once it has them, so a child that dies
    closes the last copy of its write end and the parent reads EOF.
    """
    ready_read, ready_write = os.pipe()
    go_read, go_write = os.pipe()
    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                _PROBE,
                str(install_root),
                str(ready_write),
                str(go_read),
                str(result_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=_child_env(install_root=install_root),
            cwd=str(cwd),
            pass_fds=(ready_write, go_read),
        )
    finally:
        os.close(ready_write)
        os.close(go_read)
    return process, ready_read, go_write


def test_deferred_work_runs_from_the_retained_payload_after_the_install_is_removed(
    tmp_path: Path,
) -> None:
    install_root = tmp_path / "install"
    shutil.copytree(_PLUGIN_ROOT, install_root, ignore=shutil.ignore_patterns("__pycache__"))
    result_path = tmp_path / "result.json"
    process, ready_read, go_write = _launch_probe(
        install_root=install_root, result_path=result_path, cwd=tmp_path
    )
    try:
        _wait_for(ready_fd=ready_read, timeout=_HANDSHAKE_TIMEOUT_SECONDS, process=process)
        shutil.rmtree(install_root)
        assert not install_root.exists(), "the fixture installation was not actually removed"
        _ = os.write(go_write, b"go")
        stdout, stderr = process.communicate(timeout=_DEFERRED_TIMEOUT_SECONDS)
    finally:
        os.close(ready_read)
        os.close(go_write)
        if process.poll() is None:
            process.kill()
            _ = process.communicate()

    assert process.returncode == 0, (
        "deferred work did NOT complete after the plugin installation was removed "
        "mid-invocation — the launcher left this process depending on the evicted "
        f"cache instead of retaining its own complete payload:\n{stdout}\n{stderr}"
    )
    record = json.loads(result_path.read_text(encoding="utf-8"))
    assert not record["drive_file"].startswith(
        f"{install_root}{os.sep}"
    ), f"the drive implementation was imported from the removed install: {record}"
    assert not record["dispatcher_file"].startswith(
        f"{install_root}{os.sep}"
    ), f"the Dispatcher entry route was imported from the removed install: {record}"
    assert record["manifest_length"] > 0, f"the packaged workflow asset read empty: {record}"
    assert (
        record["helper_returncode"] == 0
    ), f"the scripts/bin helper subprocess did not run from the payload: {record}"
    assert record["helper_stdout_length"] > 0, f"the helper produced no output: {record}"
