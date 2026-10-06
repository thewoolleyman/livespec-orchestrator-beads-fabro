"""Everything provisioning does belongs INSIDE the refusal boundary.

Three faults at the normal boundary, each measured before this file was
written, and each producing a traceback or a silently-disabled guard rather
than the actionable pre-claim refusal the rest of this module already gives:

- `tempfile.mkdtemp` ran OUTSIDE the handler, so an unusable temporary
  destination raised `NotADirectoryError` / `FileNotFoundError` straight out
  of the launcher. Measured: `NotADirectoryError: [Errno 20] Not a directory:
  '…/plugin.json/livespec-orchestrator-beads-fabro-payload-0.173.4-4pg2qe7t'`.
  Note `TMPDIR` CANNOT produce this — `tempfile` silently falls back through
  `/tmp`, `/var/tmp`, `/usr/tmp` and the cwd, so an unusable `TMPDIR` just
  lands the holder in `/tmp`. The destination has to be PINNED, which is what
  `tempfile.tempdir` does and what an embedder sets; that is the narrow
  control used below.
- The RAW manifest version text entered the holder's directory prefix. A
  version is only graded as a non-empty string, so `"../../escaped"` passes
  and reaches `mkdtemp` as path syntax. Measured: `FileNotFoundError: [Errno
  2] … '/tmp/…/tmp/livespec-orchestrator-beads-fabro-payload-../../escaped-w75tvr7m'`
  — a traceback here, and on a different parent layout a holder created
  OUTSIDE the temporary root entirely.
- `harness_managed` treated ANY adjacent `pyproject.toml` or `justfile` as
  proof of a source checkout. That is weaker than identifying THIS plugin's
  own checkout: an INSTALLED tree that merely happens to sit beside an
  unrelated project file had retention switched off and went back to
  executing an evictable source — silently, which is the direction that
  re-opens the bug. Measured: `harness_managed(<cache>/install) == False`
  with nothing but a stranger's `pyproject.toml` next to it.

The last case is proven end to end rather than by asking the predicate: the
installation is EVICTED mid-invocation and the child must still complete its
deferred import, which can only happen if retention really occurred.

The control at the end is what stops all of this from being "fixed" by
retaining everything: this repository's own checkout must still be exempt, so
the source-checkout policy, and the currency and canary behaviour that depend
on it, are preserved.

Real child processes are the only way to ask any of this, so this file is
listed in `pyproject.toml`'s `subprocess_spawn_allowlist` and scrubs the
coverage subprocess hooks exactly as an allowlisted spawn must.
"""

import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import IO, Any, cast

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLUGIN_ROOT = _REPO_ROOT / ".claude-plugin"
_BIN_DIR = _PLUGIN_ROOT / "scripts" / "bin"

_EXIT_PRECONDITION_ERROR = 3
_CLI_TIMEOUT_SECONDS = 300.0
_LAUNCHER_FINISHED = "launcher-finished"
_RELEASE_CHILD = "go\n"
_JOURNAL_RELPATH = ("tmp", "fabro-dispatch-journal.jsonl")

_RECORDER = """#!/bin/sh
printf '%s %s\\n' "$0" "$*" >> "$LIVESPEC_TEST_INVOCATION_RECORD"
exit 0
"""

# Completes the launcher, parks on stdin so the installation can be evicted,
# then does deferred work that only a retained payload can satisfy.
# Pins the temporary destination through the product's own `tempfile` seam and
# then runs the REAL `bin/dispatcher.py`. `TMPDIR` cannot stand in: `tempfile`
# falls back past an unusable one.
_PINNED_TEMPDIR_PROBE = """
import runpy
import sys
import tempfile
from pathlib import Path

destination, install_root, entry_point = sys.argv[1:4]
cli_args = sys.argv[4:]

sys.path.insert(0, str(Path(install_root) / "scripts" / "bin"))
tempfile.tempdir = destination

sys.argv = [entry_point, *cli_args]
runpy.run_path(entry_point, run_name="__main__")
"""

