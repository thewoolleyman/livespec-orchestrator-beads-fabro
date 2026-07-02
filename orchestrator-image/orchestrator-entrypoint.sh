#!/usr/bin/env bash
# orchestrator-entrypoint.sh — the livespec dark-factory orchestrator supervisor.
#
# Step 1 of the W7 orchestrator-convergence epic (livespec-impl-beads-8bc).
# Runs as PID 1 inside the privileged orchestrator container and brings up the
# full control plane from injected externals, then hands off to the dispatcher
# (or a passed command):
#
#   1. start the INNER dockerd in the background;
#   2. block until /var/run/docker.sock exists AND `docker info` succeeds;
#   3. provision the headless fabro server:
#        - `gh auth login --with-token`  (GitHub token leg — fabro's `token`
#          strategy reads the token from the gh CLI's stored oauth token, NOT a
#          GITHUB_TOKEN env var directly; proven 2026-06-15);
#        - hand-provision the fabro server (settings.toml with dev-token auth
#          + the native GitHub App integration, generated server credentials,
#          LLM key via env) and START it — `fabro install` is NOT used because
#          its GitHub step rejects short-lived App installation tokens;
#   4. exec the passed command (the dispatcher loop), or drop to a shell.
#
# SECRET HYGIENE (non-negotiable): every credential arrives via env at
# `docker run`. NONE is echoed, logged, or written to a tracked file. Tokens
# flow into tools via stdin / env only; this script never `echo`es a secret and
# never prints `git remote -v`, env, or URLs containing tokens.
#
# Injected externals (env — see README.md "Injectable externals"):
#   GITHUB_APP_ID + GITHUB_PRIVATE_KEY  GitHub App (livespec-pr-bot; adopters set
#                                  their own) — the SOLE GitHub credential
#                                  source, injected by the dispatch target's
#                                  credential_wrapper on the host and forwarded
#                                  in. Installation tokens are minted on demand
#                                  by the tested Python CLI
#                                  (commands/mint_app_token.py) and re-minted by
#                                  the Dispatcher's provider; there is NO
#                                  fleet-PAT fallback (fail-closed per the
#                                  github-app-auth design).
#   GITHUB_APP_INSTALLATION_ID     optional installation pin (multi-install Apps)
#   GITHUB_API_URL                 optional API root override (GitHub Enterprise)
#   FABRO_LLM_API_KEY_ENV          name of the env var holding the LLM API key
#                                  (default: ANTHROPIC_API_KEY_LIVESPEC_E2E)
#   FABRO_LLM_PROVIDER             fabro LLM provider (default: anthropic)
#   CLAUDE_CODE_OAUTH_TOKEN        model auth the dispatcher projects per-dispatch
#   BEADS_DOLT_PASSWORD          shared family Dolt password (dispatcher; one bare var)
#   HONEYCOMB_INGEST_KEY_LIVESPEC  telemetry egress key (dispatcher)
#   FABRO_PORT                     control-plane / web-UI port (default: 32276)
#   FABRO_SKIP_LLM                 set non-empty to provision GitHub only (no LLM)

set -euo pipefail

