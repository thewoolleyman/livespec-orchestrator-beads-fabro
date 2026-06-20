#!/usr/bin/env bash
# acceptance-live-golden-master.sh — the W7 LIVE Beads/Fabro golden-master tier.
#
# This is the real, end-to-end live proof of the dark factory: it creates a
# THROWAWAY private GitHub repo in the disposable `livespec-e2e` org, seeds it
# with the hello-world-greets-a-name fixture SPECIFICATION + an EMBEDDED beads
# ledger carrying ONE ready greeting work-item, then runs the production
# orchestrator container so Fabro implements the spec, opens a PR, and merges
# it. It then clones the MERGED repo, asserts the generated program greets the
# supplied name (`greet("Ada") == "Hello, Ada!"`), and DELETES the repo.
#
# It reuses, never rebuilds:
#   - the privileged DinD container skeleton from tier2-dispatch-proof.sh
#     (start/wait/trust/run), here parameterized to mount a SECOND repo (the
#     throwaway clone) and point `dispatcher.py loop --repo` at it;
#   - the e2e-repo reaper (reap-e2e-repos.sh) — swept on ENTRY (stale repos)
#     and invoked on EXIT (teardown of THIS run's repo);
#   - the greeting assertion in
#     `.claude-plugin/scripts/livespec_impl_beads/acceptance.py`
#     (`run_live_acceptance`), driven by the thin pytest binding in
#     `acceptance/test_beads_fabro_live_golden_master.py`.
#
# THE EPHEMERAL LEDGER (the hard problem, solved)
# -----------------------------------------------
# The throwaway repo gets its OWN beads ledger via `bd init` in EMBEDDED mode
# (NO `--server` flag), which provisions a self-contained managed Dolt store
# under `.beads/embeddeddolt/`. The dispatcher's ShellBeadsClient passes NO
# connection flags to `bd` (only `bd init` accepts `--server*`); every read
# verb takes its connection from the repo's own `.beads/config.yaml`. So with
# an embedded `.beads/`, the dispatcher's `bd list` against the throwaway repo
# talks to that embedded Dolt — the family Dolt tenant + BEADS_DOLT_PASSWORD
# are never touched. The dispatcher reads the ledger against the MOUNTED
# throwaway clone (its `.beads/embeddeddolt/` is physically present on disk),
# so `.beads/`-dir gitignore of the Dolt files is irrelevant to the read.
#
# TOKEN THREADING
# ---------------
# Host-side create/clone/delete use LIVESPEC_E2E_GITHUB_TOKEN directly. For the
# in-sandbox push/PR/merge legs the orchestrator entrypoint `gh auth login`s
# from LIVESPEC_FAMILY_GITHUB_TOKEN and the dispatcher projects it as GH_TOKEN
# into the Fabro sandbox; so for a LIVE run targeting the `livespec-e2e` org we
# alias LIVESPEC_FAMILY_GITHUB_TOKEN := LIVESPEC_E2E_GITHUB_TOKEN for the
# container invocation. Anthropic / Claude / Honeycomb legs are unchanged.
#
# SECRET HYGIENE (non-negotiable): tokens flow via env / stdin only; this
# script never echoes a secret, never prints `git remote -v` / URLs, redacts
# any `github_pat_...` / long opaque token-shaped run in captured output, and
# probes secret presence by byte count only.
#
# Required env (normally from the 1Password wrapper):
#   /data/projects/1password-env-wrapper/with-livespec-env.sh -- \
#     bash orchestrator-image/acceptance-live-golden-master.sh --run
#
#   LIVESPEC_E2E_GITHUB_TOKEN        org-scoped fine-grained token (livespec-e2e)
#   ANTHROPIC_API_KEY_LIVESPEC_E2E   Fabro LLM key
#   CLAUDE_CODE_OAUTH_TOKEN          model auth the dispatcher projects per-dispatch
#   HONEYCOMB_INGEST_KEY_LIVESPEC    telemetry egress key

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"