_EVICTION_PROBE = """
import importlib
import json
import sys
from pathlib import Path

install_root, result_path = sys.argv[1:3]

sys.path.insert(0, str(Path(install_root) / "scripts" / "bin"))
import _bootstrap

_bootstrap.bootstrap()

sys.stdout.write("launcher-finished\\n")
sys.stdout.flush()
_ = sys.stdin.readline()

drive = importlib.import_module("livespec_orchestrator_beads_fabro.commands.drive")
Path(result_path).write_text(
    json.dumps({"drive_file": drive.__file__}), encoding="utf-8"
)
"""


def _import_payload() -> Any:
    if str(_BIN_DIR) not in sys.path:
        sys.path.insert(0, str(_BIN_DIR))
    _ = sys.modules.pop("_payload", None)
    return importlib.import_module("_payload")


def _install(*, root: Path) -> Path:
    _ = shutil.copytree(_PLUGIN_ROOT, root, ignore=shutil.ignore_patterns("__pycache__"))
    return root


def _shims(*, shim_dir: Path) -> Path:
    shim_dir.mkdir(parents=True)
    for name in ("bd", "fabro"):
        executable = shim_dir / name
        _ = executable.write_text(_RECORDER, encoding="utf-8")
        executable.chmod(0o755)
    return shim_dir


def _target_repo(*, root: Path) -> Path:
    (root / ".beads").mkdir(parents=True)
    _ = (root / ".beads" / "config.yaml").write_text("dolt.mode: server\n", encoding="utf-8")
    _ = (root / ".livespec.jsonc").write_text("{}\n", encoding="utf-8")
    return root


def _base_env(*, install_root: Path, record: Path, shim_dir: Path) -> dict[str, str]:
    scrubbed = ("PYTHONPATH", "COVERAGE_PROCESS_START")
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in scrubbed and not key.startswith("COV_CORE_")
    }
    env["PATH"] = f"{shim_dir}{os.pathsep}{env.get('PATH', '')}"
    env["CLAUDE_PLUGIN_ROOT"] = str(install_root)
    env["LIVESPEC_TEST_INVOCATION_RECORD"] = str(record)
    env["BEADS_DOLT_PASSWORD"] = "test-not-a-real-secret"
    env["GITHUB_APP_ID"] = "000000"
    env["GITHUB_PRIVATE_KEY"] = "test-not-a-real-key"
    return env


def _run_dispatcher(*, install_root: Path, tmp_path: Path, temp_dir: Path):
    repo = _target_repo(root=tmp_path / "repo")
    record = tmp_path / "invocations.txt"
    env = _base_env(
        install_root=install_root, record=record, shim_dir=_shims(shim_dir=tmp_path / "shims")
    )
    env["TMPDIR"] = str(temp_dir)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            _PINNED_TEMPDIR_PROBE,
            str(temp_dir),
            str(install_root),
            str(install_root / "scripts" / "bin" / "dispatcher.py"),
            "ledger-check",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo),
        check=False,
        timeout=_CLI_TIMEOUT_SECONDS,
    )
    return completed, record, repo


def _assert_refused_cleanly(*, completed, record: Path, repo: Path) -> None:
    assert completed.returncode == _EXIT_PRECONDITION_ERROR, (
        "provisioning must refuse actionably rather than traceback:\n"
        f"exit={completed.returncode}\n{completed.stdout}\n{completed.stderr}"
    )
    assert (
        "Traceback" not in completed.stderr
    ), f"the launcher reported a traceback instead of a refusal:\n{completed.stderr}"
    assert (
        "refused" in completed.stderr
    ), f"the message is not an actionable refusal:\n{completed.stderr}"
    assert (
        not record.exists()
    ), f"the dispatch invoked bd/fabro before refusing:\n{record.read_text(encoding='utf-8')}"
    assert not repo.joinpath(*_JOURNAL_RELPATH).exists(), "the dispatch journaled before refusing"


@pytest.mark.parametrize("shape", ["a-file", "absent"])
def test_an_unusable_temporary_destination_is_refused_not_raised(
    tmp_path: Path, shape: str
) -> None:
    """`mkdtemp` must sit inside the handler, like every other provisioning step."""
    install_root = _install(root=tmp_path / "install")
    if shape == "a-file":
        temp_dir = tmp_path / "not-a-directory"
        _ = temp_dir.write_text("this is a file\n", encoding="utf-8")
    else:
        temp_dir = tmp_path / "never-created"

    completed, record, repo = _run_dispatcher(
        install_root=install_root, tmp_path=tmp_path, temp_dir=temp_dir
    )

    _assert_refused_cleanly(completed=completed, record=record, repo=repo)
    assert (
        str(temp_dir) in completed.stderr
    ), f"the refusal does not name the destination it could not use:\n{completed.stderr}"


