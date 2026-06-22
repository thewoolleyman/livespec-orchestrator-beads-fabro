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
