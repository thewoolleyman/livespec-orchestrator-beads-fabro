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


def test_proxy_applies_leading_env_assignments_to_the_adapter(tmp_path: Path) -> None:
    """An adapter command that opens with `NAME=value` words launches with them set."""
    node = shutil.which("node")
    assert node is not None
    script = "process.stdout.write(process.env.LIVESPEC_PROXY_PROBE + '\\n');"
    completed = subprocess.run(
        [
            node,
            str(_PROXY),
            "--",
            "LIVESPEC_PROXY_PROBE=from-assignment",
            "OTHER_PROBE=a=b",
            node,
            "-e",
            script,
        ],
        check=False,
        cwd=tmp_path,
        env={"LIVESPEC_ACP_CONTEXT_ROOT": str(tmp_path)},
        input="",
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "from-assignment\n"


def _run_with_instruction_files(
    root: Path, files: list[str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    assert node is not None
    return subprocess.run(
        [node, str(_PROXY), "--", node, "-e", _ECHO_ADAPTER],
        check=False,
        cwd=cwd,
        env={
            "LIVESPEC_ACP_CONTEXT_ROOT": str(root),
            "LIVESPEC_ACP_CONTEXT_LOADS": json.dumps({"instruction_files": files}),
        },
        input="",
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_proxy_refuses_instruction_files_outside_the_governed_root(tmp_path: Path) -> None:
    """Absolute, `..`-escaping and symlink-escaping instruction files are refused."""
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("outside text", encoding="utf-8")
    (root / "link.md").symlink_to(outside)

    for declared in (str(outside), "../secret.txt", "link.md"):
        completed = _run_with_instruction_files(root, [declared], tmp_path)
        assert completed.returncode != 0, declared
        assert "governed repository root" in completed.stderr, declared
        assert "outside text" not in completed.stdout, declared


def test_proxy_accepts_a_nested_instruction_file_inside_the_root(tmp_path: Path) -> None:
    """A relative path inside the governed root still loads."""
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "rules.md").write_text("nested", encoding="utf-8")

    completed = _run_with_instruction_files(root, ["docs/rules.md"], tmp_path)

    assert completed.returncode == 0, completed.stderr
