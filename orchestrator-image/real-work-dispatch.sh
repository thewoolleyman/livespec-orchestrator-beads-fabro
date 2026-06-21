#!/usr/bin/env bash
# real-work-dispatch.sh — the W7 step-5 REAL-WORK containerized dispatch path.
#
# This is the production substrate the Dispatcher runs on for routine cross-repo
# work. Unlike tier2-dispatch-proof.sh (which bind-mounted the HOST impl-beads
# checkout and pointed `--repo` at it), this path mounts NO host checkout: every
# git working tree the Dispatcher needs is fresh-`git clone`d from GitHub INSIDE
# the container. So the only host coupling that remains is the EXPLICIT SECRET
# PROVISIONING via `-e VAR` (GitHub token, model keys, tenant Dolt password,
# telemetry key) — no host checkout state leaks in via a bind-mount.
#
# WHAT IS CLONED FRESH IN-CONTAINER
# ---------------------------------
#   1. livespec-orchestrator-beads-fabro ITSELF — the source of the Dispatcher code AND the
#      `.fabro/workflows/implement-work-item/` phase graph. The Dispatcher
#      resolves its package root via `__file__` (dispatcher.py climbs to the
#      repo root, then reads `.fabro/workflows/...`), so it MUST run from a real
#      impl-beads tree. We clone it under /workspace (NOT /tmp — see below) and
#      `uv sync` it so the Python deps resolve. We then regenerate the gitignored
#      `.beads/metadata.json` (a fresh clone carries the committed
#      `.beads/config.yaml` server endpoint but NOT the per-machine
#      metadata.json) via `bd init --server --external` in a scratch dir; the
#      `project_id` is server-stable, so the regenerated value is identical and
#      `bd` then resolves the family tenant.
#   2. The dispatch TARGET repo — the repo whose ready work-item is dispatched.
#      `dispatcher.py loop --repo <target-clone>` keys ledger resolution, the
#      post-merge primary refresh, and the post-merge janitor worktree off this
#      path. Fabro itself clones the target AGAIN fresh inside its sandbox
#      (Architecture C); this clone is the Dispatcher's own host-side venue.
#
# WHY /workspace AND NOT /tmp
# ---------------------------
# The post-merge janitor worktree lands at `<target-clone>/worktrees/janitor-<id>`
# and runs `mise exec -- just check` there. The family pyproject's
# `[tool.coverage.run]` omit carries `/tmp/*`, so a /tmp-rooted checkout would
# omit every source file and false-red a merged-green change with NoDataError
# (work-item livespec-impl-beads-1l6). Both clones therefore live under
# /workspace inside the container.
#
# SECRET HYGIENE (non-negotiable, identical to the sibling live scripts):
# secret env is probed by BYTE COUNT only (`require_env`); tokens flow into
# tools via env / stdin only; clone origins are TOKEN-FREE URLs (Fabro / gh
# supply the credential out of band via the gh credential helper); this script
# never echoes a secret, never prints `git remote -v` / a token-bearing URL /
# env, and redacts long opaque token-shaped runs in any captured output.
#
# Required env, normally supplied by:
#   /data/projects/1password-env-wrapper/with-livespec-env.sh -- <command>
#
#   LIVESPEC_FAMILY_GITHUB_TOKEN
#     (the entrypoint gh-auth's with it; forwarded to the Dispatcher as GH_TOKEN
#      for the in-sandbox PR; also authenticates the in-container fresh clones)
#   ANTHROPIC_API_KEY_LIVESPEC_E2E
#   CLAUDE_CODE_OAUTH_TOKEN
#   BEADS_DOLT_PASSWORD_<target-tenant>   (tenant DB == target repo name)
#   HONEYCOMB_INGEST_KEY_LIVESPEC

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

IMAGE="${IMAGE:-livespec-orchestrator:dev}"
CONTAINER="${CONTAINER:-livespec-orch-realwork}"
VARLIB_VOL="${VARLIB_VOL:-livespec-orch-realwork-varlib}"
FABRO_PORT_WAS_SET="${FABRO_PORT+x}"
FABRO_PORT="${FABRO_PORT:-32276}"
HOST_PUBLISH_PORT="${HOST_PUBLISH_PORT:-32283}"
HOST_FABRO_BIN="${HOST_FABRO_BIN:-$HOME/.fabro/bin/fabro}"

# GitHub org/repo coordinates for the two in-container fresh clones.
DISPATCHER_ORG="${DISPATCHER_ORG:-thewoolleyman}"
DISPATCHER_REPO="${DISPATCHER_REPO:-livespec-orchestrator-beads-fabro}"
TARGET_ORG="${TARGET_ORG:-thewoolleyman}"
TARGET_REPO="${TARGET_REPO:-}"

