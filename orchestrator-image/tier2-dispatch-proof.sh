#!/usr/bin/env bash
# tier2-dispatch-proof.sh - run the W7 Tier-2 containerized dispatch proof.
#
# This is the step after `build-and-verify.sh`: it starts the production
# orchestrator image, lets the entrypoint provision inner dockerd + Fabro, then
# runs one explicitly named dispatcher item from inside the container. It never
# creates a work-item and never selects from the ready queue; the operator must
# supply a deliberately tiny, isolated item id.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"

IMAGE="${IMAGE:-livespec-orchestrator:dev}"
CONTAINER="${CONTAINER:-livespec-orch-tier2}"
VARLIB_VOL="${VARLIB_VOL:-livespec-orch-tier2-varlib}"
FABRO_PORT_WAS_SET="${FABRO_PORT+x}"
FABRO_PORT="${FABRO_PORT:-32276}"
HOST_PUBLISH_PORT="${HOST_PUBLISH_PORT:-32281}"
HOST_FABRO_BIN="${HOST_FABRO_BIN:-$HOME/.fabro/bin/fabro}"
MOUNT_REPO="${MOUNT_REPO:-$REPO_ROOT}"
WORKSPACE_REPO="${WORKSPACE_REPO:-/workspace/livespec-impl-beads}"
TIER2_USE_HOST_NETWORK="${TIER2_USE_HOST_NETWORK:-1}"
if [ "$TIER2_USE_HOST_NETWORK" = "1" ] && [ -z "$FABRO_PORT_WAS_SET" ]; then
  FABRO_PORT="$HOST_PUBLISH_PORT"
fi
POLL_ATTEMPTS="${POLL_ATTEMPTS:-3}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-10}"
JOURNAL_PATH="${JOURNAL_PATH:-/tmp/livespec-tier2-dispatch-journal.jsonl}"
LOG_PATH="${LOG_PATH:-/tmp/livespec-tier2-dispatch.log}"

ITEM_ID=""
RUN_DISPATCH=0
BUILD_IMAGE=0
KEEP_CONTAINER=0

usage() {
  cat <<'USAGE'
Usage:
  bash orchestrator-image/tier2-dispatch-proof.sh --item <work-item-id> --run

Modes:
  --preflight          Check host/env/image inputs only. Default when --run is absent.
  --run                Start the container and run one explicit shadow dispatch.
  --build-image        Stage the host Fabro binary and build livespec-orchestrator:dev first.
  --keep-container     Leave the container and Docker volume for inspection.

Options:
  --item ID            Required for --run. Use a tiny, isolated ready work item.
  --image NAME         Docker image tag. Default: livespec-orchestrator:dev.
  --container NAME     Container name. Default: livespec-orch-tier2.
  --host-port PORT     Host loopback port for Fabro UI. Default: 32281.
                      Ignored when TIER2_USE_HOST_NETWORK=1.
  --poll-attempts N    Dispatcher PR poll attempts. Default: 3.

Required env, normally supplied by:
  /data/projects/1password-env-wrapper/with-livespec-env.sh -- <command>

  LIVESPEC_FAMILY_GITHUB_TOKEN
    (forwarded to the Dispatcher as GH_TOKEN for in-sandbox PR creation)
  ANTHROPIC_API_KEY_LIVESPEC_E2E
  CLAUDE_CODE_OAUTH_TOKEN
  BEADS_DOLT_PASSWORD_livespec_impl_beads
  HONEYCOMB_INGEST_KEY_LIVESPEC

The script checks only presence/byte counts for secret env vars; it never prints
secret values.
USAGE
}

