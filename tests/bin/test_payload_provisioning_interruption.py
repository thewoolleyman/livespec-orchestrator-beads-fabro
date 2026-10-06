"""A provision that is INTERRUPTED, or whose source vanishes under it, leaves nothing.

`test_payload_provisioning_refusal.py` is the accepted Red for the refusal
itself, and its second case uses a dangling symlink. That is a real copy
ERROR, and it is worth having — but it is NOT a source disappearing during
provisioning and NOT an interrupted provision, and that file's own prose
overclaims it as "the same shape". This file covers the two literal cases
instead, and neither is reachable by making a copy fail up front:

- the source tree is deleted WHILE the real `shutil.copytree` is walking it,
  so the copy fails part-way through a tree it had already begun writing;
- the provision is INTERRUPTED — the shape a `SIGINT` or a `SIGTERM` produces,
  which arrives as `KeyboardInterrupt`/`SystemExit` rather than as `OSError`,
  so a handler enumerating filesystem errors never sees it and the private
  directory survives as a half-copied tree a later invocation could adopt.

It also closes the gap the refusal file leaves on its FIRST case: an
incomplete source refuses, but nothing there asserts that no private
directory was created.

Every case drives the real packaged Dispatcher entry point in a real child
process and observes the absence of the side effects a claim would leave —
`bd` and `fabro` replaced on `PATH` by recorders that must never be called,
no dispatch journal, and `TMPDIR` empty afterwards. The disappearance and the
interruption are each introduced through ONE narrow control on the product's
own seam inside that child (`shutil.ignore_patterns`, which `_payload` calls,
and `shutil.copytree` itself), because neither can be made deterministic from
outside the copy: a wall-clock race would pass or fail on load.

Real child processes are the only way to ask this, so this file is listed in
`pyproject.toml`'s `subprocess_spawn_allowlist` and scrubs the coverage
subprocess hooks exactly as an allowlisted spawn must.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLUGIN_ROOT = _REPO_ROOT / ".claude-plugin"

_EXIT_PRECONDITION_ERROR = 3
_CLI_TIMEOUT_SECONDS = 300.0
_VENDOR_RELPATH = ("scripts", "_vendor")
_JOURNAL_RELPATH = ("tmp", "fabro-dispatch-journal.jsonl")

_RECORDER = """#!/bin/sh
printf '%s %s\\n' "$0" "$*" >> "$LIVESPEC_TEST_INVOCATION_RECORD"
exit 0
"""

# Runs the REAL `bin/dispatcher.py` through `runpy`, after applying one narrow
# control to the product seam named in argv. `runpy.run_path` executes the
# shipped wrapper exactly as the shell would, so the entry point under test is
# the real one; the control only decides what the copy encounters.
#
# `vanish` deletes a subtree of the SOURCE from inside the real `copytree`
# walk — `ignore_patterns` is called once per directory visited, so the
# deletion lands after the copy has started and after it has already written
# part of the destination.
#
# `interrupt` writes a partial tree and then raises `KeyboardInterrupt`, which
# is what a `SIGINT` delivers mid-provision.
_PROBE = """
import runpy
import shutil
import sys
from pathlib import Path

mode, install_root, entry_point = sys.argv[1:4]
cli_args = sys.argv[4:]

sys.path.insert(0, str(Path(install_root) / "scripts" / "bin"))
import _payload

if mode == "vanish":
    real_ignore = shutil.ignore_patterns
    state = {"fired": False}

    def _vanishing_ignore(*names):
        inner = real_ignore(*names)

        def _ignore(directory, entries):
            if not state["fired"]:
                state["fired"] = True
                shutil.rmtree(Path(install_root) / "scripts" / "_vendor")
            return inner(directory, entries)

        return _ignore

    _payload.shutil.ignore_patterns = _vanishing_ignore

if mode == "interrupt":
    def _interrupted_copytree(source, destination, **kwargs):
        Path(destination).mkdir(parents=True)
        (Path(destination) / "plugin.json").write_text("{}", encoding="utf-8")
        raise KeyboardInterrupt("provision interrupted")

    _payload.shutil.copytree = _interrupted_copytree