@pytest.mark.parametrize(
    "version",
    [
        pytest.param("../../escaped", id="parent-traversal"),
        pytest.param("a/b", id="embedded-separator"),
        pytest.param(".", id="bare-dot"),
    ],
)
def test_a_path_like_release_version_is_refused_and_escapes_nothing(
    tmp_path: Path, version: str
) -> None:
    """Raw manifest text must never reach the holder's path as path SYNTAX."""
    install_root = _install(root=tmp_path / "install")
    _ = (install_root / "plugin.json").write_text(
        json.dumps({"version": version}), encoding="utf-8"
    )
    temp_dir = tmp_path / "tmpdir"
    temp_dir.mkdir()

    completed, record, repo = _run_dispatcher(
        install_root=install_root, tmp_path=tmp_path, temp_dir=temp_dir
    )

    _assert_refused_cleanly(completed=completed, record=record, repo=repo)
    assert list(temp_dir.iterdir()) == [], (
        f"a refused provision created something anyway: "
        f"{sorted(entry.name for entry in temp_dir.iterdir())}"
    )
    # Nothing may have been created beside the temporary root either, which is
    # where parent traversal in the prefix would land it. Asserted as "no
    # holder anywhere outside tmpdir" rather than as an exact sibling listing:
    # a clean refusal never creates the recorder file, so an exact listing
    # encodes a fixture detail rather than the property under test.
    assert not (tmp_path / "escaped").exists()
    strays = [
        entry
        for entry in tmp_path.rglob("livespec-orchestrator-beads-fabro-payload-*")
        if temp_dir not in entry.parents
    ]
    assert strays == [], f"a holder was created outside the temporary root: {strays}"


def test_an_installed_tree_beside_a_strangers_project_file_still_retains(
    tmp_path: Path,
) -> None:
    """An accidental neighbour must not switch execution back onto an evictable source.

    Proven by EVICTING the installation and requiring the deferred import to
    succeed anyway — asking the predicate would only report what it believes,
    not whether the run was actually protected.
    """
    cache = tmp_path / "cache"
    cache.mkdir()
    # A stranger's project file, of the kind that exempted the whole tree.
    _ = (cache / "pyproject.toml").write_text(
        '[project]\nname = "something-entirely-unrelated"\n', encoding="utf-8"
    )
    _ = (cache / "justfile").write_text("default:\n    @echo unrelated\n", encoding="utf-8")
    install_root = _install(root=cache / "install")
    result_path = tmp_path / "result.json"

    record = tmp_path / "invocations.txt"
    env = _base_env(
        install_root=install_root, record=record, shim_dir=_shims(shim_dir=tmp_path / "shims")
    )
    process = subprocess.Popen(
        [sys.executable, "-c", _EVICTION_PROBE, str(install_root), str(result_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(tmp_path),
    )
    handshake = cast("IO[str]", process.stdout).readline()
    shutil.rmtree(install_root)
    stdout, stderr = process.communicate(input=_RELEASE_CHILD, timeout=_CLI_TIMEOUT_SECONDS)

    assert (
        handshake.strip() == _LAUNCHER_FINISHED
    ), f"the launcher did not finish:\n{handshake}\n{stdout}\n{stderr}"
    assert not install_root.exists()
    assert process.returncode == 0, (
        "retention was disabled by an unrelated neighbouring project file, so "
        f"the invocation died with its evicted source:\n{stdout}\n{stderr}"
    )
    record_json = json.loads(result_path.read_text(encoding="utf-8"))
    assert not record_json["drive_file"].startswith(
        f"{install_root}{os.sep}"
    ), f"the deferred import resolved inside the evicted install: {record_json}"


def test_this_repositorys_own_checkout_is_still_exempt_from_retention() -> None:
    """The control: the fix must identify THIS checkout, not retain everything.

    Without this, every assertion above could be satisfied by retaining any
    tree at all — which would relocate a developer's working copy and discard
    the source-checkout policy the currency gate and the canary rely on.
    """
    payload = _import_payload()
    assert payload.harness_managed(source_root=_PLUGIN_ROOT) is False