# In-container clone venues (under /workspace, NOT /tmp — coverage omit guard).
DISPATCHER_CLONE="${DISPATCHER_CLONE:-/workspace/livespec-orchestrator-beads-fabro}"
TARGET_CLONE="${TARGET_CLONE:-/workspace/dispatch-target}"

TIER2_USE_HOST_NETWORK="${TIER2_USE_HOST_NETWORK:-1}"
if [ "$TIER2_USE_HOST_NETWORK" = "1" ] && [ -z "$FABRO_PORT_WAS_SET" ]; then
  FABRO_PORT="$HOST_PUBLISH_PORT"
fi
POLL_ATTEMPTS="${POLL_ATTEMPTS:-80}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-30}"
MODE="${MODE:-autonomous}"
JOURNAL_PATH="${JOURNAL_PATH:-/tmp/livespec-realwork-journal.jsonl}"
LOG_PATH="${LOG_PATH:-/tmp/livespec-realwork-dispatch.log}"

ITEM_ID=""
RUN_DISPATCH=0
BUILD_IMAGE=0
KEEP_CONTAINER=0

usage() {
  cat <<'USAGE'
Usage:
  bash orchestrator-image/real-work-dispatch.sh \
    --target-repo <name> --item <work-item-id> --run

Modes:
  --preflight          Check host/env/image inputs only. Default when --run is absent.
  --run                Start the container and run one real-work dispatch.
  --build-image        Stage the host Fabro binary and build livespec-orchestrator:dev first.
  --keep-container     Leave the container and Docker volume for inspection.

Options:
  --target-repo NAME   Required. The dispatch-target repo name (tenant DB == name).
  --target-org ORG     GitHub org of the target. Default: thewoolleyman.
  --item ID            Required for --run. A ready work-item id in the target ledger.
  --mode MODE          Dispatcher mode: shadow|autonomous. Default: autonomous.
  --image NAME         Docker image tag. Default: livespec-orchestrator:dev.
  --container NAME     Container name. Default: livespec-orch-realwork.
  --host-port PORT     Host loopback port for Fabro UI. Default: 32283.
                      Ignored when TIER2_USE_HOST_NETWORK=1.
  --poll-attempts N    Dispatcher PR-merge poll attempts. Default: 80.

Required env, normally supplied by:
  /data/projects/1password-env-wrapper/with-livespec-env.sh -- <command>

  LIVESPEC_FAMILY_GITHUB_TOKEN
    (forwarded to the Dispatcher as GH_TOKEN for in-sandbox PR creation; also
     authenticates the in-container fresh clones via the gh credential helper)
  ANTHROPIC_API_KEY_LIVESPEC_E2E
  CLAUDE_CODE_OAUTH_TOKEN
  BEADS_DOLT_PASSWORD_<target-tenant>   (tenant DB == --target-repo name; the
     hyphens in the repo name become underscores in the env var name)
  HONEYCOMB_INGEST_KEY_LIVESPEC

The script checks only presence/byte counts for secret env vars; it never prints
secret values, `git remote -v`, token-bearing URLs, or env.
USAGE
}

log() { printf '\n=== %s ===\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# Redact fine-grained PATs and any long opaque token-shaped run.
redact() {
  sed -E 's/github_pat_[A-Za-z0-9_]+/<redacted>/g; s/gh[posu]_[A-Za-z0-9]{16,}/<redacted>/g; s/[A-Za-z0-9_=-]{40,}/<redacted>/g'
}

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

# The bare BEADS_DOLT_PASSWORD the in-container `bd` consumes is derived from the
# target tenant's scoped variable (hyphens in the repo name -> underscores).
TENANT_PASSWORD_VAR=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --) shift;;
    --help|-h) usage; exit 0;;
    --preflight) RUN_DISPATCH=0; shift;;
    --run) RUN_DISPATCH=1; shift;;
    --build-image) BUILD_IMAGE=1; shift;;
    --keep-container) KEEP_CONTAINER=1; shift;;
    --target-repo) TARGET_REPO="${2:-}"; shift 2;;
    --target-org) TARGET_ORG="${2:-}"; shift 2;;
    --item) ITEM_ID="${2:-}"; shift 2;;
    --mode) MODE="${2:-}"; shift 2;;
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
  [ -n "$TARGET_REPO" ] || fail "--target-repo <name> is required"
  # Derive the tenant password env var name from the target repo (tenant DB ==
  # repo name; hyphens -> underscores). NEVER print its value — byte count only.
  TENANT_PASSWORD_VAR="BEADS_DOLT_PASSWORD_$(printf '%s' "$TARGET_REPO" | tr '-' '_')"
  require_env LIVESPEC_FAMILY_GITHUB_TOKEN
  require_env ANTHROPIC_API_KEY_LIVESPEC_E2E
  require_env CLAUDE_CODE_OAUTH_TOKEN
  require_env "$TENANT_PASSWORD_VAR"
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
  case "$MODE" in
    shadow|autonomous) ;;
    *) fail "unknown --mode: $MODE (expected shadow|autonomous)";;
  esac
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
  log "starting $CONTAINER from $IMAGE (NO host checkout bind-mount)"
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
  # The ONLY host coupling is the explicit `-e` secret set: NO `-v <host-repo>`
  # checkout bind-mount. The varlib volume is the ext4-backed inner graph store,
  # not host checkout state.
  docker run -d --name "$CONTAINER" \
    --privileged \
    --cgroupns=host \
    "${network_args[@]}" \
    -v "$VARLIB_VOL:/var/lib/docker" \
    "${publish_args[@]}" \
    -e FABRO_PORT="$FABRO_PORT" \
    -e LIVESPEC_FAMILY_GITHUB_TOKEN \
    -e ANTHROPIC_API_KEY_LIVESPEC_E2E \
    -e CLAUDE_CODE_OAUTH_TOKEN \
    -e "$TENANT_PASSWORD_VAR" \
    -e BEADS_DOLT_PASSWORD="${!TENANT_PASSWORD_VAR}" \
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