sys.argv = [entry_point, *cli_args]
runpy.run_path(entry_point, run_name="__main__")
"""


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


def _dispatch_repo(*, root: Path) -> Path:
    (root / ".beads").mkdir(parents=True)
    _ = (root / ".beads" / "config.yaml").write_text("dolt.mode: server\n", encoding="utf-8")
    _ = (root / ".livespec.jsonc").write_text("{}\n", encoding="utf-8")
    return root


def _run(*, mode: str, install_root: Path, tmp_path: Path):
    """Run the real Dispatcher entry point with one narrow control applied."""
    repo = _dispatch_repo(root=tmp_path / "repo")
    tmp_root = tmp_path / "tmpdir"
    tmp_root.mkdir()
    record = tmp_path / "invocations.txt"
    shim_dir = _shims(shim_dir=tmp_path / "shims")

    scrubbed = ("PYTHONPATH", "COVERAGE_PROCESS_START")
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in scrubbed and not key.startswith("COV_CORE_")
    }
    env["PATH"] = f"{shim_dir}{os.pathsep}{env.get('PATH', '')}"
    env["TMPDIR"] = str(tmp_root)
    env["CLAUDE_PLUGIN_ROOT"] = str(install_root)
    env["LIVESPEC_TEST_INVOCATION_RECORD"] = str(record)
    env["BEADS_DOLT_PASSWORD"] = "test-not-a-real-secret"
    env["GITHUB_APP_ID"] = "000000"
    env["GITHUB_PRIVATE_KEY"] = "test-not-a-real-key"

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            _PROBE,
            mode,
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
    return completed, tmp_root, record, repo


def _assert_no_claim_or_run(*, record: Path, repo: Path) -> None:
    assert (
        not record.exists()
    ), f"the dispatch invoked bd/fabro before refusing:\n{record.read_text(encoding='utf-8')}"
    assert not repo.joinpath(*_JOURNAL_RELPATH).exists(), "the dispatch journaled before refusing"


def test_a_source_that_vanishes_during_provisioning_refuses_and_cleans_up(
    tmp_path: Path,
) -> None:
    """The literal disappearance case: the source goes while the copy is walking it."""
    install_root = _install(root=tmp_path / "install")

    completed, tmp_root, record, repo = _run(
        mode="vanish", install_root=install_root, tmp_path=tmp_path
    )

    assert not install_root.joinpath(*_VENDOR_RELPATH).exists(), (
        "the control did not actually remove the source subtree, so no "
        "disappearance was exercised"
    )
    assert completed.returncode == _EXIT_PRECONDITION_ERROR, (
        "a source that vanished mid-provision must produce a precondition "
        f"refusal:\nexit={completed.returncode}\n{completed.stdout}\n{completed.stderr}"
    )
    assert (
        str(install_root) in completed.stderr
    ), f"the refusal does not name the installation it refused:\n{completed.stderr}"
    assert list(tmp_root.iterdir()) == [], (
        "the vanished-source provision left a partial payload a later "
        f"invocation could adopt: {sorted(p.name for p in tmp_root.iterdir())}"
    )
    _assert_no_claim_or_run(record=record, repo=repo)


def test_an_interrupted_provision_leaves_no_adoptable_payload(tmp_path: Path) -> None:
    """The literal interruption case: `SIGINT` arrives mid-copy.

    An interrupt is not an `OSError`, so a handler that enumerates filesystem
    failures never sees it. What must still hold is that the private directory
    does not survive as a half-copied tree — the launcher is the only thing
    that knows the tree is incomplete, and once it exits the directory is
    indistinguishable from a finished payload.
    """
    install_root = _install(root=tmp_path / "install")

    completed, tmp_root, record, repo = _run(
        mode="interrupt", install_root=install_root, tmp_path=tmp_path
    )

    assert (
        completed.returncode != 0
    ), f"an interrupted provision must not report success:\n{completed.stdout}"
    assert list(tmp_root.iterdir()) == [], (
        "the interrupted provision left its private directory behind as a "
        f"half-copied tree: {sorted(p.name for p in tmp_root.iterdir())}"
    )
    _assert_no_claim_or_run(record=record, repo=repo)


def test_an_incomplete_source_creates_no_private_directory_at_all(tmp_path: Path) -> None:
    """The refusal file's first case asserts the refusal but not this.

    A source graded incomplete is refused BEFORE anything is copied, so the
    correct observation is not "the directory was cleaned up" but "no private
    directory was ever created".
    """
    install_root = _install(root=tmp_path / "install")
    shutil.rmtree(install_root.joinpath(*_VENDOR_RELPATH))

    completed, tmp_root, record, repo = _run(
        mode="none", install_root=install_root, tmp_path=tmp_path
    )

    assert (
        completed.returncode == _EXIT_PRECONDITION_ERROR
    ), f"an incomplete source must refuse:\n{completed.stdout}\n{completed.stderr}"
    assert (
        "_vendor" in completed.stderr
    ), f"the refusal does not name what is missing:\n{completed.stderr}"
    assert list(tmp_root.iterdir()) == [], (
        "a source refused as incomplete still created a private directory: "
        f"{sorted(p.name for p in tmp_root.iterdir())}"
    )
    _assert_no_claim_or_run(record=record, repo=repo)
