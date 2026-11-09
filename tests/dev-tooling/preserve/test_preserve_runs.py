"""`dev-tooling/preserve/preserve_runs.sh` on a container worker node (livespec-dev-tooling-smzkpu).

A container worker (`homelab-worker.livespec.dev/class=worker`) runs plain containerd and takes no ssh
login, so the script reads its sandbox through `kubectl exec` on the control node rather than through
ssh and `k3s crictl` on the node itself (legacy-coordinator-agent ruling, 2026-11-09). These run the
real script under bash against stub `ssh`, `sudo` and `k3s` commands. The stub `k3s kubectl exec` runs
the sandbox command against a local workspace standing in for the pod's `/workspace`, and the run's
origin is a local bare repository reached through `url.<base>.insteadOf`, so nothing leaves the host.
"""

from __future__ import annotations

import json
import os
import shlex
import stat
import subprocess
from pathlib import Path

__all__: list[str] = []

_SCRIPT = Path(__file__).resolve().parents[3] / "dev-tooling" / "preserve" / "preserve_runs.sh"
_RUN = "01TESTRUN0000000000000000AB"
_POD = "petri-01testrun-l0"
_WORKER = "alpha-homelab-worker"
_URL = "https://github.com/acme/widget"

_SSH = """#!/bin/bash
# Stub ssh: drop options, log `<host> <command>`, run the command locally.
no_stdin=0
while [ $# -gt 0 ]; do
  case "$1" in
    -n) no_stdin=1; shift ;;
    -o) shift 2 ;;
    *) break ;;
  esac
done
host=$1; shift
printf '%s %s\\n' "$host" "$*" >> "$STUB_LOG"
[ "$no_stdin" = 1 ] && exec bash -c "$*" < /dev/null
exec bash -c "$*"
"""

_SUDO = """#!/bin/bash
[ "$1" = -n ] && shift
exec "$@"
"""