log() { printf '\n=== %s ===\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

cleanup() {
  if [ "$KEEP_CONTAINER" -eq 0 ]; then
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    docker volume rm "$VARLIB_VOL" >/dev/null 2>&1 || true
  else
    printf 'kept container=%s volume=%s\n' "$CONTAINER" "$VARLIB_VOL" >&2
  fi
  rm -f "$HERE/fabro" || true
}
trap cleanup EXIT

while [ "$#" -gt 0 ]; do
  case "$1" in
    --) shift;;
    --help|-h) usage; exit 0;;
    --preflight) RUN_DISPATCH=0; shift;;
    --run) RUN_DISPATCH=1; shift;;
    --build-image) BUILD_IMAGE=1; shift;;
    --keep-container) KEEP_CONTAINER=1; shift;;
    --item) ITEM_ID="${2:-}"; shift 2;;
    --image) IMAGE="${2:-}"; shift 2;;
    --container) CONTAINER="${2:-}"; shift 2;;
    --host-port) HOST_PUBLISH_PORT="${2:-}"; shift 2;;
    --poll-attempts) POLL_ATTEMPTS="${2:-}"; shift 2;;
    *) fail "unknown argument: $1";;
  esac
done

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"
}

require_env() {
  local name="$1"
  local value="${!name:-}"
  if [ -z "$value" ]; then
    fail "required env var is not set: $name"
  fi
  printf '%s present (%s bytes)\n' "$name" "$(printf '%s' "$value" | wc -c | tr -d ' ')"
}

stage_and_build_image() {
  log "staging Fabro binary and building $IMAGE"
  [ -x "$HOST_FABRO_BIN" ] || fail "fabro binary not found at $HOST_FABRO_BIN"
  cp "$HOST_FABRO_BIN" "$HERE/fabro"
  chmod +x "$HERE/fabro"
  "$HERE/fabro" version | head -1
  docker build -t "$IMAGE" "$HERE"
}

preflight() {
  log "preflight"
  require_command docker
  require_command curl
  docker info >/dev/null 2>&1 || fail "docker is not reachable from the host"
  [ -e "$MOUNT_REPO/.git" ] || fail "MOUNT_REPO is not a git checkout: $MOUNT_REPO"
  [ -f "$MOUNT_REPO/.livespec.jsonc" ] || fail "MOUNT_REPO lacks .livespec.jsonc: $MOUNT_REPO"
  [ -f "$MOUNT_REPO/.beads/config.yaml" ] || fail "MOUNT_REPO lacks .beads/config.yaml: $MOUNT_REPO"
  [ -f "$MOUNT_REPO/.beads/metadata.json" ] || fail "MOUNT_REPO lacks .beads/metadata.json: $MOUNT_REPO"
  require_env LIVESPEC_FAMILY_GITHUB_TOKEN
  require_env ANTHROPIC_API_KEY_LIVESPEC_E2E
  require_env CLAUDE_CODE_OAUTH_TOKEN
  require_env BEADS_DOLT_PASSWORD_livespec_impl_beads
  require_env HONEYCOMB_INGEST_KEY_LIVESPEC
  if [ "$BUILD_IMAGE" -eq 1 ]; then
    stage_and_build_image
  elif docker image inspect "$IMAGE" >/dev/null 2>&1; then
    printf 'image present: %s\n' "$IMAGE"
  else
    fail "image not present: $IMAGE (rerun with --build-image or build-and-verify.sh first)"
  fi
  if [ "$RUN_DISPATCH" -eq 1 ] && [ -z "$ITEM_ID" ]; then
    fail "--item is required with --run"
  fi
}

wait_for_container() {
  log "waiting for inner dockerd and Fabro provisioning"
  for _ in $(seq 1 90); do
    if docker exec "$CONTAINER" docker info >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  docker exec "$CONTAINER" docker info >/dev/null 2>&1 \
    || fail "inner docker daemon did not become healthy"
  for _ in $(seq 1 90); do
    if docker exec "$CONTAINER" test -f /root/.fabro/settings.toml; then
      break
    fi
    sleep 1
  done
  docker exec "$CONTAINER" test -f /root/.fabro/settings.toml \
    || fail "fabro settings were not provisioned"
}

