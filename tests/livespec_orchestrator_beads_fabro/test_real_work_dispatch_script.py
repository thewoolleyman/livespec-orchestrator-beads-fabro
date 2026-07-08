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


def test_dispatch_script_resolves_github_auth_via_app_env_never_the_fleet_pat() -> None:
    """github-app-auth Pillars 1+2 pinned at the shell layer.

    The dispatch TARGET's credential_wrapper injects the GitHub App env
    (GITHUB_APP_ID + GITHUB_PRIVATE_KEY); the script requires and forwards
    THAT, never the retired fleet PAT (LIVESPEC_FAMILY_GITHUB_TOKEN), and
    never bakes a once-at-start `export GH_TOKEN=...` into the dispatcher
    invocation — the in-container provider re-mints per subprocess.
    """
    text = _SCRIPT.read_text(encoding="utf-8")

    assert "require_env GITHUB_APP_ID" in text
    assert "require_env GITHUB_PRIVATE_KEY" in text
    assert "-e GITHUB_APP_ID" in text
    assert "-e GITHUB_PRIVATE_KEY" in text
    assert "LIVESPEC_FAMILY_GITHUB_TOKEN" not in text
    assert "export GH_TOKEN=" not in text


def test_target_clone_is_mise_trusted_before_dispatch() -> None:
    """The post-merge pull-primary stage runs `mise exec` with the TARGET
    clone as cwd; a fresh clone's .mise.toml is untrusted in-container, so
    the provisioning step must `mise trust` it (the dispatcher clone gets
    the same treatment in sync_dispatcher_deps)."""
    text = _SCRIPT.read_text(encoding="utf-8")

    assert text.count("mise trust") >= 2
    assert '-w "$TARGET_CLONE" "$CONTAINER" sh -lc \\\n    \'mise trust' in text


def test_beads_metadata_regen_uses_a_non_git_scratch_dir_not_the_clone() -> None:
    """metadata.json is derived in a non-git scratch dir, then copied in.

    Running `bd init` inside the cloned git checkout makes bd derive a
    dolt-over-git remote from the repo origin and attempt a `dolt clone` that
    fails for tenants whose SQL user cannot access it (observed for `livespec`).
    A non-git scratch dir has no origin, so bd init adopts the server identity.
    """
    text = _SCRIPT.read_text(encoding="utf-8")

    # bd init runs against a fresh scratch dir, and only metadata.json is copied
    # into the clone.
    assert 'scratch="$(mktemp -d)"' in text
    assert 'cp "$scratch/.beads/metadata.json" .beads/metadata.json' in text
    # The old in-clone behavior (auto-commit then reset) is gone: regen must not
    # reset the clone to origin/master anymore.
    assert "git reset --hard origin/master" not in text


def test_running_dispatch_container_is_never_force_removed_by_newcomer() -> None:
    """Concurrent launches fail fast instead of killing in-flight dispatches."""
    text = _SCRIPT.read_text(encoding="utf-8")

    assert "CONTAINER_STARTED=0" in text
    assert "remove_stale_dispatch_container" in text
    assert "docker container inspect -f '{{.State.Running}}'" in text
    assert 'fail "container already running: $CONTAINER"' in text
    assert 'if [ "$CONTAINER_STARTED" -eq 1 ]; then' in text
    assert 'docker rm -f "$CONTAINER" >/dev/null 2>&1 || true' in text
    assert (
        'docker rm -f "$CONTAINER" >/dev/null 2>&1 || true\n  docker volume rm "$VARLIB_VOL"'
        not in text
    )