# Fresh-clone a GitHub repo INSIDE the container from a TOKEN-FREE origin URL.
# The container entrypoint already `gh auth login`ed from
# LIVESPEC_FAMILY_GITHUB_TOKEN and wired `gh auth setup-git`, so raw `git clone`
# of an https://github.com/<org>/<repo>.git URL authenticates with the stored
# credential — the URL itself carries NO token (secret hygiene).
clone_in_container() {
  local org="$1" repo="$2" dest="$3"
  log "fresh-cloning $org/$repo -> $dest (in-container, token-free origin)"
  docker exec "$CONTAINER" sh -lc 'gh auth setup-git' >/dev/null 2>&1 \
    || fail "gh auth setup-git failed in-container; fresh clones cannot authenticate"
  docker exec "$CONTAINER" rm -rf "$dest"
  docker exec "$CONTAINER" mkdir -p "$(dirname "$dest")"
  # NOTE: the URL is token-free; the credential comes from the gh helper. Any
  # clone progress chatter is redacted on its way to the operator's terminal.
  docker exec "$CONTAINER" sh -lc \
    'git clone "https://github.com/$1/$2.git" "$3"' \
    sh "$org" "$repo" "$dest" 2>&1 | redact
  docker exec "$CONTAINER" git config --global --add safe.directory "$dest"
  docker exec "$CONTAINER" git -C "$dest" status --short --branch >/dev/null
}

# `uv sync` the freshly-cloned impl-beads tree so the Dispatcher's Python deps
# resolve from the clone (the image ships uv + mise but the cloned tree's
# environment is created here).
sync_dispatcher_deps() {
  log "uv sync the cloned dispatcher tree ($DISPATCHER_CLONE)"
  docker exec -w "$DISPATCHER_CLONE" "$CONTAINER" sh -lc \
    'mise trust >/dev/null 2>&1 || true; uv sync --all-groups' 2>&1 | redact
}

