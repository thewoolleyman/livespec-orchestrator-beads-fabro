"""Static coverage for the real-work dispatch shell helper.

The helper is intentionally shell because it owns Docker lifecycle and
secret projection. These tests pin the brittle command construction that
must stay aligned with the Beads connection model without running Docker.
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "orchestrator-image" / "real-work-dispatch.sh"


def test_metadata_regeneration_uses_target_clone_connection_fields() -> None:
    """Decoupled tenants must not be reconstructed from TARGET_REPO."""
    text = _SCRIPT.read_text(encoding="utf-8")

    assert '--server-user "$server_user"' in text
    assert '--database "$database"' in text
    assert '--prefix "$prefix"' in text
    assert '--server-user "$1"' not in text
    assert '--database "$1"' not in text
    assert '--prefix "$1"' not in text
    assert ".livespec.jsonc" in text


def test_codex_auth_projects_only_the_credential_not_the_whole_codex_home() -> None:
    """Only ~/.codex/auth.json crosses into the container (credential-only).

    The whole ~/.codex (config.toml, MCP servers, history) must NOT be carried —
    it would change the sandboxed agent's behavior and invalidate the run — and
    the credential flows via stdin, never a directory bind-mount or a container
    env var.
    """
    text = _SCRIPT.read_text(encoding="utf-8")

    # The credential SOURCE is the single host auth.json file.
    assert "${CODEX_HOME:-$HOME/.codex}/auth.json" in text
    # Written in-container as ONLY auth.json, fed over stdin (docker exec -i).
    assert 'cat > "$HOME/.codex/auth.json"' in text
    assert "docker exec -i" in text
    # The projection step is wired into the dispatch flow.
    assert "provision_codex_auth" in text
    # The whole ~/.codex is NEVER bind-mounted, and the credential is never an env var.
    assert '-v "$HOME/.codex' not in text
    assert ":/root/.codex" not in text
    assert "-e CODEX" not in text