_K3S = """#!/bin/bash
# Stub `k3s kubectl`: answers get pods and get nodes, and runs exec against the stand-in workspace.
if [ "$1" = crictl ]; then
  printf 'crictl %s\\n' "$*" >> "$STUB_LOG"
  exit 98
fi
shift
case "$1 $2" in
  "get pods") cat "$PODS_JSON"; exit 0 ;;
  "get nodes") printf '%s' "$WORKER_NODES"; exit 0 ;;
esac
if [ "$1" = exec ]; then
  while [ $# -gt 0 ] && [ "$1" != -- ]; do shift; done
  shift
  [ "$1" = sh ] && [ "$2" = -c ] || exit 97
  printf 'exec %s\\n' "$3" >> "$STUB_LOG"
  exec sh -c "${3//\\/workspace/$SANDBOX_ROOT/workspace}"
fi
exit 99
"""


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _stub(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _make_repos(tmp_path: Path) -> tuple[Path, str]:
    """A bare origin, and a sandbox workspace whose run branch carries one commit of work."""
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    seed.mkdir()
    _git("init", "-q", "-b", "master", cwd=seed)
    _git("config", "user.email", "t@example.invalid", cwd=seed)
    _git("config", "user.name", "t", cwd=seed)
    (seed / "README").write_text("base\n", encoding="utf-8")
    _git("add", "README", cwd=seed)
    _git("commit", "-q", "-m", "base", cwd=seed)
    subprocess.run(["git", "clone", "-q", "--bare", str(seed), str(origin)], check=True)

    workspace = tmp_path / "sandbox" / "workspace"
    subprocess.run(["git", "clone", "-q", str(origin), str(workspace)], check=True)
    _git("config", "user.email", "t@example.invalid", cwd=workspace)
    _git("config", "user.name", "t", cwd=workspace)
    _git("checkout", "-q", "-b", f"fabro/run/{_RUN}", cwd=workspace)
    (workspace / "work.txt").write_text("the run's work\n", encoding="utf-8")
    _git("add", "work.txt", cwd=workspace)
    _git("commit", "-q", "-m", "work", cwd=workspace)
    work_sha = _git("rev-parse", "HEAD", cwd=workspace)
    _git("config", "remote.origin.url", f"{_URL}.git", cwd=workspace)
    _git("config", "livespec.factoryRunId", "dispatch-1", cwd=workspace)

    return origin, work_sha


def _make_stubs(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub(bin_dir, "ssh", _SSH)
    _stub(bin_dir, "sudo", _SUDO)
    _stub(bin_dir, "k3s", _K3S)
    return bin_dir


def _setup(tmp_path: Path, *, worker_nodes: str) -> tuple[dict[str, str], Path, str]:
    origin, work_sha = _make_repos(tmp_path)
    bin_dir = _make_stubs(tmp_path)
    pods = tmp_path / "pods.json"
    pods.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "metadata": {"name": _POD, "labels": {"petri.run": _RUN}},
                        "spec": {"nodeName": _WORKER},
                        "status": {"phase": "Running"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    log = tmp_path / "calls.log"
    log.write_text("", encoding="utf-8")
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "STUB_LOG": str(log),
        "PODS_JSON": str(pods),
        "WORKER_NODES": worker_nodes,
        "SANDBOX_ROOT": str(tmp_path / "sandbox"),
        "PRESERVE_WORK": str(tmp_path / "work"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": f"url.{origin}.insteadOf",
        "GIT_CONFIG_VALUE_0": _URL,
    }
    return env, origin, work_sha


def _run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(_SCRIPT), _RUN],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
    )


def test_a_worker_nodes_run_is_preserved_through_kubectl_exec(tmp_path: Path) -> None:
    env, origin, work_sha = _setup(tmp_path, worker_nodes=_WORKER)
    result = _run(env)
    assert result.returncode == 0, result.stderr
    [row] = [line.split("\t") for line in result.stdout.splitlines()[1:]]
    assert row[0] == _RUN and row[1] == _WORKER
    assert row[5] == "VERIFIED", result.stdout + result.stderr
    assert row[3] == work_sha and row[7] == "tip"
    assert _git("rev-parse", f"refs/heads/preserve/run-{_RUN}", cwd=origin) == work_sha


def test_a_worker_node_is_never_reached_over_ssh_or_crictl(tmp_path: Path) -> None:
    env, _, _ = _setup(tmp_path, worker_nodes=_WORKER)
    result = _run(env)
    assert result.returncode == 0, result.stderr
    calls = Path(env["STUB_LOG"]).read_text(encoding="utf-8").splitlines()
    assert not [c for c in calls if c.startswith(f"{_WORKER} ")]
    assert not [c for c in calls if c.startswith("crictl ")]
    assert [c for c in calls if c.startswith("exec ")]


def test_the_worker_exec_route_runs_only_read_commands(tmp_path: Path) -> None:
    env, _, _ = _setup(tmp_path, worker_nodes=_WORKER)
    result = _run(env)
    assert result.returncode == 0, result.stderr
    calls = Path(env["STUB_LOG"]).read_text(encoding="utf-8").splitlines()
    readers = {"test", "git", "cat", "find", "cd", "xargs"}
    for call in (c.removeprefix("exec ") for c in calls if c.startswith("exec ")):
        for part in call.split("&&"):
            words = shlex.split(part)
            assert words[0] in readers, call
            if words[0] == "git":
                assert "--get" in words, call
            if words[0] == "xargs":
                assert words[-1] == "cat", call


def test_a_non_worker_node_keeps_the_ssh_and_crictl_route(tmp_path: Path) -> None:
    """With the node absent from the worker list, the script goes to the node over ssh and crictl."""
    env, _, _ = _setup(tmp_path, worker_nodes="")
    result = _run(env)
    calls = Path(env["STUB_LOG"]).read_text(encoding="utf-8").splitlines()
    assert [c for c in calls if c.startswith(f"{_WORKER} ") and "k3s crictl ps" in c]
    assert not [c for c in calls if c.startswith("exec ")]
    assert "NO_CONTAINER" in result.stdout


def test_a_worker_copy_is_read_in_bounded_chunks(tmp_path: Path) -> None:
    """A tree larger than the chunk budget is copied over several exec streams, intact.

    One exec stream carrying the whole tree was reset by the API server on the first M4 run
    (2026-11-09, 31.8 MiB); each exec now carries at most the chunk budget.
    """
    env, origin, _ = _setup(tmp_path, worker_nodes=_WORKER)
    workspace = tmp_path / "sandbox" / "workspace"
    (workspace / "big.bin").write_bytes(os.urandom(5 * 1024 * 1024 // 2))
    _git("add", "big.bin", cwd=workspace)
    _git("commit", "-q", "-m", "big", cwd=workspace)
    work_sha = _git("rev-parse", "HEAD", cwd=workspace)
    env["PRESERVE_EXEC_CHUNK_BYTES"] = str(1024 * 1024)
    result = _run(env)
    assert result.returncode == 0, result.stderr
    [row] = [line.split("\t") for line in result.stdout.splitlines()[1:]]
    assert row[5] == "VERIFIED", result.stdout + result.stderr
    assert _git("rev-parse", f"refs/heads/preserve/run-{_RUN}", cwd=origin) == work_sha
    calls = Path(env["STUB_LOG"]).read_text(encoding="utf-8").splitlines()
    ranged = [c for c in calls if c.startswith("exec dd ")]
    assert len(ranged) >= 3, calls
    assert all("bs=1048576" in c and "count=1" in c for c in ranged)