start_container() {
  log "starting $CONTAINER from $IMAGE"
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  docker volume rm "$VARLIB_VOL" >/dev/null 2>&1 || true
  docker volume create "$VARLIB_VOL" >/dev/null
  local network_args=()
  local publish_args=()
  if [ "$TIER2_USE_HOST_NETWORK" = "1" ]; then
    # The committed .beads/config.yaml points at the host Dolt sql-server on
    # 127.0.0.1:3307. Host networking preserves that loopback meaning inside
    # the orchestrator container; no host Docker socket is mounted.
    network_args=(--network host)
  else
    publish_args=(-p "127.0.0.1:${HOST_PUBLISH_PORT}:${FABRO_PORT}")
  fi
  docker run -d --name "$CONTAINER" \
    --privileged \
    --cgroupns=host \
    "${network_args[@]}" \
    -v "$VARLIB_VOL:/var/lib/docker" \
    -v "$MOUNT_REPO:$WORKSPACE_REPO:ro" \
    "${publish_args[@]}" \
    -e FABRO_PORT="$FABRO_PORT" \
    -e LIVESPEC_FAMILY_GITHUB_TOKEN \
    -e ANTHROPIC_API_KEY_LIVESPEC_E2E \
    -e CLAUDE_CODE_OAUTH_TOKEN \
    -e BEADS_DOLT_PASSWORD_livespec_impl_beads \
    -e BEADS_DOLT_PASSWORD="$BEADS_DOLT_PASSWORD_livespec_impl_beads" \
    -e HONEYCOMB_INGEST_KEY_LIVESPEC \
    "$IMAGE" \
    sleep infinity >/dev/null
  wait_for_container
}

prove_inner_daemon() {
  log "inner docker daemon proof"
  local driver
  driver="$(docker exec "$CONTAINER" docker info --format '{{.Driver}}')"
  printf 'inner storage driver: %s\n' "$driver"
  case "$driver" in
    overlay2|overlayfs) ;;
    *) fail "unexpected inner storage driver: $driver";;
  esac
  printf 'host docker socket mounted into container: '
  if docker exec "$CONTAINER" test -S /host/var/run/docker.sock; then
    fail "unexpected host docker socket path exists"
  fi
  printf 'no\n'
}

trust_mounted_repo() {
  log "trusting mounted repo for in-container git discovery"
  docker exec "$CONTAINER" git config --global --add safe.directory "$WORKSPACE_REPO"
  docker exec "$CONTAINER" git -C "$WORKSPACE_REPO" status --short --branch >/dev/null
}

run_dispatch() {
  log "running one explicit shadow dispatch"
  docker exec "$CONTAINER" mkdir -p "$(dirname "$JOURNAL_PATH")"
  set +e
  docker exec \
    -w "$WORKSPACE_REPO" \
    "$CONTAINER" \
    sh -lc 'export GH_TOKEN="$LIVESPEC_FAMILY_GITHUB_TOKEN"; exec python3 "$1/.claude-plugin/scripts/bin/dispatcher.py" \
      loop \
      --repo "$1" \
      --budget 1 \
      --mode shadow \
      --item "$2" \
      --no-close-on-merge \
      --journal "$3" \
      --poll-attempts "$4" \
      --poll-interval-seconds "$5" \
      --json' \
      sh "$WORKSPACE_REPO" "$ITEM_ID" "$JOURNAL_PATH" "$POLL_ATTEMPTS" "$POLL_INTERVAL_SECONDS" \
      >"$LOG_PATH" 2>&1
  local code=$?
  set -e
  sed -E 's/[A-Za-z0-9_=-]{32,}/<redacted>/g' "$LOG_PATH" | tail -80
  printf 'dispatcher exit code: %s\n' "$code"
  docker exec "$CONTAINER" test -s "$JOURNAL_PATH" \
    || fail "dispatcher did not write a journal at $JOURNAL_PATH"
  log "journal tail (redacted)"
  docker exec "$CONTAINER" tail -20 "$JOURNAL_PATH" \
    | sed -E 's/[A-Za-z0-9_=-]{32,}/<redacted>/g'
  log "inner docker containers after dispatch"
  docker exec "$CONTAINER" docker ps -a --format '{{.Names}} {{.Image}} {{.Status}}' \
    | sed -E 's/[A-Za-z0-9_=-]{32,}/<redacted>/g' || true
  return "$code"
}

preflight
if [ "$RUN_DISPATCH" -eq 0 ]; then
  log "preflight complete"
  printf 'rerun with --run --item <tiny-ready-item> to execute the Tier-2 proof\n'
  exit 0
fi

start_container
prove_inner_daemon
trust_mounted_repo
run_dispatch
