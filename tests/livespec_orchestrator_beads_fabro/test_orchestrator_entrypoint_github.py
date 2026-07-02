"""Static guard: the entrypoint's GitHub provisioning is thin glue, no logic.

All credential logic (App JWT signing, installation-token exchange, the
fail-closed no-fleet-fallback boundary) lives in the tested Python CLI
`commands/mint_app_token.py` over the vendored `livespec_runtime.github_auth`.
The shell entrypoint may ONLY invoke that CLI and `gh auth login` with its
output. These assertions pin that invariant so logic cannot silently creep
back into shell, mirroring `test_real_work_dispatch_script.py`.
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENTRYPOINT = _REPO_ROOT / "orchestrator-image" / "orchestrator-entrypoint.sh"


def test_entrypoint_delegates_credential_resolution_to_the_python_cli() -> None:
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    assert 'token="$(python3 "$MINT_APP_TOKEN_BIN")"' in text
    assert "mint_app_token.py" in text


def test_entrypoint_logs_gh_in_but_never_exports_a_static_token() -> None:
    """`gh auth login` bootstraps fabro + the initial clones; a once-at-start
    `export GH_TOKEN` is FORBIDDEN (github-app-auth Pillar 1) — it would
    expire after ~1 hour while the Dispatcher's provider re-mints per
    subprocess instead."""
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    assert "gh auth login --with-token" in text
    assert "export GH_TOKEN" not in text


def test_entrypoint_carries_no_token_minting_logic() -> None:
    """No JWT/openssl/installation-exchange logic may live in the shell."""
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    for forbidden in ("openssl", "/app/installations", "access_tokens", "RS256", "JWT"):
        assert forbidden not in text, f"token logic leaked into shell: {forbidden}"


def test_entrypoint_never_references_the_retired_fleet_pat() -> None:
    """The fleet PAT is retired (github-app-auth Pillar 2): the App env via
    the dispatch target's credential_wrapper is the SOLE credential source,
    and no PAT fallback branch may reappear in shell."""
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    assert "LIVESPEC_FAMILY_GITHUB_TOKEN" not in text
    assert "GITHUB_APP_ID" in text
    assert "GITHUB_PRIVATE_KEY" in text