# Regenerate the gitignored .beads/metadata.json inside a CLONE. A fresh clone
# carries the committed .beads/config.yaml (server endpoint) but NOT
# metadata.json, and `bd list` without metadata.json fails with "no beads
# database found". `bd init --server --external` re-derives the SERVER-STABLE
# project_id (identical across clones) and writes metadata.json; thereafter `bd`
# resolves the family tenant from config.yaml + the BEADS_DOLT_PASSWORD env var.
#
# Two hardenings learned from in-container validation:
#   - `bd init` silently falls to EMBEDDED mode (provisioning .beads/dolt/ +
#     .beads/embeddeddolt/) if the .beads/ dir already carries embedded-store
#     artifacts. A truly fresh clone has only config.yaml + .gitignore tracked,
#     so we assert no embedded store is present before init and treat its
#     appearance as a hard failure (it would shadow the family tenant with an
#     empty local store).
#   - `bd init` AUTO-COMMITS its tracked .beads changes onto the clone's master
#     (leaving it `ahead 1` of origin/master), which would later break the
#     dispatcher's post-merge `git pull --ff-only origin master`. The
#     gitignored metadata.json survives a hard reset, so we drop that auto-commit
#     by resetting the clone to origin/master after init.
regen_beads_metadata() {
  local clone="$1" tenant="$2"
  log "regenerating .beads/metadata.json in $clone (tenant $tenant; project_id is server-stable)"
  docker exec -w "$clone" "$CONTAINER" sh -lc '
    set -e
    [ -f .beads/config.yaml ] || { echo "ERROR: clone lacks .beads/config.yaml: $0" >&2; exit 1; }
    if [ -f .beads/metadata.json ]; then
      echo "metadata.json already present; leaving as-is"
      exit 0
    fi
    if [ -d .beads/embeddeddolt ] || [ -d .beads/dolt ]; then
      echo "ERROR: .beads/ already carries an embedded Dolt store; refusing to init (would shadow the family tenant): $0" >&2
      exit 1
    fi
    bd init \
      --server --external \
      --server-host 127.0.0.1 \
      --server-port 3307 \
      --server-user "$1" \
      --database "$1" \
      --prefix "$1" \
      --skip-agents --skip-hooks --non-interactive --quiet >/dev/null 2>&1
    [ -f .beads/metadata.json ] || { echo "ERROR: bd init did not produce metadata.json" >&2; exit 1; }
    if [ -d .beads/embeddeddolt ]; then
      echo "ERROR: bd init fell to EMBEDDED mode (empty local store would shadow the family tenant): $0" >&2
      exit 1
    fi
    # Drop the bd-init auto-commit so the clone matches origin/master; the
    # gitignored metadata.json survives the reset.
    git reset --hard origin/master >/dev/null 2>&1 || true
    [ -f .beads/metadata.json ] || { echo "ERROR: metadata.json lost after reset" >&2; exit 1; }
    echo "metadata.json regenerated; clone reset to origin/master"
  ' "$clone" "$tenant" 2>&1 | redact
}

provision_clones() {
  clone_in_container "$DISPATCHER_ORG" "$DISPATCHER_REPO" "$DISPATCHER_CLONE"
  sync_dispatcher_deps
  clone_in_container "$TARGET_ORG" "$TARGET_REPO" "$TARGET_CLONE"
  # The target ledger is the family tenant named after the target repo. The
  # dispatcher resolves the ledger against the target clone's cwd, so its
  # metadata.json must exist.
  regen_beads_metadata "$TARGET_CLONE" "$TARGET_REPO"
}

run_dispatch() {
  log "running one real-work dispatch (mode=$MODE) against $TARGET_ORG/$TARGET_REPO item $ITEM_ID"
  docker exec "$CONTAINER" mkdir -p "$(dirname "$JOURNAL_PATH")"
  set +e
  # The Dispatcher script is invoked by its ABSOLUTE path under the FRESH
  # impl-beads clone, so its package-root resolution (the .fabro/workflows graph,
  # via __file__) points at the clone. `--repo` is the FRESH target clone:
  # ledger resolution, post-merge primary refresh, and the janitor worktree all
  # key off it. GH_TOKEN is projected for the in-sandbox PR leg only.
  docker exec \
    -w "$TARGET_CLONE" \
    "$CONTAINER" \
    sh -lc 'export GH_TOKEN="$LIVESPEC_FAMILY_GITHUB_TOKEN"; exec python3 "$1/.claude-plugin/scripts/bin/dispatcher.py" \
      loop \
      --repo "$2" \
      --budget 1 \
      --mode "$3" \
      --item "$4" \
      --journal "$5" \
      --poll-attempts "$6" \
      --poll-interval-seconds "$7" \
      --json' \
      sh "$DISPATCHER_CLONE" "$TARGET_CLONE" "$MODE" "$ITEM_ID" "$JOURNAL_PATH" "$POLL_ATTEMPTS" "$POLL_INTERVAL_SECONDS" \
      >"$LOG_PATH" 2>&1
  local code=$?
  set -e
  redact <"$LOG_PATH" | tail -80
  printf 'dispatcher exit code: %s\n' "$code"
  docker exec "$CONTAINER" test -s "$JOURNAL_PATH" \
    || fail "dispatcher did not write a journal at $JOURNAL_PATH"
  log "journal tail (redacted)"
  docker exec "$CONTAINER" tail -20 "$JOURNAL_PATH" | redact
  log "inner docker containers after dispatch"
  docker exec "$CONTAINER" docker ps -a --format '{{.Names}} {{.Image}} {{.Status}}' \
    | redact || true
  return "$code"
}

preflight
if [ "$RUN_DISPATCH" -eq 0 ]; then
  log "preflight complete"
  printf 'rerun with --run --target-repo <name> --item <ready-item> to dispatch real work\n'
  exit 0
fi

start_container
prove_inner_daemon
provision_clones
run_dispatch
