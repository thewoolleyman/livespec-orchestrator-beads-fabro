"""Contracts for the orchestrator image's `build-and-verify.sh` runner.

Two defects motivated this module, and they share one shape: EACH PRODUCED A
RUN THAT LOOKED LIKE IT VERIFIED THE IMAGE AND DID NOT.

  * The script was committed mode `100644` while every sibling runner in the
    directory is `100755`, so the invocation the image README documents died
    `permission denied` before a single check ran.
  * The provisioning wait failed OPEN: the poll loop simply ran out and
    execution fell through to the checks with no error and no message, so the
    first check probed a container that was already dead and was SIGKILLed.

The image is what makes the containerized server and the host-direct server
agree on which fabro they run, so a verification run that silently checks
nothing is exactly the artifact that would let those two diverge while the
operator believes they were checked.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "orchestrator-image" / "build-and-verify.sh"
_README = _REPO_ROOT / "orchestrator-image" / "README.md"
_SCRIPT_REL = "orchestrator-image/build-and-verify.sh"

# The line the stubbed `docker logs` emits. Deliberately made of SHORT words:
# the script pipes the container logs through its secret-redaction filter,
# which rewrites any run of 24-or-more `[A-Za-z0-9_-]` characters, and a
# sentinel that tripped it would make this test unable to observe its own
# evidence.
_CONTAINER_LOG_SENTINEL = "entrypoint FATAL: no secrets to provision from"

# The banner the FIRST tier-1 check prints. Reaching it is what the old
# fall-through did and what the assertion must now prevent, so it is the one
# token that separates "aborted at the wait" from "exited non-zero elsewhere".
_FIRST_CHECK_BANNER = "T1.0 gh version"


def _write_docker_stub(*, bin_dir: Path, readiness_probe_succeeds: bool) -> None:
    """Install a `docker` whose readiness probe succeeds or fails on demand.

    `docker exec "$CONTAINER" docker info` is the script's readiness probe, so
    an `exec` arm that always fails IS the "container never came up" condition
    the wait must refuse to fall through, and an `exec` arm that succeeds is
    the control proving the same wait still lets a healthy run through. Every
    other verb succeeds, which is what forces the run to reach the wait rather
    than dying earlier for an unrelated reason.
    """
    stub = bin_dir / "docker"
    exec_arm = "  exec) : ;;\n" if readiness_probe_succeeds else "  exec) exit 1 ;;\n"
    _ = stub.write_text(
        "#!/usr/bin/env bash\n"
        "set -uo pipefail\n"
        'case "${1:-}" in\n'
        f"{exec_arm}"
        f"  logs) printf '%s\\n' '{_CONTAINER_LOG_SENTINEL}' ;;\n"
        "  *) : ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)


def _write_fabro_stub(*, bin_dir: Path) -> Path:
    """Install a stand-in for `$HOST_FABRO_BIN`, which the script stages and runs."""
    stub = bin_dir / "fabro"
    _ = stub.write_text(
        "#!/usr/bin/env bash\nprintf 'fabro 0.0.0-stub\\n'\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return stub


def _stage_build_context(*, tmp_path: Path) -> Path:
    """Copy the script into an isolated tree that mirrors the paths it reads.

    The script is exercised from a COPY rather than in place because a real run
    mutates its own directory: it stages the fabro binary and two source trees
    into the build context and its cleanup trap deletes those paths
    unconditionally. Pointing it at the live checkout would make the test
    destructive.
    """
    root = tmp_path / "checkout"
    image_dir = root / "orchestrator-image"
    image_dir.mkdir(parents=True)
    for copied_tree in (root / ".claude-plugin" / "scripts", root / "bd-guard"):
        copied_tree.mkdir(parents=True)
        _ = (copied_tree / "placeholder").write_text("", encoding="utf-8")
    script = image_dir / "build-and-verify.sh"
    _ = script.write_bytes(_SCRIPT.read_bytes())
    script.chmod(0o755)
    return script


def _run_script(
    *, tmp_path: Path, readiness_probe_succeeds: bool
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_docker_stub(bin_dir=bin_dir, readiness_probe_succeeds=readiness_probe_succeeds)
    fabro = _write_fabro_stub(bin_dir=bin_dir)
    script = _stage_build_context(tmp_path=tmp_path)
    env = {
        **os.environ,
        "HOST_FABRO_BIN": str(fabro),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        # One poll rather than ninety, so the assertion under test is reached
        # in about a second.
        "PROVISION_WAIT_SECONDS": "1",
    }
    return subprocess.run(
        [str(script)],
        check=False,
        env=env,
        text=True,
        capture_output=True,
    )


def test_script_is_committed_with_the_executable_bit_set() -> None:
    staged = subprocess.run(
        ["git", "ls-files", "--stage", "--", _SCRIPT_REL],
        check=True,
        cwd=_REPO_ROOT,
        text=True,
        capture_output=True,
    ).stdout.split()

    # The INDEX mode is the one a fresh clone materializes, so it — not the
    # working tree — is what decides whether the documented invocation runs
    # for the next operator.
    assert staged[:1] == ["100755"], staged

    assert os.access(_SCRIPT, os.X_OK)


def test_readme_documents_the_invocation_with_no_shell_prefix() -> None:
    readme = _README.read_text(encoding="utf-8")

    assert f"./{_SCRIPT_REL}" in readme
    # A `bash <script>` spelling papers over a missing executable bit, which is
    # how the mode drifted from its siblings unnoticed in the first place.
    assert f"bash {_SCRIPT_REL}" not in readme
    assert f"bash {_SCRIPT_REL}" not in _SCRIPT.read_text(encoding="utf-8")


def test_provisioning_that_never_succeeds_fails_loudly_with_the_container_logs(
    tmp_path: Path,
) -> None:
    result = _run_script(tmp_path=tmp_path, readiness_probe_succeeds=False)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "in-container provisioning never completed" in result.stderr
    assert _CONTAINER_LOG_SENTINEL in result.stderr

    # The discriminator. A non-zero exit alone is equally consistent with the
    # run having died somewhere EARLIER for an unrelated reason, which is the
    # measurement this test would otherwise be incapable of distinguishing.
    # `T1.0` is the first check the old fall-through reached, so its absence
    # proves the run aborted AT the wait rather than before or after it.
    assert _FIRST_CHECK_BANNER not in result.stdout


def test_provisioning_that_succeeds_is_not_refused_by_the_same_wait(
    tmp_path: Path,
) -> None:
    """The control for the refusal above — a guard that can never pass is no guard.

    Only the readiness probe differs from the refusal case, so this pins the
    wait's power to DISCRIMINATE rather than merely to fail. The run still
    exits non-zero, because the stubbed `docker info` reports no storage
    driver and T1.a rejects it; what matters is that it got that far.
    """
    result = _run_script(tmp_path=tmp_path, readiness_probe_succeeds=True)

    assert "in-container provisioning never completed" not in result.stderr
    assert _FIRST_CHECK_BANNER in result.stdout
