"""Completeness means USABLE and SAME-RELEASE, not "these six paths exist".

The provisioning refusal already grades a source before copying it, but it
graded with `Path.exists()` over six entries, and `exists()` cannot tell any
of these apart from a healthy release:

- `scripts/_vendor` or `.fabro/workflows` present but EMPTY — every deferred
  `livespec_runtime` import and every packaged asset read fails later, at the
  far end of the dispatch, which is the failure retention exists to prevent;
- a required path of the WRONG FILE TYPE — `__init__.py` as a directory, or
  `_vendor` as a plain file — which satisfies `exists()` and nothing else;
- a COPY that landed short of its source. This is the literal one: the
  incident behind this work-item was `_dispatcher_cost_wave` raising
  `ModuleNotFoundError`, a module no six-entry list names, so a payload
  missing exactly that file was publishable as complete.

The existing `cache-manifest.json` is not the answer either: its
`required_paths` are top-level and omit `scripts/_vendor` and `.fabro/`
entirely — the two trees whose absence produced the measured failure — so
grading against it unchanged would establish no more than grading against the
six entries did.

What IS bounded and provable here: the payload is a WHOLE-TREE COPY of the
release, so "same release, complete" is answerable by comparing the copy
against the source it was made from, file for file. Paired with a type- and
emptiness-aware grade of the source itself, that covers every case above
without a file manifest, a content-integrity service, or anything resembling a
cache platform.

Every case drives the real packaged Dispatcher entry point in a real child and
observes the same zero-claim evidence as the other provisioning guards:
`bd`/`fabro` recorders that must never be called, no dispatch journal, and no
private directory left behind. The short-copy case needs ONE narrow control on
the product's own `shutil.ignore_patterns` seam, because a copy that drops a
single deferred module cannot be produced from outside the copy.

Real child processes are the only way to ask this, so this file is listed in
`pyproject.toml`'s `subprocess_spawn_allowlist` and scrubs the coverage
subprocess hooks exactly as an allowlisted spawn must.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLUGIN_ROOT = _REPO_ROOT / ".claude-plugin"

_EXIT_PRECONDITION_ERROR = 3
_CLI_TIMEOUT_SECONDS = 300.0
_JOURNAL_RELPATH = ("tmp", "fabro-dispatch-journal.jsonl")
# The module whose absence IS the incident: `bd-ib-3ftj` records this exact
# `ModuleNotFoundError` after an older cache was evicted.
_DEFERRED_MODULE = "_dispatcher_cost_wave.py"
_DEFERRED_MODULE_RELPATH = (
    "scripts",
    "livespec_orchestrator_beads_fabro",
    "commands",
    _DEFERRED_MODULE,
)

_RECORDER = """#!/bin/sh
printf '%s %s\\n' "$0" "$*" >> "$LIVESPEC_TEST_INVOCATION_RECORD"
exit 0
"""

# Runs the REAL `bin/dispatcher.py` through `runpy`. In `short-copy` mode one
# narrow control is applied first: the product's own `ignore_patterns` seam is
# wrapped so the real `copytree` SKIPS one deferred module, which is what a
# copy landing short of its source looks like from the inside.
_PROBE = """
import runpy
import shutil
import sys
from pathlib import Path

mode, install_root, entry_point, dropped = sys.argv[1:5]
cli_args = sys.argv[5:]

sys.path.insert(0, str(Path(install_root) / "scripts" / "bin"))
import _payload

if mode == "short-copy":
    real_ignore = shutil.ignore_patterns

    def _dropping_ignore(*names):
        return real_ignore(*names, dropped)

    _payload.shutil.ignore_patterns = _dropping_ignore

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


def _run_dispatcher(*, install_root: Path, tmp_path: Path, mode: str = "none"):
    repo = tmp_path / "repo"
    (repo / ".beads").mkdir(parents=True)
    _ = (repo / ".beads" / "config.yaml").write_text("dolt.mode: server\n", encoding="utf-8")
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "probe-tenant",
                        "prefix": "bd-pb",
                        "database": "probe-tenant",
                        "server_user": "probe-tenant",
                        "fake": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
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
    env["LIVESPEC_BEADS_FAKE"] = "1"
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
            _DEFERRED_MODULE,
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