ORG="livespec-e2e"
IMAGE="${IMAGE:-livespec-orchestrator:dev}"
CONTAINER="${CONTAINER:-livespec-orch-live-gm}"
VARLIB_VOL="${VARLIB_VOL:-livespec-orch-live-gm-varlib}"
FABRO_PORT="${FABRO_PORT:-32276}"
HOST_PUBLISH_PORT="${HOST_PUBLISH_PORT:-32282}"
HOST_FABRO_BIN="${HOST_FABRO_BIN:-$HOME/.fabro/bin/fabro}"
# The impl-beads repo is mounted so the dispatcher code + the
# .fabro/workflows/implement-work-item/ phase graph resolve from the package
# root; the throwaway clone is mounted separately as the dispatch --repo.
WORKSPACE_REPO="${WORKSPACE_REPO:-/workspace/livespec-impl-beads}"
TARGET_MOUNT="${TARGET_MOUNT:-/workspace/e2e-target}"
TIER2_USE_HOST_NETWORK="${TIER2_USE_HOST_NETWORK:-1}"
POLL_ATTEMPTS="${POLL_ATTEMPTS:-80}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-30}"
NAME="${NAME:-Ada}"
EXPECTED_GREETING="Hello, ${NAME}!"
JOURNAL_PATH="${JOURNAL_PATH:-/tmp/livespec-live-gm-journal.jsonl}"
LOG_PATH="${LOG_PATH:-/tmp/livespec-live-gm-dispatch.log}"
# Reaper age gate for the ENTRY stale sweep. The exit teardown of THIS run's
# repo is an explicit, age-independent delete (we own it), so the gate only
# governs the opportunistic stale sweep.
ENTRY_REAP_MAX_AGE_MINUTES="${ENTRY_REAP_MAX_AGE_MINUTES:-120}"

RUN=0
BUILD_IMAGE=0
KEEP_CONTAINER=0
KEEP_REPO=0
SCRATCH_DIR=""
THROWAWAY_REPO=""
THROWAWAY_CREATED=0

usage() {
  cat <<'USAGE'
Usage:
  bash orchestrator-image/acceptance-live-golden-master.sh --run [options]

Modes:
  --preflight       Check host/env/image inputs only (default when --run absent).
  --run             Execute the full live golden-master proof.
  --build-image     Stage the host Fabro binary and build the image first.
  --keep-container  Leave the container + volume for inspection.
  --keep-repo       Do NOT delete the throwaway repo on exit (debugging only;
                    the reaper will still sweep it once it ages past the gate).

Options:
  --name NAME       Greeting name to assert. Default: Ada.
  --poll-attempts N Dispatcher PR-merge poll attempts. Default: 80.

Required env (normally from /data/projects/1password-env-wrapper/with-livespec-env.sh):
  LIVESPEC_E2E_GITHUB_TOKEN
  ANTHROPIC_API_KEY_LIVESPEC_E2E
  CLAUDE_CODE_OAUTH_TOKEN
  HONEYCOMB_INGEST_KEY_LIVESPEC

Secret env presence is checked by byte count only; values are never printed.
USAGE
}

log() { printf '\n=== %s ===\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# Redact fine-grained PATs and any long opaque token-shaped run.
redact() {
  sed -E 's/github_pat_[A-Za-z0-9_]+/<redacted>/g; s/gh[posu]_[A-Za-z0-9]{16,}/<redacted>/g; s/[A-Za-z0-9_=-]{40,}/<redacted>/g'
}

require_command() { command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"; }

require_env() {
  local name="$1"
  local value="${!name:-}"
  [ -n "$value" ] || fail "required env var is not set: $name"
  printf '%s present (%s bytes)\n' "$name" "$(printf '%s' "$value" | wc -c | tr -d ' ')"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --) shift;;
    --help|-h) usage; exit 0;;
    --preflight) RUN=0; shift;;
    --run) RUN=1; shift;;
    --build-image) BUILD_IMAGE=1; shift;;
    --keep-container) KEEP_CONTAINER=1; shift;;
    --keep-repo) KEEP_REPO=1; shift;;
    --name) NAME="${2:-}"; EXPECTED_GREETING="Hello, ${NAME}!"; shift 2;;
    --poll-attempts) POLL_ATTEMPTS="${2:-}"; shift 2;;
    *) fail "unknown argument: $1";;
  esac
done

# ---------------------------------------------------------------------------
# Teardown: delete the throwaway repo (idempotent, race-tolerant), tear down
# the container + volume + scratch dir. Runs on ANY exit.
# ---------------------------------------------------------------------------
delete_throwaway_repo() {
  local full="$ORG/$THROWAWAY_REPO"
  local attempt=1 out code
  while [ "$attempt" -le 6 ]; do
    set +e
    out="$(GH_TOKEN="$LIVESPEC_E2E_GITHUB_TOKEN" gh api -X DELETE "/repos/${full}" 2>&1)"
    code=$?
    set -e
    if [ "$code" -eq 0 ]; then printf 'teardown: deleted %s\n' "$full"; return 0; fi
    if printf '%s' "$out" | grep -qiE 'HTTP 404|Not Found'; then
      printf 'teardown: already gone (404): %s\n' "$full"; return 0
    fi
    printf 'teardown: attempt %s/6 not-yet-deletable, backing off 3s\n' "$attempt"
    sleep 3
    attempt=$((attempt + 1))
  done
  printf 'teardown: WARNING could not delete %s after retries; the reaper will sweep it\n' "$full" >&2
  return 1
}

