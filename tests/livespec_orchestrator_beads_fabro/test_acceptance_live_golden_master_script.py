"""Static guards for the live golden-master shell harness.

The live harness owns Docker lifecycle and the host-to-container credential
projection needed before the Dispatcher can materialize the worker overlay.
These tests pin that brittle shell contract without running Docker.
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "orchestrator-image" / "acceptance-live-golden-master.sh"


def test_live_golden_master_projects_codex_auth_before_dispatch() -> None:
    """The live proof must give the Dispatcher a host Codex credential.

    The Dispatcher reads its own host-side `$HOME/.codex/auth.json`, then writes
    the non-rotatable snapshot into the Fabro sandbox overlay. In the live
    harness that host is the orchestrator container, so the script must copy the
    operator host's single auth.json file into the container before dispatch.
    """
    text = _SCRIPT.read_text(encoding="utf-8")

    assert "${CODEX_HOME:-$HOME/.codex}/auth.json" in text
    assert 'cat > "$HOME/.codex/auth.json"' in text
    assert "docker exec -i" in text
    assert "provision_codex_auth" in text
    assert "provision_codex_auth" in text.split("run_dispatch", maxsplit=1)[0]


def test_live_golden_master_keeps_codex_projection_credential_only() -> None:
    """Never carry the whole host Codex home or the credential as env."""
    text = _SCRIPT.read_text(encoding="utf-8")

    assert '-v "$HOME/.codex' not in text
    assert ":/root/.codex" not in text
    assert "-e CODEX" not in text
