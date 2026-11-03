"""The launch preflight delegates host judges to the committed ACP chain.

The complete preflight needs the host's installed plugin registry and live
tenant, so its execution is captured on the launch host.  These assertions pin
the committed integration seam: the shell script restores the operator CLI
directory, resolves its candidates through the package, and delegates the
actual invocation to the same ordered chain used by the governing-heading and
reflector judgements.
"""

from __future__ import annotations

from pathlib import Path

_SCRIPT = Path("dev-tooling/dod-preflight.sh")


def test_the_preflight_uses_the_resolved_candidate_chain_and_operator_cli_directory() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")

    assert 'PATH="$HOME/.local/bin:$PATH"' in text
    assert "dod_gate_candidates" in text
    assert "run_candidate_chain" in text


def test_a_legacy_claude_agent_acp_adapter_string_remains_a_host_candidate() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")

    assert '"claude-agent-acp" in adapter.command' in text
    assert 'agent_id="claude-acp"' in text
