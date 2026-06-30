"""Static guard: the entrypoint's GitHub provisioning is thin glue, no logic.

All credential logic (App JWT signing, installation-token exchange, App-vs-PAT
choice) lives in the tested Python CLI `commands/mint_app_token.py`. The shell
entrypoint may ONLY invoke that CLI and export its output. These assertions pin
that invariant so logic cannot silently creep back into shell, mirroring
`test_real_work_dispatch_script.py`.
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENTRYPOINT = _REPO_ROOT / "orchestrator-image" / "orchestrator-entrypoint.sh"


def test_entrypoint_delegates_credential_resolution_to_the_python_cli() -> None:
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    assert 'token="$(python3 "$MINT_APP_TOKEN_BIN")"' in text
    assert "mint_app_token.py" in text


def test_entrypoint_exports_the_resolved_token() -> None:
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    assert 'export GH_TOKEN="$token"' in text
    assert "gh auth login --with-token" in text


def test_entrypoint_carries_no_token_minting_logic() -> None:
    """No JWT/openssl/installation-exchange logic may live in the shell."""
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    for forbidden in ("openssl", "/app/installations", "access_tokens", "RS256", "JWT"):
        assert forbidden not in text, f"token logic leaked into shell: {forbidden}"


def test_entrypoint_does_not_branch_credential_source_in_shell() -> None:
    """The App-vs-PAT decision is the CLI's job; the shell must not re-branch it."""
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    # The old shell guard that branched on the PAT must be gone.
    assert 'if [ -z "${LIVESPEC_FAMILY_GITHUB_TOKEN' not in text
