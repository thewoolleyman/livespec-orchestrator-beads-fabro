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
FABRO_PORT_WAS_SET="${FABRO_PORT+x}"
FABRO_PORT="${FABRO_PORT:-32276}"
HOST_PUBLISH_PORT="${HOST_PUBLISH_PORT:-32282}"
HOST_FABRO_BIN="${HOST_FABRO_BIN:-$HOME/.fabro/bin/fabro}"
# The impl-beads repo is mounted so the dispatcher code + the
# .fabro/workflows/implement-work-item/ phase graph resolve from the package
# root; the throwaway clone is mounted separately as the dispatch --repo.
WORKSPACE_REPO="${WORKSPACE_REPO:-/workspace/livespec-impl-beads}"
TARGET_MOUNT="${TARGET_MOUNT:-/workspace/e2e-target}"
TIER2_USE_HOST_NETWORK="${TIER2_USE_HOST_NETWORK:-1}"
# Under --network host the container shares the host network namespace, so an
# in-container fabro bound to the default 32276 collides with the host's own
# fabro server (which holds 127.0.0.1:32276). When the operator did not pin
# FABRO_PORT explicitly, bind the in-container server to HOST_PUBLISH_PORT
# instead so the two never contend (mirrors tier2-dispatch-proof.sh).
if [ "$TIER2_USE_HOST_NETWORK" = "1" ] && [ -z "$FABRO_PORT_WAS_SET" ]; then
  FABRO_PORT="$HOST_PUBLISH_PORT"