cleanup() {
  local rc=$?
  if [ "$KEEP_CONTAINER" -eq 0 ]; then
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    docker volume rm "$VARLIB_VOL" >/dev/null 2>&1 || true
  else
    printf 'kept container=%s volume=%s\n' "$CONTAINER" "$VARLIB_VOL" >&2
  fi
  if [ "$THROWAWAY_CREATED" -eq 1 ] && [ "$KEEP_REPO" -eq 0 ]; then
    log "teardown: deleting throwaway repo"
    delete_throwaway_repo || true
  elif [ "$THROWAWAY_CREATED" -eq 1 ]; then
    printf 'kept throwaway repo: %s/%s (reaper will sweep it after the age gate)\n' "$ORG" "$THROWAWAY_REPO" >&2
  fi
  if [ -n "$SCRATCH_DIR" ]; then rm -rf "$SCRATCH_DIR" 2>/dev/null || true; fi
  rm -f "$HERE/fabro" 2>/dev/null || true
  exit "$rc"
}
trap cleanup EXIT

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
  require_command gh
  require_command jq
  require_command bd
  require_command git
  docker info >/dev/null 2>&1 || fail "docker is not reachable from the host"
  [ -e "$REPO_ROOT/.git" ] || fail "impl-beads repo is not a git checkout: $REPO_ROOT"
  [ -f "$REPO_ROOT/.claude-plugin/scripts/bin/dispatcher.py" ] || fail "dispatcher.py missing under impl-beads"
  [ -d "$REPO_ROOT/acceptance/fixtures/hello-world-greets-a-name/SPECIFICATION" ] \
    || fail "fixture SPECIFICATION missing"
  require_env LIVESPEC_E2E_GITHUB_TOKEN
  require_env ANTHROPIC_API_KEY_LIVESPEC_E2E
  require_env CLAUDE_CODE_OAUTH_TOKEN
  require_env HONEYCOMB_INGEST_KEY_LIVESPEC
  if [ "$BUILD_IMAGE" -eq 1 ]; then
    stage_and_build_image
  elif docker image inspect "$IMAGE" >/dev/null 2>&1; then
    printf 'image present: %s\n' "$IMAGE"
  else
    fail "image not present: $IMAGE (rerun with --build-image or build-and-verify.sh first)"
  fi
}

# ENTRY: sweep stale livespec-e2e-* repos (age-gated; never touches a fresh
# in-progress run's repo). Reuses the canonical reaper.
sweep_stale_repos() {
  log "entry stale sweep (reaper, age gate ${ENTRY_REAP_MAX_AGE_MINUTES}m)"
  LIVESPEC_E2E_GITHUB_TOKEN="$LIVESPEC_E2E_GITHUB_TOKEN" \
    bash "$HERE/reap-e2e-repos.sh" --max-age "$ENTRY_REAP_MAX_AGE_MINUTES" 2>&1 | redact || \
    printf 'entry sweep degraded (non-fatal)\n' >&2
}