def _assert_refused_cleanly(*, completed, tmp_root: Path, record: Path, repo: Path) -> None:
    assert completed.returncode == _EXIT_PRECONDITION_ERROR, (
        "an unusable payload must produce a precondition refusal before any "
        f"claim:\nexit={completed.returncode}\n{completed.stdout}\n{completed.stderr}"
    )
    assert list(tmp_root.iterdir()) == [], (
        f"a refused provision left a private directory: "
        f"{sorted(entry.name for entry in tmp_root.iterdir())}"
    )
    assert (
        not record.exists()
    ), f"the dispatch invoked bd/fabro before refusing:\n{record.read_text(encoding='utf-8')}"
    assert not repo.joinpath(*_JOURNAL_RELPATH).exists(), "the dispatch journaled before refusing"


@pytest.mark.parametrize(
    ("relative", "named"),
    [
        pytest.param(("scripts", "_vendor"), "_vendor", id="empty-vendor-tree"),
        pytest.param((".fabro", "workflows"), "workflows", id="empty-workflow-tree"),
    ],
)
def test_a_required_tree_that_is_present_but_empty_is_refused(
    tmp_path: Path, relative: tuple[str, ...], named: str
) -> None:
    """An empty tree satisfies `exists()` and supplies nothing."""
    install_root = _install(root=tmp_path / "install")
    target = install_root.joinpath(*relative)
    shutil.rmtree(target)
    target.mkdir(parents=True)

    completed, tmp_root, record, repo = _run_dispatcher(
        install_root=install_root, tmp_path=tmp_path
    )

    _assert_refused_cleanly(completed=completed, tmp_root=tmp_root, record=record, repo=repo)
    assert (
        named in completed.stderr
    ), f"the refusal does not name the unusable tree:\n{completed.stderr}"


@pytest.mark.parametrize(
    ("relative", "named"),
    [
        pytest.param(("scripts", "_vendor"), "_vendor", id="vendor-tree-as-a-file"),
        pytest.param(
            ("scripts", "livespec_orchestrator_beads_fabro", "__init__.py"),
            "__init__.py",
            id="package-init-as-a-directory",
        ),
    ],
)
def test_a_required_path_of_the_wrong_file_type_is_refused(
    tmp_path: Path, relative: tuple[str, ...], named: str
) -> None:
    """`exists()` is blind to type; a directory is not an importable module."""
    install_root = _install(root=tmp_path / "install")
    target = install_root.joinpath(*relative)
    if target.is_dir():
        shutil.rmtree(target)
        _ = target.write_text("not a directory\n", encoding="utf-8")
    else:
        target.unlink()
        target.mkdir()

    completed, tmp_root, record, repo = _run_dispatcher(
        install_root=install_root, tmp_path=tmp_path
    )

    _assert_refused_cleanly(completed=completed, tmp_root=tmp_root, record=record, repo=repo)
    assert (
        named in completed.stderr
    ), f"the refusal does not name the wrong-typed path:\n{completed.stderr}"


def test_a_copy_that_lands_short_of_its_source_is_refused(tmp_path: Path) -> None:
    """The literal incident: a payload missing one deferred module.

    `_dispatcher_cost_wave` is the module `bd-ib-3ftj` records failing to
    import after an eviction. No fixed list of required paths names it, so
    completeness has to be established against the SOURCE the copy was made
    from rather than against a list — which is also what makes it a
    same-release guarantee rather than a shape check.
    """
    install_root = _install(root=tmp_path / "install")
    assert install_root.joinpath(
        *_DEFERRED_MODULE_RELPATH
    ).is_file(), "fixture precondition: the source must carry the module the copy will drop"

    completed, tmp_root, record, repo = _run_dispatcher(
        install_root=install_root, tmp_path=tmp_path, mode="short-copy"
    )

    _assert_refused_cleanly(completed=completed, tmp_root=tmp_root, record=record, repo=repo)
    assert (
        _DEFERRED_MODULE in completed.stderr
    ), f"the refusal does not name the file the copy dropped:\n{completed.stderr}"


def test_a_complete_usable_release_still_provisions(tmp_path: Path) -> None:
    """The control: none of the above may be achieved by refusing everything."""
    install_root = _install(root=tmp_path / "install")

    completed, tmp_root, _record, _repo = _run_dispatcher(
        install_root=install_root, tmp_path=tmp_path
    )

    assert (
        completed.returncode == 0
    ), f"a complete release no longer provisions:\n{completed.stdout}\n{completed.stderr}"
    assert (
        "ledger findings" in completed.stdout
    ), f"the Dispatcher produced no ledger-check result:\n{completed.stdout}"
    # Empty because a COMPLETED invocation releases its own payload, not
    # because it refused — the exit code above is what separates those.
    assert list(tmp_root.iterdir()) == [], (
        f"the completed invocation leaked its payload: "
        f"{sorted(entry.name for entry in tmp_root.iterdir())}"
    )
