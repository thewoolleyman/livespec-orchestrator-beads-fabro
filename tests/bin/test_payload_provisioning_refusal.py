"""An unusable source payload is REFUSED before the Dispatcher claims anything.

Retention copies the installed release aside before any application import. If
that source is incomplete, or the copy fails part-way through, the launcher has
two jobs and the second is the one that matters: say so ACTIONABLY, and make
sure nothing irreversible has happened yet. A dispatch that gets far enough to
claim a work item or start a factory run and THEN discovers its own payload is
unusable has stranded that item — which is the whole cost the retention is
meant to avoid, re-introduced at a different point.

So both cases below drive the real packaged Dispatcher entry point,
`bin/dispatcher.py`, through a real child process, and observe the absence of
every side effect a claim would leave:

- `bd` and `fabro` are replaced on `PATH` by recorders that append to a file.
  The file must not exist: not "no claim was committed", but "the ledger and
  the factory were never even invoked".
- The dispatch journal (`<repo>/tmp/fabro-dispatch-journal.jsonl`) must not
  exist.
- `TMPDIR` points at a test-owned directory, which must be EMPTY afterwards:
  an interrupted provision that leaves a half-copied tree behind is a payload
  a later invocation could mistake for usable.

The credential env is fully supplied, so the only refusal that can fire is the
payload one — a refusal reached for the wrong reason would prove nothing.

Real child processes are the only way to ask this (the question is what a
packaged CLI does before it claims), so this file is listed in
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

# Stand-ins for the two executables a dispatch reaches for. Each records that
# it was invoked at all, which is the side effect under observation.
_RECORDER = """#!/bin/sh
printf '%s %s\\n' "$0" "$*" >> "$LIVESPEC_TEST_INVOCATION_RECORD"
exit 0
"""


def _install(*, root: Path) -> Path:
    _ = shutil.copytree(_PLUGIN_ROOT, root, ignore=shutil.ignore_patterns("__pycache__"))
    return root


def _shim_path(*, shim_dir: Path, record: Path) -> Path:
    """A `PATH` directory whose `bd` and `fabro` only record being called."""
    shim_dir.mkdir(parents=True)
    for name in ("bd", "fabro"):
        executable = shim_dir / name
        _ = executable.write_text(_RECORDER, encoding="utf-8")
        executable.chmod(0o755)
    _ = record  # the recorders read the destination from the environment
    return shim_dir


def _dispatch_repo(*, root: Path) -> Path:
    """A dispatch target just complete enough for the CLI to accept `--repo`."""
    (root / ".beads").mkdir(parents=True)
    _ = (root / ".beads" / "config.yaml").write_text("dolt:\n  mode: server\n", encoding="utf-8")
    _ = (root / ".livespec.jsonc").write_text("{}\n", encoding="utf-8")
    return root


def _run_dispatcher(*, install_root: Path, repo: Path, tmp_root: Path, record: Path, shims: Path):
    """Run the packaged Dispatcher entry point and capture everything it did."""
    scrubbed = ("PYTHONPATH", "COVERAGE_PROCESS_START")
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in scrubbed and not key.startswith("COV_CORE_")
    }
    env["PATH"] = f"{shims}{os.pathsep}{env.get('PATH', '')}"
    env["TMPDIR"] = str(tmp_root)
    env["CLAUDE_PLUGIN_ROOT"] = str(install_root)
    env["LIVESPEC_TEST_INVOCATION_RECORD"] = str(record)
    # Fully supplied, so a credential refusal cannot stand in for the payload
    # refusal this test is about.
    env["BEADS_DOLT_PASSWORD"] = "test-not-a-real-secret"
    env["GITHUB_APP_ID"] = "000000"
    env["GITHUB_PRIVATE_KEY"] = "test-not-a-real-key"
    return subprocess.run(
        [
            sys.executable,
            str(install_root / "scripts" / "bin" / "dispatcher.py"),
            "loop",
            "--repo",
            str(repo),
            "--item",
            "bd-ib-never-claimed",
            "--budget",
            "1",
            "--parallel",
            "1",
            "--invoker",
            "test:payload-refusal",
            "--json",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo),
        check=False,
        timeout=_CLI_TIMEOUT_SECONDS,
    )


def test_an_incomplete_source_payload_is_refused_before_any_claim(tmp_path: Path) -> None:
    """A source missing its vendored tree must refuse, not crash deep in an import."""
    install_root = _install(root=tmp_path / "install")
    shutil.rmtree(install_root.joinpath(*_VENDOR_RELPATH))
    repo = _dispatch_repo(root=tmp_path / "repo")
    tmp_root = tmp_path / "tmpdir"
    tmp_root.mkdir()
    record = tmp_path / "invocations.txt"
    shims = _shim_path(shim_dir=tmp_path / "shims", record=record)

    result = _run_dispatcher(
        install_root=install_root, repo=repo, tmp_root=tmp_root, record=record, shims=shims
    )

    assert result.returncode == _EXIT_PRECONDITION_ERROR, (
        "an incomplete source payload must produce a precondition refusal, not a "
        f"crash:\nexit={result.returncode}\n{result.stdout}\n{result.stderr}"
    )
    assert (
        "_vendor" in result.stderr
    ), f"the refusal does not name what is missing:\n{result.stderr}"
    assert (
        str(install_root) in result.stderr
    ), f"the refusal does not name the installation it refused:\n{result.stderr}"
    assert (
        not record.exists()
    ), f"the dispatch invoked bd/fabro before refusing:\n{record.read_text(encoding='utf-8')}"
    assert not repo.joinpath(*_JOURNAL_RELPATH).exists(), "the dispatch journaled before refusing"


def test_a_failed_copy_refuses_and_leaves_no_adoptable_payload(tmp_path: Path) -> None:
    """A provision that breaks part-way must clean up after itself.

    A dangling symlink inside the source makes the real whole-tree copy fail
    after it has already written part of the destination — the same shape as a
    source that disappears mid-provision. What must NOT survive is the partial
    tree: a later invocation finding it could execute an incomplete release.
    """
    install_root = _install(root=tmp_path / "install")
    (install_root / "scripts" / "dangling-link").symlink_to(tmp_path / "nothing-here")
    repo = _dispatch_repo(root=tmp_path / "repo")
    tmp_root = tmp_path / "tmpdir"
    tmp_root.mkdir()
    record = tmp_path / "invocations.txt"
    shims = _shim_path(shim_dir=tmp_path / "shims", record=record)

    result = _run_dispatcher(
        install_root=install_root, repo=repo, tmp_root=tmp_root, record=record, shims=shims
    )

    assert result.returncode == _EXIT_PRECONDITION_ERROR, (
        "a failed copy must produce a precondition refusal, not a crash:\n"
        f"exit={result.returncode}\n{result.stdout}\n{result.stderr}"
    )
    assert (
        str(install_root) in result.stderr
    ), f"the refusal does not name the installation it refused:\n{result.stderr}"
    assert sorted(entry.name for entry in tmp_root.iterdir()) == [], (
        "the failed provision left a partial payload a later invocation could "
        f"adopt: {sorted(entry.name for entry in tmp_root.iterdir())}"
    )
    assert (
        not record.exists()
    ), f"the dispatch invoked bd/fabro before refusing:\n{record.read_text(encoding='utf-8')}"
    assert not repo.joinpath(*_JOURNAL_RELPATH).exists(), "the dispatch journaled before refusing"
