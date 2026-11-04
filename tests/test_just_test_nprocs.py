"""Behavioral coverage for the test-worker count resolver."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_RESOLVER = _ROOT / "dev-tooling" / "just-test-nprocs.sh"


def _run_resolver(
    *,
    tmp_path: Path,
    cpu_max: str,
    nproc_output: str,
    parallelism: str = "",
) -> subprocess.CompletedProcess[str]:
    """Run the resolver with controlled cgroup and affinity probes."""
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_cat = fake_bin / "cat"
    _ = fake_cat.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$1" == /sys/fs/cgroup/cpu.max ]]; then\n'
        f"    printf '%s\\n' '{cpu_max}'\n"
        "    exit 0\n"
        "fi\n"
        'exec /bin/cat "$@"\n',
        encoding="utf-8",
    )
    fake_cat.chmod(0o755)
    fake_nproc = fake_bin / "nproc"
    _ = fake_nproc.write_text(
        "#!/usr/bin/env bash\n" f"printf '%s\\n' '{nproc_output}'\n",
        encoding="utf-8",
    )
    fake_nproc.chmod(0o755)
    return subprocess.run(
        ["bash", str(_RESOLVER)],
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "LIVESPEC_CI_LANE": "local",
            "LIVESPEC_TEST_PARALLELISM": parallelism,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
        },
        text=True,
    )


def test_cgroup_quota_sets_worker_count_before_host_core_count(
    tmp_path: Path,
) -> None:
    """A four-CPU quota yields one worker even when nproc sees 32 CPUs."""
    result = _run_resolver(
        tmp_path=tmp_path,
        cpu_max="400000 100000",
        nproc_output="32",
    )

    assert result.returncode == 0
    assert result.stdout == "1\n"


def test_affinity_count_sets_worker_count_when_no_cgroup_quota(
    tmp_path: Path,
) -> None:
    """The affinity-aware nproc fallback sets workers when cpu.max is unlimited."""
    result = _run_resolver(
        tmp_path=tmp_path,
        cpu_max="max 100000",
        nproc_output="8",
    )

    assert result.returncode == 0
    assert result.stdout == "2\n"


def test_explicit_parallelism_takes_precedence_over_cpu_allowance(
    tmp_path: Path,
) -> None:
    """An explicit worker count bypasses quota and affinity resolution."""
    result = _run_resolver(
        tmp_path=tmp_path,
        cpu_max="400000 100000",
        nproc_output="32",
        parallelism="3",
    )

    assert result.returncode == 0
    assert result.stdout == "3\n"