log() { printf '[entrypoint] %s\n' "$*" >&2; }
die() { printf '[entrypoint] FATAL: %s\n' "$*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The tested Python CLI that mints the factory GitHub credential (a GitHub App
# installation token; fail-closed — NO PAT fallback). ALL credential logic
# lives in Python (commands/mint_app_token.py); this script only invokes it.
# Overridable for layouts where the plugin payload is not the entrypoint's
# sibling.
MINT_APP_TOKEN_BIN="${LIVESPEC_MINT_APP_TOKEN_BIN:-${SCRIPT_DIR}/../.claude-plugin/scripts/bin/mint_app_token.py}"

FABRO_PORT="${FABRO_PORT:-32276}"
FABRO_BIN="${FABRO_BIN:-/usr/local/bin/fabro}"
FABRO_LLM_PROVIDER="${FABRO_LLM_PROVIDER:-anthropic}"
FABRO_LLM_API_KEY_ENV="${FABRO_LLM_API_KEY_ENV:-ANTHROPIC_API_KEY_LIVESPEC_E2E}"

# --------------------------------------------------------------------------
# 1 + 2. Inner dockerd, then block on a healthy daemon.
# --------------------------------------------------------------------------
start_dockerd() {
  log "starting inner dockerd ..."
  # Log to a file (not the foreground) so a noisy daemon never drowns the
  # supervisor's own output. The daemon is the inner one; no host socket is
  # mounted, so Fabro targets it by construction (DinD, not DooD).
  dockerd >/var/log/dockerd.log 2>&1 &
}

wait_for_docker() {
  log "waiting for the inner docker daemon ..."
  local deadline=$((SECONDS + 60))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if [ -S /var/run/docker.sock ] && docker info >/dev/null 2>&1; then
      log "inner docker daemon is up."
      docker info --format 'Storage Driver: {{.Driver}}' 2>/dev/null | sed 's/^/[entrypoint] /' >&2 || true
      return 0
    fi
    sleep 1
  done
  log "----- tail of /var/log/dockerd.log -----"
  tail -n 30 /var/log/dockerd.log >&2 || true
  die "inner docker daemon did not become healthy within 60s (need --privileged + an ext4-backed /var/lib/docker volume)"
}

# --------------------------------------------------------------------------
# 3. Headless fabro server provisioning.
# --------------------------------------------------------------------------
provision_github() {
  # Thin glue ONLY (no credential logic — that lives in the tested Python CLI):
  # mint a GitHub App installation token and log gh in with it. The CLI is
  # FAIL-CLOSED (github-app-auth Pillar 2): the App env is the SOLE credential
  # source — there is NO fleet-PAT fallback. It prints ONLY the token to stdout
  # (its source is logged to stderr); the token is piped via stdin — never
  # placed in argv or echoed. The stored gh credential bootstraps the initial
  # in-container clones (`gh auth setup-git`); fabro itself authenticates via
  # its native GitHub App integration (see provision_fabro), NOT via gh.
  # Deliberately NO static token export here: a once-at-start export would
  # expire after ~1 hour (Pillar 1); the Dispatcher's provider re-mints per
  # subprocess instead.
  local token
  token="$(python3 "$MINT_APP_TOKEN_BIN")" \
    || die "could not mint a GitHub App installation token (the dispatch target's credential_wrapper must inject GITHUB_APP_ID + GITHUB_PRIVATE_KEY; there is no fleet-PAT fallback)"
  log "authenticating gh CLI (token via stdin) ..."
  printf '%s' "$token" | gh auth login --with-token \
    || die "gh auth login failed (bad/expired credential?)"
  log "gh CLI authenticated."
}

provision_fabro() {
  # Hand-provision the fabro server — deliberately NOT `fabro install`:
  # install's GitHub step VALIDATES a static gh token and rejects App
  # installation tokens (ghs_*) by design, while fabro NATIVELY supports
  # GitHub App auth via [server.integrations.github] strategy="app" +
  # app_id with the private key in the GITHUB_APP_PRIVATE_KEY env — fabro
  # then mints and refreshes its OWN installation tokens for its git legs
  # (the github-app-auth Pillar 1 shape at the fabro layer). So the
  # entrypoint writes the non-secret settings plus generated server
  # credentials directly and starts the server:
  #   - settings.toml: dev-token auth, 0.0.0.0:$FABRO_PORT listen (a
  #     published docker port must be reachable from outside the
  #     container; the HOST port stays loopback-bound per README), the
  #     GitHub App integration (app_id only — never a key);
  #   - storage/server.env (0600): generated FABRO_DEV_TOKEN +
  #     SESSION_SECRET — the dev token gates the control plane;
  #   - auth.json (0600): the same dev token for the CLI;
  #   - GITHUB_APP_PRIVATE_KEY + ANTHROPIC_API_KEY (from the env var named
  #     by FABRO_LLM_API_KEY_ENV, unless FABRO_SKIP_LLM) exported into the
  #     server's process env — env only, never argv, never a settings key.
  log "hand-provisioning fabro (dev-token auth + GitHub App integration) ..."
  [ -n "${GITHUB_APP_ID:-}" ] || die "GITHUB_APP_ID is empty; the dispatch target's credential_wrapper must inject it"
  local dev_token session_secret
  dev_token="fabro_dev_$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  session_secret="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  mkdir -p "$HOME/.fabro/storage"
  (
    umask 077
    printf 'FABRO_DEV_TOKEN=%s\nSESSION_SECRET=%s\n' "$dev_token" "$session_secret" \
      > "$HOME/.fabro/storage/server.env"
    printf '{"servers":{"http://127.0.0.1:%s":{"kind":"dev-token","token":"%s","logged_in_at":"%s"}}}\n' \
      "$FABRO_PORT" "$dev_token" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      > "$HOME/.fabro/auth.json"
  )
  cat > "$HOME/.fabro/settings.toml" <<SETTINGS
_version = 1

[cli.target]
type = "http"
url = "http://127.0.0.1:${FABRO_PORT}"

[server.api]
url = "http://127.0.0.1:${FABRO_PORT}/api/v1"

[server.auth]
methods = ["dev-token"]

[server.integrations.github]
strategy = "app"
app_id = "${GITHUB_APP_ID}"

[server.listen]
address = "0.0.0.0:${FABRO_PORT}"
type = "tcp"

[server.web]
enabled = true
url = "http://127.0.0.1:${FABRO_PORT}"
SETTINGS
  export GITHUB_APP_PRIVATE_KEY="$GITHUB_PRIVATE_KEY"
  if [ -z "${FABRO_SKIP_LLM:-}" ]; then
    local key_value="${!FABRO_LLM_API_KEY_ENV:-}"
    if [ -z "$key_value" ]; then
      die "LLM key env '$FABRO_LLM_API_KEY_ENV' is empty; set it or pass FABRO_SKIP_LLM=1"
    fi
    # fabro's LLM provider resolves ANTHROPIC_API_KEY from the server's
    # process env (no on-disk vault write needed).
    export ANTHROPIC_API_KEY="$key_value"
  else
    log "FABRO_SKIP_LLM set — no LLM provider env exported."
  fi
  "$FABRO_BIN" server start --no-upgrade-check || die "fabro server start failed"
  log "fabro server provisioned; settings.toml written."
}

wait_for_fabro_web() {
  # Verify reachability (status code only — never the response body / token).
  local deadline=$((SECONDS + 30))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if curl -s -o /dev/null "http://127.0.0.1:${FABRO_PORT}/"; then
      log "fabro web UI reachable on 0.0.0.0:${FABRO_PORT} (publish to host loopback only)."
      return 0
    fi
    sleep 1
  done
  log "WARNING: fabro web UI not reachable within 30s; check 'fabro server status'."
}

# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
main() {
  start_dockerd
  wait_for_docker

  if [ -n "${ORCHESTRATOR_SKIP_FABRO:-}" ]; then
    log "ORCHESTRATOR_SKIP_FABRO set — skipping fabro provisioning (dockerd-only mode)."
  else
    provision_github
    provision_fabro
    wait_for_fabro_web
  fi

  if [ "$#" -gt 0 ]; then
    log "exec: $1 ..."
    exec "$@"
  fi
  log "no command passed; dropping to an interactive shell."
  log "  run the dispatcher with, e.g.:"
  log "  python3 /workspace/livespec-orchestrator-beads-fabro/.claude-plugin/scripts/bin/dispatcher.py loop --repo /workspace/livespec-orchestrator-beads-fabro --budget 1 --mode shadow --item <id>"
  exec bash
}

main "$@"