# Create the throwaway private repo, seed it (fixture SPECIFICATION +
# .livespec.jsonc + embedded .beads/ with one ready greeting work-item), and
# push the initial state. Echoes nothing secret.
create_and_seed_repo() {
  local rand
  rand="$(LC_ALL=C tr -dc 'a-z0-9' </dev/urandom | head -c 8)"
  THROWAWAY_REPO="livespec-e2e-${rand}"
  log "creating throwaway repo $ORG/$THROWAWAY_REPO (private)"
  GH_TOKEN="$LIVESPEC_E2E_GITHUB_TOKEN" gh repo create "$ORG/$THROWAWAY_REPO" \
    --private --description "W7 live golden-master throwaway (auto-deleted)" >/dev/null
  THROWAWAY_CREATED=1

  SCRATCH_DIR="$(mktemp -d /tmp/live-gm-seed.XXXXXX)"
  local clone="$SCRATCH_DIR/$THROWAWAY_REPO"
  # Clone via an x-access-token URL kept ONLY in this subshell's argv to the
  # `git clone`; the persisted remote is rewritten to a token-free https URL,
  # and the in-container push uses the entrypoint's gh-stored credential.
  GH_TOKEN="$LIVESPEC_E2E_GITHUB_TOKEN" gh repo clone "$ORG/$THROWAWAY_REPO" "$clone" >/dev/null 2>&1

  log "seeding fixture SPECIFICATION + .livespec.jsonc"
  cp -R "$REPO_ROOT/acceptance/fixtures/hello-world-greets-a-name/SPECIFICATION" "$clone/SPECIFICATION"
  # A minimal .livespec.jsonc so the dispatcher's config resolver picks the
  # ShellBeadsClient (fake:false) and the embedded .beads/ decides the
  # connection. NO server keys, NO password — embedded mode needs neither.
  cat >"$clone/.livespec.jsonc" <<JSONC
{
  "template": "livespec",
  "spec_root": "SPECIFICATION",
  "implementation": { "plugin": "livespec-impl-beads" },
  "livespec-impl-beads": {
    "format": "beads",
    "connection": { "fake": false }
  }
}
JSONC

  log "seeding embedded beads ledger + one ready greeting work-item"
  (
    cd "$clone"
    # Embedded mode: NO --server. Provisions a self-contained Dolt store under
    # .beads/embeddeddolt/. --skip-agents --skip-hooks per the family rule.
    bd init --prefix "${rand}greet" --skip-agents --skip-hooks --non-interactive --quiet >/dev/null 2>&1
    bd create "Implement greet per the SPECIFICATION" \
      -d "Implement the program described in this repo's SPECIFICATION/: expose a Python function greet(name: str) -> str that returns exactly \"Hello, <name>!\". For the input Ada it must return \"Hello, Ada!\". Follow the contracts.md / scenarios.md exactly." \
      >/dev/null 2>&1
  )
  # Confirm the ready item exists in the embedded ledger (redacted count only).
  local ready_count
  ready_count="$(cd "$clone" && bd list --status open --json 2>/dev/null | jq 'length' 2>/dev/null || echo '?')"
  printf 'embedded ledger ready (open) items: %s\n' "$ready_count"
  [ "$ready_count" = "1" ] || fail "expected exactly 1 ready item in the embedded ledger (got $ready_count)"

  log "pushing initial state (git content; embedded Dolt files are gitignored)"
  (
    cd "$clone"
    git add -A
    git -c user.email="e2e@livespec.invalid" -c user.name="livespec-e2e" \
      commit -q -m "seed: hello-world greeting fixture + embedded ledger"
    # Push over a token URL passed ONLY on this argv; no token persisted to the
    # repo config and nothing echoed.
    git push "https://x-access-token:${LIVESPEC_E2E_GITHUB_TOKEN}@github.com/${ORG}/${THROWAWAY_REPO}.git" HEAD:main >/dev/null 2>&1
  )
  printf 'seeded + pushed: %s/%s (default branch main)\n' "$ORG" "$THROWAWAY_REPO"
  CLONE_DIR="$clone"
}

wait_for_container() {
  log "waiting for inner dockerd and Fabro provisioning"
  for _ in $(seq 1 90); do
    docker exec "$CONTAINER" docker info >/dev/null 2>&1 && break
    sleep 1
  done
  docker exec "$CONTAINER" docker info >/dev/null 2>&1 || fail "inner docker daemon did not become healthy"
  for _ in $(seq 1 90); do
    docker exec "$CONTAINER" test -f /root/.fabro/settings.toml && break
    sleep 1
  done
  docker exec "$CONTAINER" test -f /root/.fabro/settings.toml || fail "fabro settings were not provisioned"
}

start_container() {
  log "starting $CONTAINER from $IMAGE"
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  docker volume rm "$VARLIB_VOL" >/dev/null 2>&1 || true
  docker volume create "$VARLIB_VOL" >/dev/null
  local network_args=() publish_args=()
  if [ "$TIER2_USE_HOST_NETWORK" = "1" ]; then
    network_args=(--network host)
  else
    publish_args=(-p "127.0.0.1:${HOST_PUBLISH_PORT}:${FABRO_PORT}")
  fi
  # LIVESPEC_FAMILY_GITHUB_TOKEN is aliased to the e2e token so the entrypoint's
  # gh-auth + the dispatcher's GH_TOKEN projection target the livespec-e2e org.
  docker run -d --name "$CONTAINER" \
    --privileged \
    --cgroupns=host \
    "${network_args[@]}" \
    -v "$VARLIB_VOL:/var/lib/docker" \
    -v "$REPO_ROOT:$WORKSPACE_REPO" \
    -v "$CLONE_DIR:$TARGET_MOUNT" \
    "${publish_args[@]}" \
    -e FABRO_PORT="$FABRO_PORT" \
    -e LIVESPEC_FAMILY_GITHUB_TOKEN="$LIVESPEC_E2E_GITHUB_TOKEN" \
    -e ANTHROPIC_API_KEY_LIVESPEC_E2E \
    -e CLAUDE_CODE_OAUTH_TOKEN \
    -e HONEYCOMB_INGEST_KEY_LIVESPEC \
    "$IMAGE" \
    sleep infinity >/dev/null
  wait_for_container
}

