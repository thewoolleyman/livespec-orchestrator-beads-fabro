"""The host-wide Codex marketplace registrations keep their clone payload sparse."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "dev-tooling" / "just-ensure-codex-plugins.sh"
_MARKETPLACES = (
    "thewoolleyman/livespec",
    "thewoolleyman/livespec-driver-codex",
    "thewoolleyman/livespec-orchestrator-beads-fabro",
)
_SPARSE_PATHS = (".agents/plugins", ".claude-plugin")


def test_each_git_marketplace_registration_requests_only_the_catalog_and_plugin_payload(
    tmp_path: Path,
) -> None:
    """Sparse registrations keep Codex's refresh clone below its 30-second limit."""
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
    expected = [
        f"plugin marketplace add {marketplace} --ref release"
        " --sparse .agents/plugins --sparse .claude-plugin"
        for marketplace in _MARKETPLACES
    ]
    calls = invocation_log.read_text(encoding="utf-8").splitlines()
    assert calls[: len(_MARKETPLACES)] == expected