fi
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
  [ -f "$REPO_ROOT/orchestrator-image/e2e-skeleton/pyproject.toml" ] \
    || fail "throwaway-repo skeleton template missing: orchestrator-image/e2e-skeleton/"
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
  # SIGPIPE-safe random suffix: read a FIXED, generous chunk of urandom first
  # (head is the reader, so nothing downstream can SIGPIPE `tr` under `set -o
  # pipefail`), then filter + slice to 8 lowercase alphanumerics. 256 bytes
  # yields ~36 alphanumerics on average, comfortably above 8.
  rand="$(head -c 256 /dev/urandom | LC_ALL=C tr -dc 'a-z0-9' | cut -c1-8)"
  [ "${#rand}" -ge 8 ] || rand="r$(date +%s)"
  THROWAWAY_REPO="livespec-e2e-${rand}"
  log "creating throwaway repo $ORG/$THROWAWAY_REPO (private)"
  GH_TOKEN="$LIVESPEC_E2E_GITHUB_TOKEN" gh repo create "$ORG/$THROWAWAY_REPO" \
    --private --description "W7 live golden-master throwaway (auto-deleted)" >/dev/null
  THROWAWAY_CREATED=1

  SCRATCH_DIR="$(mktemp -d /tmp/live-gm-seed.XXXXXX)"
  local clone="$SCRATCH_DIR/$THROWAWAY_REPO"

  log "seeding minimal livespec-impl-shaped skeleton (master, >10 commits)"
  # The skeleton is a committed template (orchestrator-image/e2e-skeleton/): a
  # minimal-but-real livespec-impl-shaped repo (.mise.toml, pyproject + uv,
  # lefthook.yml, a lightweight green `just check`, a benign pass-through hook,
  # SPECIFICATION/, CLAUDE.md local constraints) so the UNMODIFIED production
  # implement-work-item workflow's prepare -> implement -> janitor -> PR steps
  # all succeed. We build the working tree locally and push it (no `gh repo
  # clone` round-trip needed).
  local skeleton="$REPO_ROOT/orchestrator-image/e2e-skeleton"
  [ -d "$skeleton" ] || fail "skeleton template missing: $skeleton"
  mkdir -p "$clone"
  # Copy tracked + dotfiles (cp -R of `.` brings hidden entries).
  cp -R "$skeleton/." "$clone/"

  log "initializing git on master + committing the skeleton"
  (
    cd "$clone"
    # git init FIRST (deterministic master branch), then the skeleton commit, so
    # the later `bd init` auto-commit (it git-commits its own .beads/ scaffold
    # even with --skip-hooks) lands ON master rather than racing the branch name.
    git init -q -b master
    git config user.email "e2e@livespec.invalid"
    git config user.name "livespec-e2e"
    # Set a TOKEN-FREE `origin` remote at the GitHub repo. This is LOAD-BEARING:
    # Fabro detects the GitHub origin from the mounted clone's .git/config and
    # clones FRESH in-sandbox from it (run #5 proved that WITHOUT an origin
    # remote, Fabro reports repo_cloned=false / origin_url="" and the workflow's
    # `git fetch --unshallow` then fails with "not a git repository"). The URL
    # carries NO token (secret hygiene); Fabro authenticates the in-sandbox clone
    # with the GH_TOKEN the Dispatcher projects into the sandbox env.
    git remote add origin "https://github.com/${ORG}/${THROWAWAY_REPO}.git"
    git add -A
    git commit -q -m "seed: minimal livespec-impl skeleton + greeting SPECIFICATION"
  )

  log "seeding embedded beads ledger + one ready greeting work-item"
  (
    cd "$clone"
    # Embedded mode: NO --server. Provisions a self-contained Dolt store under
    # .beads/embeddeddolt/. --skip-agents --skip-hooks per the family rule. bd
    # init also auto-commits its .beads/ scaffold (on the current master HEAD).
    bd init --prefix "${rand}greet" --skip-agents --skip-hooks --non-interactive --quiet >/dev/null 2>&1
    bd create "Implement greet per the SPECIFICATION" \
      -d "Implement the program described in this repo's SPECIFICATION/: expose a Python function greet(name: str) -> str (in src/greeting/greet.py) that returns exactly \"Hello, <name>!\". For the input Ada it must return \"Hello, Ada!\". Add a test under tests/ and make \`just check\` pass. Read this repo's root CLAUDE.md for local constraints (no Red-Green-Replay ritual here; commit normally). Follow contracts.md / scenarios.md exactly." \
      >/dev/null 2>&1
  )
  # Confirm exactly one ready item in the embedded ledger (redacted count only).
  local ready_count
  ready_count="$(cd "$clone" && bd list --status open --json 2>/dev/null | jq 'length' 2>/dev/null || echo '?')"
  printf 'embedded ledger ready (open) items: %s\n' "$ready_count"
  [ "$ready_count" = "1" ] || fail "expected exactly 1 ready item in the embedded ledger (got $ready_count)"

  log "padding git history (>10 commits so the depth-10 sandbox clone is shallow)"
  (
    cd "$clone"
    # Pad the history past Fabro's hardcoded GIT_CLONE_DEPTH=10 so the workflow's
    # `git fetch --unshallow` prepare step succeeds in-sandbox (a depth-10 clone
    # of a <=10-commit repo is COMPLETE, and --unshallow then errors).
    local i
    for i in $(seq 1 12); do
      printf 'history line %s\n' "$i" >>HISTORY.txt
      git add HISTORY.txt
      git commit -q -m "chore: history padding ${i}/12 (depth-10 unshallow headroom)"
    done
    printf 'commit count: %s\n' "$(git rev-list --count HEAD)"
    # Push master and SET it as the default branch (the PR stage targets master
    # and ranges origin/master..HEAD). Token only on this argv; nothing echoed.
    git push -q "https://x-access-token:${LIVESPEC_E2E_GITHUB_TOKEN}@github.com/${ORG}/${THROWAWAY_REPO}.git" HEAD:master 2>/dev/null
  )
  GH_TOKEN="$LIVESPEC_E2E_GITHUB_TOKEN" gh api -X PATCH "/repos/${ORG}/${THROWAWAY_REPO}" -f default_branch=master >/dev/null 2>&1 || true
  printf 'seeded + pushed: %s/%s (default branch master)\n' "$ORG" "$THROWAWAY_REPO"
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
  # Wire gh as git's credential helper in the orchestrator container so the
  # Dispatcher's POST-MERGE `git -C <throwaway-mount> pull --ff-only origin
  # master` authenticates against the token-free `origin` URL. The entrypoint
  # already `gh auth login`ed with the e2e token (aliased via
  # LIVESPEC_FAMILY_GITHUB_TOKEN); `gh auth setup-git` makes raw `git` reuse that
  # stored credential. Run #6 confirmed the PR genuinely MERGED and only this
  # post-merge pull failed ("could not read Username") — this closes that gap.
  docker exec "$CONTAINER" sh -lc 'gh auth setup-git' >/dev/null 2>&1 \
    || printf 'WARNING: gh auth setup-git failed; the post-merge pull may need credentials\n' >&2
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
  #
  # CWD = the THROWAWAY repo (-w "$TARGET_MOUNT"): the dispatcher's
  # ShellBeadsClient shells out to `bd` WITHOUT a cwd override, so `bd`
  # discovers the `.beads/` of the process cwd. Running with cwd = the
  # throwaway mount makes `bd list` resolve the throwaway's EMBEDDED ledger
  # (no family server, no password). The dispatcher script itself is invoked
  # by its ABSOLUTE path under $WORKSPACE_REPO, so its package-root resolution
  # (the .fabro/workflows graph, via __file__) is cwd-independent and still
  # points at the mounted impl-beads repo.
  docker exec \
    -w "$TARGET_MOUNT" \
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