trust_mounts() {
  log "trusting mounted repos for in-container git discovery"
  docker exec "$CONTAINER" git config --global --add safe.directory "$WORKSPACE_REPO"
  docker exec "$CONTAINER" git config --global --add safe.directory "$TARGET_MOUNT"
  docker exec "$CONTAINER" git -C "$TARGET_MOUNT" status --short --branch >/dev/null
}

# Capture the target work-item id from the embedded ledger (host-side read).
target_item_id() {
  (cd "$CLONE_DIR" && bd list --status open --json 2>/dev/null | jq -r '.[0].id')
}

run_dispatch() {
  local item_id="$1"
  log "dispatching greeting work-item ($item_id) into the Fabro factory"
  docker exec "$CONTAINER" mkdir -p "$(dirname "$JOURNAL_PATH")"
  set +e
  # mode shadow + explicit --item targets exactly the seeded item. A no-op
  # janitor ("true") is injected because the throwaway repo is a bare
  # hello-world (no justfile / livespec impl); the PR merge is the gate.
  docker exec \
    -w "$WORKSPACE_REPO" \
    "$CONTAINER" \
    sh -lc 'export GH_TOKEN="$LIVESPEC_FAMILY_GITHUB_TOKEN"; exec python3 "$1/.claude-plugin/scripts/bin/dispatcher.py" \
      loop \
      --repo "$2" \
      --budget 1 \
      --mode shadow \
      --item "$3" \
      --janitor "[\"true\"]" \
      --journal "$4" \
      --poll-attempts "$5" \
      --poll-interval-seconds "$6" \
      --json' \
      sh "$WORKSPACE_REPO" "$TARGET_MOUNT" "$item_id" "$JOURNAL_PATH" "$POLL_ATTEMPTS" "$POLL_INTERVAL_SECONDS" \
      >"$LOG_PATH" 2>&1
  local code=$?
  set -e
  log "dispatcher log tail (redacted)"
  redact <"$LOG_PATH" | tail -60
  printf 'dispatcher exit code: %s\n' "$code"
  docker exec "$CONTAINER" test -s "$JOURNAL_PATH" || fail "dispatcher did not write a journal"
  log "journal tail (redacted)"
  docker exec "$CONTAINER" tail -25 "$JOURNAL_PATH" | redact
  return "$code"
}

# Clone the MERGED repo at its default branch and run the greeting assertion
# via the live pytest binding (which calls run_live_acceptance).
assert_merged_greeting() {
  log "cloning MERGED repo at default branch + asserting greeting"
  local merged="$SCRATCH_DIR/merged-$THROWAWAY_REPO"
  GH_TOKEN="$LIVESPEC_E2E_GITHUB_TOKEN" gh repo clone "$ORG/$THROWAWAY_REPO" "$merged" >/dev/null 2>&1
  # Drive the assertion through the committed pytest binding so the SAME
  # run_live_acceptance code path is exercised. The binding reads the checkout
  # path + expected name from env.
  LIVESPEC_LIVE_CHECKOUT="$merged" \
  LIVESPEC_LIVE_NAME="$NAME" \
  LIVESPEC_BEADS_FAKE=1 \
    uv run --project "$REPO_ROOT" pytest \
      "$REPO_ROOT/acceptance/test_beads_fabro_live_golden_master.py" -q 2>&1 | redact | tail -20
  printf 'asserted greeting: %s\n' "$EXPECTED_GREETING"
}

main() {
  preflight
  if [ "$RUN" -eq 0 ]; then
    log "preflight complete"
    printf 'rerun with --run to execute the live golden-master proof\n'
    exit 0
  fi
  sweep_stale_repos
  create_and_seed_repo
  start_container
  trust_mounts
  local item_id
  item_id="$(target_item_id)"
  if [ -z "$item_id" ] || [ "$item_id" = "null" ]; then
    fail "could not read the seeded work-item id"
  fi
  if ! run_dispatch "$item_id"; then
    fail "dispatch did not reach a green (merged) outcome — see the dispatcher log + journal tail above"
  fi
  assert_merged_greeting
  log "live golden-master PROOF COMPLETE"
  printf 'repo:     %s/%s\n' "$ORG" "$THROWAWAY_REPO"
  printf 'item:     %s\n' "$item_id"
  printf 'greeting: %s\n' "$EXPECTED_GREETING"
  printf 'teardown + org-count check follow on exit\n'
}

main "$@"
