"""An unusable release manifest is REFUSED, never labelled and run anyway.

The completeness contract already requires `plugin.json` to be PRESENT. What
it did not require is that the file be usable: a manifest that is unreadable,
malformed, not an object, or carries no non-empty `version` degraded to the
string `unknown-release`, which became the holder's label, and the invocation
proceeded.

That is the wrong direction for this launcher. The release a payload carries
is its PROVENANCE, and provenance is what every downstream build comparison is
made of — `minimum_release_floor` reads it to decide whether the executing
build clears a committed floor, and the self-update canary and the
registered-install currency finding both compare it against another build. A
payload whose own release cannot be established cannot be compared with
anything; carrying it forward under a placeholder makes "which build is this"
unanswerable while every surface that asks continues to report an answer.
`unknown-release` also made a second payload indistinguishable from the first
in the one place an operator reads these directories by eye.

So validation now rejects an unusable manifest with the same actionable,
pre-claim refusal an incomplete source gets. The cases below drive the real
packaged Dispatcher entry point and observe the same zero-claim evidence as
the other provisioning guards: `bd` and `fabro` replaced on `PATH` by
recorders that must never be called, no dispatch journal, and no private
directory left behind.

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
_UNKNOWN_RELEASE = "unknown-release"

_RECORDER = """#!/bin/sh
printf '%s %s\\n' "$0" "$*" >> "$LIVESPEC_TEST_INVOCATION_RECORD"
exit 0
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


def _run_dispatcher(*, install_root: Path, tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / ".beads").mkdir(parents=True)
    _ = (repo / ".beads" / "config.yaml").write_text("dolt.mode: server\n", encoding="utf-8")
    # A resolvable hermetic connection, so the CONTROL below can reach a real
    # exit 0. An empty config cannot resolve one, which would make every case
    # here fail for a config reason and hide whether the refusal fired.
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
        [sys.executable, str(install_root / "scripts" / "bin" / "dispatcher.py"), "ledger-check"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo),
        check=False,
        timeout=_CLI_TIMEOUT_SECONDS,
    )
    return completed, tmp_root, record, repo


@pytest.mark.parametrize(
    "manifest",
    [
        pytest.param("{not json", id="malformed"),
        pytest.param("[]", id="not-an-object"),
        pytest.param("{}", id="no-version-key"),
        pytest.param('{"version": 7}', id="version-not-a-string"),
        pytest.param('{"version": "   "}', id="version-blank"),
    ],
)
def test_an_unusable_release_manifest_is_refused_before_any_claim(
    tmp_path: Path, manifest: str
) -> None:
    """Each unusable shape must refuse, name the manifest, and leave nothing."""
    install_root = _install(root=tmp_path / "install")
    _ = (install_root / "plugin.json").write_text(manifest, encoding="utf-8")

    completed, tmp_root, record, repo = _run_dispatcher(
        install_root=install_root, tmp_path=tmp_path
    )

    assert completed.returncode == _EXIT_PRECONDITION_ERROR, (
        "an unusable release manifest must produce a precondition refusal, not "
        f"a labelled payload:\nexit={completed.returncode}\n{completed.stdout}\n"
        f"{completed.stderr}"
    )
    assert (
        "plugin.json" in completed.stderr
    ), f"the refusal does not name the manifest it could not use:\n{completed.stderr}"
    assert (
        str(install_root) in completed.stderr
    ), f"the refusal does not name the installation it refused:\n{completed.stderr}"
    assert _UNKNOWN_RELEASE not in completed.stderr, (
        "the launcher still reports a placeholder release rather than refusing "
        f"to establish one:\n{completed.stderr}"
    )
    assert list(tmp_root.iterdir()) == [], (
        f"a refused provision created a private directory anyway: "
        f"{sorted(p.name for p in tmp_root.iterdir())}"
    )
    assert (
        not record.exists()
    ), f"the dispatch invoked bd/fabro before refusing:\n{record.read_text(encoding='utf-8')}"
    assert not repo.joinpath(*_JOURNAL_RELPATH).exists(), "the dispatch journaled before refusing"


def test_an_unreadable_release_manifest_is_refused_before_any_claim(tmp_path: Path) -> None:
    """Present but unreadable is its own shape: the completeness probe passes.

    A DIRECTORY named `plugin.json` satisfies an existence check and then
    fails the text read, which is exactly the gap a presence-only contract
    leaves.
    """
    install_root = _install(root=tmp_path / "install")
    (install_root / "plugin.json").unlink()
    (install_root / "plugin.json").mkdir()

    completed, tmp_root, record, repo = _run_dispatcher(
        install_root=install_root, tmp_path=tmp_path
    )

    assert completed.returncode == _EXIT_PRECONDITION_ERROR, (
        "an unreadable release manifest must produce a precondition refusal:\n"
        f"exit={completed.returncode}\n{completed.stdout}\n{completed.stderr}"
    )
    assert (
        "plugin.json" in completed.stderr
    ), f"the refusal does not name the manifest it could not read:\n{completed.stderr}"
    assert list(tmp_root.iterdir()) == [], (
        f"a refused provision created a private directory anyway: "
        f"{sorted(p.name for p in tmp_root.iterdir())}"
    )
    assert (
        not record.exists()
    ), f"the dispatch invoked bd/fabro before refusing:\n{record.read_text(encoding='utf-8')}"
    assert not repo.joinpath(*_JOURNAL_RELPATH).exists(), "the dispatch journaled before refusing"


def test_a_usable_release_manifest_still_provisions(tmp_path: Path) -> None:
    """The control: rejection must not have swallowed the normal path.

    Without this, every assertion above would also pass against a launcher
    that refused unconditionally.
    """
    install_root = _install(root=tmp_path / "install")

    completed, tmp_root, _record, _repo = _run_dispatcher(
        install_root=install_root, tmp_path=tmp_path
    )

    assert (
        completed.returncode == 0
    ), f"a usable release no longer provisions:\n{completed.stdout}\n{completed.stderr}"
    assert (
        "ledger findings" in completed.stdout
    ), f"the Dispatcher produced no ledger-check result:\n{completed.stdout}"
    # TMPDIR is empty here too, and that is NOT the discriminator: a COMPLETED
    # invocation releases its own payload (test_payload_lifetime_release.py), so
    # the holder is correctly gone by the time this runs. The exit code and the
    # result above are what separate "provisioned and ran" from "refused".
    assert list(tmp_root.iterdir()) == [], (
        f"the completed invocation leaked its payload: "
        f"{sorted(entry.name for entry in tmp_root.iterdir())}"
    )