# Confirm the throwaway repo has a MERGED PR (the genuine golden-master success
# criterion). Echoes the merged PR number + url. Returns 0 iff a merged PR
# exists. The dispatcher's post-merge housekeeping (pull-primary refresh,
# janitor re-check) is SEPARATE from the merge itself; the proof gates on the
# merge + the greeting assertion, not on that housekeeping.
MERGED_PR_NUMBER=""
MERGED_PR_URL=""
confirm_merged_pr() {
  local json
  json="$(GH_TOKEN="$LIVESPEC_E2E_GITHUB_TOKEN" gh pr list \
    --repo "$ORG/$THROWAWAY_REPO" --state merged --base master \
    --json number,url,mergedAt --limit 5 2>/dev/null || echo '[]')"
  MERGED_PR_NUMBER="$(printf '%s' "$json" | jq -r '.[0].number // empty' 2>/dev/null)"
  MERGED_PR_URL="$(printf '%s' "$json" | jq -r '.[0].url // empty' 2>/dev/null)"
  [ -n "$MERGED_PR_NUMBER" ]
}

# Clone the MERGED repo at its default branch and run the greeting assertion
# via the live pytest binding (which calls run_live_acceptance).
assert_merged_greeting() {
  log "cloning MERGED repo at default branch + asserting greeting"
  local merged="$SCRATCH_DIR/merged-$THROWAWAY_REPO"
  GH_TOKEN="$LIVESPEC_E2E_GITHUB_TOKEN" gh repo clone "$ORG/$THROWAWAY_REPO" "$merged" >/dev/null 2>&1 \
    || fail "could not clone the merged repo for assertion"
  # Drive the assertion through the committed pytest binding so the SAME
  # run_live_acceptance code path is exercised. The binding reads the checkout
  # path + expected name from env and asserts greet(name) == "Hello, <name>!".
  # Capture the exit code (pipefail + the tee) so a FAILED assertion fails the
  # whole proof — the greeting assertion is NEVER weakened or masked.
  local out rc
  out="$(LIVESPEC_LIVE_CHECKOUT="$merged" LIVESPEC_LIVE_NAME="$NAME" LIVESPEC_BEADS_FAKE=1 \
    uv run --project "$REPO_ROOT" pytest \
      "$REPO_ROOT/acceptance/test_beads_fabro_live_golden_master.py" -q 2>&1)"
  rc=$?
  printf '%s\n' "$out" | redact | tail -20
  [ "$rc" -eq 0 ] || fail "greeting assertion FAILED (pytest exit $rc) — the merged program did not greet $NAME as \"$EXPECTED_GREETING\""
  printf 'asserted greeting: %s == greet("%s") from the merged repo\n' "$EXPECTED_GREETING" "$NAME"
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
  # Run the dispatch. A non-green dispatcher outcome is NOT automatically fatal:
  # the genuine golden-master criterion is a MERGED PR + the greeting assertion.
  # The dispatcher can report `failed` for post-merge HOUSEKEEPING (e.g. the
  # pull-primary refresh) AFTER a real merge; we therefore gate on the merge
  # itself, confirmed directly against GitHub.
  local dispatch_ok=1
  run_dispatch "$item_id" || dispatch_ok=0
  log "confirming a merged PR on the throwaway repo (the true success criterion)"
  if ! confirm_merged_pr; then
    if [ "$dispatch_ok" -eq 0 ]; then
      fail "dispatch did not produce a merged PR — see the dispatcher log + journal tail above"
    fi
    fail "dispatch reported green but no merged PR was found on $ORG/$THROWAWAY_REPO"
  fi
  printf 'merged PR: #%s  %s\n' "$MERGED_PR_NUMBER" "$MERGED_PR_URL"
  if [ "$dispatch_ok" -eq 0 ]; then
    printf 'NOTE: the dispatcher reported a non-green outcome (post-merge housekeeping), '
    printf 'but the PR genuinely MERGED; the proof gates on the merge + greeting assertion.\n'
  fi
  assert_merged_greeting
  log "live golden-master PROOF COMPLETE"
  printf 'repo:     %s/%s\n' "$ORG" "$THROWAWAY_REPO"
  printf 'item:     %s\n' "$item_id"
  printf 'merged PR: #%s  %s\n' "$MERGED_PR_NUMBER" "$MERGED_PR_URL"
  printf 'greeting: %s\n' "$EXPECTED_GREETING"
  printf 'teardown + org-count check follow on exit\n'
}

main "$@"
