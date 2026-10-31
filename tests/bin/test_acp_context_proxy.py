"""ACP request-boundary coverage for the per-node context proxy.

The proxy is an executable Node program, so its effect must be tested through
the stdio transport an ACP adapter actually receives rather than by copying its
message transformation into Python.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROXY = _REPO_ROOT / ".claude-plugin" / "scripts" / "bin" / "livespec-acp-context-proxy.mjs"
_ECHO_ADAPTER = "process.stdin.pipe(process.stdout);"


def test_proxy_replaces_ambient_context_with_declared_instruction_text(tmp_path: Path) -> None:
    """A `session/new` request receives only the declared repository instruction."""
    node = shutil.which("node")
    assert node is not None
    (tmp_path / "AGENTS.md").write_text("declared instruction text", encoding="utf-8")
    request = {"method": "session/new", "params": {"mcpServers": {"ambient": {}}}}
    completed = subprocess.run(
        [node, str(_PROXY), "--", node, "-e", _ECHO_ADAPTER],
        check=False,
        cwd=tmp_path,
        env={
            "LIVESPEC_ACP_CONTEXT_ROOT": str(tmp_path),
            "LIVESPEC_ACP_CONTEXT_LOADS": json.dumps(
                {
                    "instruction_files": ["AGENTS.md"],
                    "skills": [],
                    "plugins": [],
                    "mcp_servers": [],
                }
            ),
        },
        input=f"{json.dumps(request)}\n",
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
    [forwarded] = [json.loads(line) for line in completed.stdout.splitlines()]
    assert forwarded["params"]["mcpServers"] == {}
    options = forwarded["params"]["_meta"]["claudeCode"]["options"]
    assert options["settingSources"] == []
    assert options["strictMcpConfig"] is True
    assert options["systemPrompt"]["append"] == "declared instruction text"
