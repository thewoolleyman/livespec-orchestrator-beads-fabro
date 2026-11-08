"""The host-wide Codex marketplace registrations keep their clone payload sparse."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "dev-tooling" / "just-ensure-codex-plugins.sh"
_SPARSE_SUFFIX = " --sparse .agents/plugins --sparse .claude-plugin"
_REGISTRATIONS = (
    "thewoolleyman/livespec --ref release",
    "thewoolleyman/livespec-driver-codex --ref release",
    f"thewoolleyman/livespec-orchestrator-beads-fabro --ref release{_SPARSE_SUFFIX}",
)


def test_only_the_orchestrator_registration_is_sparse_to_its_catalog_and_plugin_payload(
    tmp_path: Path,
) -> None:
    """The orchestrator's sparse clone keeps Codex's refresh below its 30-second limit."""
    invocation_log = tmp_path / "codex-invocations"
    fake_codex = tmp_path / "bin" / "codex"
    fake_codex.parent.mkdir()
    fake_codex.write_text(
        "#!/usr/bin/env bash\n" 'printf \'%s\\n\' "$*" >> "$CODEX_INVOCATION_LOG"\n',
        encoding="utf-8",
    )
    fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)
    environment = {
        **os.environ,
        "PATH": f"{fake_codex.parent}:{os.environ['PATH']}",
        "CODEX_INVOCATION_LOG": str(invocation_log),
    }

    completed = subprocess.run(
        ["bash", str(_SCRIPT)],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    expected = [f"plugin marketplace add {registration}" for registration in _REGISTRATIONS]
    calls = invocation_log.read_text(encoding="utf-8").splitlines()
    assert calls[: len(_REGISTRATIONS)] == expected
