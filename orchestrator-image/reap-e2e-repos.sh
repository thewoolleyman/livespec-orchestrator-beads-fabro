#!/usr/bin/env bash
# reap-e2e-repos.sh - W7 mechanical fail-safe reaper for orphaned
# `livespec-e2e-*` throwaway GitHub repos in the disposable `livespec-e2e`
# org.
#
# WHY THIS EXISTS
# ---------------
# The W7 dark-factory end-to-end acceptance runs create throwaway GitHub
# repositories named `livespec-e2e-*` inside the dedicated, disposable
# `livespec-e2e` org. A crashed run, a killed sandbox, or an interrupted
# teardown can leave such repos orphaned. This reaper is the mechanical
# fail-safe that sweeps them.
#
# SAFETY MODEL
# ------------
# - Org-scoped by construction. It only ever lists and deletes repos in the
#   `livespec-e2e` org, and within that org only repos whose name matches the
#   throwaway pattern `^livespec-e2e-`. It can never touch a repo outside that
#   org or a non-matching repo inside it.
# - Age-gated by default. A repo is eligible only if BOTH its createdAt and
#   pushedAt are older than --max-age minutes (default 120). This means a repo
#   belonging to an in-progress acceptance run (recently created or recently
#   pushed) is NOT reaped. Set --max-age 0 (or --force-all) to delete every
#   matching repo regardless of age — use only during a deliberate full
#   teardown of the disposable org.
# - Dry-run first. --dry-run lists exactly what WOULD be deleted and deletes
#   nothing; it is the safe way to preview a sweep.
# - Idempotent + race-tolerant deletes. `gh repo delete` immediately after a
#   create can return HTTP 403 "Repository cannot be deleted until it is done
#   being created on disk"; the delete retries with bounded backoff. An
#   already-gone repo (HTTP 404) is treated as success.
# - Secret hygiene. The org-scoped fine-grained token is read by byte count
#   only; its value is never printed, and any `github_pat_...` substring in
#   tool output is redacted.
#
# "NEVER REAP DURING AN ACTIVE DISPATCH" DISCIPLINE
# -------------------------------------------------
# This reaper is for session-start, post-confirmed-merge, deliberate teardown,
# and scheduled fail-safe use — NOT mid-dispatch. Deleting a repo that a live
# Fabro sandbox is still cloning/pushing/PRing against would corrupt an
# in-flight run. The age gate is the mechanical guard (an active run's repo is
# fresh, so it is skipped), but the operational rule stands regardless of the
# threshold: run this only when no dispatch is in flight against the org.
#
# REQUIRED ENV (normally from the 1Password wrapper)
# --------------------------------------------------
#   LIVESPEC_E2E_GITHUB_TOKEN
#     Fine-grained token scoped to the `livespec-e2e` org
#     (Administration/Contents/Pull-requests/Workflows RW). Mapped to GH_TOKEN
#     for the `gh` calls. Presence is checked by byte count only; the value is
#     never printed.
#
# Supplied by:
#   /data/projects/1password-env-wrapper/with-livespec-env.sh -- <command>

set -euo pipefail

ORG="livespec-e2e"
NAME_PATTERN='^livespec-e2e-'
MAX_AGE_MINUTES="${REAP_E2E_MAX_AGE_MINUTES:-120}"
LIST_LIMIT="${REAP_E2E_LIST_LIMIT:-200}"
DELETE_ATTEMPTS="${REAP_E2E_DELETE_ATTEMPTS:-5}"
DELETE_BACKOFF_SECONDS="${REAP_E2E_DELETE_BACKOFF_SECONDS:-3}"
DRY_RUN=0
FORCE_ALL=0

usage() {
  cat <<'USAGE'
Usage:
  reap-e2e-repos.sh [--dry-run] [--max-age <minutes>] [--force-all]

Reaps orphaned `livespec-e2e-*` repos in the disposable `livespec-e2e` GitHub
org. Org-scoped and name-gated by construction; never touches anything else.

Options:
  --dry-run            List what WOULD be deleted; delete nothing.
  --max-age MINUTES    Only reap repos whose createdAt AND pushedAt are older
                       than this many minutes. Default: 120. A fresher repo
                       (an in-progress run) is skipped. --max-age 0 disables
                       the age gate (delete every matching repo).
  --force-all          Alias for --max-age 0: delete every matching repo
                       regardless of age. Use only for a deliberate full
                       teardown of the disposable org.
  --help, -h           Show this help.

Env overrides:
  REAP_E2E_MAX_AGE_MINUTES         Default for --max-age (default 120).
  REAP_E2E_LIST_LIMIT              gh repo list --limit (default 200).
  REAP_E2E_DELETE_ATTEMPTS         Delete retry attempts (default 5).
  REAP_E2E_DELETE_BACKOFF_SECONDS  Seconds between delete retries (default 3).

Required env (normally from the 1Password wrapper):
  LIVESPEC_E2E_GITHUB_TOKEN
    Fine-grained token scoped to the `livespec-e2e` org. Mapped to GH_TOKEN.
    Presence is checked by byte count only; the value is never printed.

  /data/projects/1password-env-wrapper/with-livespec-env.sh -- \
    bash orchestrator-image/reap-e2e-repos.sh --dry-run
USAGE
}

log() { printf '\n=== %s ===\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# Redact any fine-grained PAT and any long opaque token-shaped run so a leaked
# value in tool output never reaches the terminal or a log.
redact() {
  sed -E 's/github_pat_[A-Za-z0-9_]+/<redacted>/g; s/gh[posu]_[A-Za-z0-9]{16,}/<redacted>/g'
}

require_env() {
  local name="$1"
  local value="${!name:-}"
  if [ -z "$value" ]; then
    fail "required env var is not set: $name"
  fi
  printf '%s present (%s bytes)\n' "$name" "$(printf '%s' "$value" | wc -c | tr -d ' ')"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --) shift;;
    --help|-h) usage; exit 0;;
    --dry-run) DRY_RUN=1; shift;;
    --force-all) FORCE_ALL=1; shift;;
    --max-age) MAX_AGE_MINUTES="${2:-}"; shift 2;;
    *) fail "unknown argument: $1";;
  esac
done

if [ "$FORCE_ALL" -eq 1 ]; then
  MAX_AGE_MINUTES=0
fi

case "$MAX_AGE_MINUTES" in
  ''|*[!0-9]*) fail "--max-age must be a non-negative integer (got: $MAX_AGE_MINUTES)";;
esac

require_command gh
require_command jq
require_env LIVESPEC_E2E_GITHUB_TOKEN
export GH_TOKEN="$LIVESPEC_E2E_GITHUB_TOKEN"

# Delete one repo with bounded backoff for the create-on-disk race. Returns 0
# on a confirmed delete OR an already-gone (404) repo; non-zero only after all
# attempts are exhausted on a persistent error.
delete_repo() {
  local full_name="$1"
  local attempt=1
  local out=""
  local code=0
  while [ "$attempt" -le "$DELETE_ATTEMPTS" ]; do
    set +e
    out="$(gh api -X DELETE "/repos/${full_name}" 2>&1)"
    code=$?
    set -e
    if [ "$code" -eq 0 ]; then
      return 0
    fi
    # Already gone is success (idempotent).
    if printf '%s' "$out" | grep -qiE 'HTTP 404|Not Found'; then
      printf '    already gone (404): %s\n' "$full_name"
      return 0
    fi
    # The create-on-disk race: retry with backoff.
    if printf '%s' "$out" | grep -qiE 'done being created on disk|HTTP 403'; then
      printf '    attempt %s/%s not-yet-deletable, backing off %ss\n' \
        "$attempt" "$DELETE_ATTEMPTS" "$DELETE_BACKOFF_SECONDS"
      sleep "$DELETE_BACKOFF_SECONDS"
      attempt=$((attempt + 1))
      continue
    fi
    # Unknown error: retry too (still bounded), but surface the redacted reason.
    printf '    attempt %s/%s failed: %s\n' \
      "$attempt" "$DELETE_ATTEMPTS" "$(printf '%s' "$out" | redact | head -1)"
    sleep "$DELETE_BACKOFF_SECONDS"
    attempt=$((attempt + 1))
  done
  printf '    giving up after %s attempts: %s\n' "$DELETE_ATTEMPTS" "$full_name"
  return 1
}

log "scanning org $ORG"
printf 'max-age: %s minutes (0 = age gate disabled)\n' "$MAX_AGE_MINUTES"
printf 'mode: %s\n' "$([ "$DRY_RUN" -eq 1 ] && echo 'DRY-RUN (no deletes)' || echo 'REAP (deletes eligible repos)')"

# now (epoch) and the threshold cutoff (epoch). A repo is age-eligible when
# BOTH createdAt and pushedAt are at or before the cutoff. With max-age 0 the
# cutoff is "now", so every repo is eligible.
now_epoch="$(date -u +%s)"
cutoff_epoch=$((now_epoch - MAX_AGE_MINUTES * 60))

# Emit `name<TAB>createdAt<TAB>pushedAt` for every matching repo. The name
# filter is applied here so nothing outside the throwaway pattern is ever
# considered for deletion.
repos_tsv="$(
  gh repo list "$ORG" --json name,createdAt,pushedAt --limit "$LIST_LIMIT" \
    | jq -r --arg pat "$NAME_PATTERN" \
        '.[] | select(.name | test($pat)) | [.name, .createdAt, (.pushedAt // .createdAt)] | @tsv'
)"

scanned=0
eligible=0
deleted=0
skipped=0
failed=0

if [ -n "$repos_tsv" ]; then
  while IFS=$'\t' read -r name created pushed; do
    [ -z "$name" ] && continue
    scanned=$((scanned + 1))
    created_epoch="$(date -u -d "$created" +%s 2>/dev/null || echo 0)"
    pushed_epoch="$(date -u -d "$pushed" +%s 2>/dev/null || echo 0)"
    # Newest of the two timestamps gates eligibility: a fresh push OR a fresh
    # create both protect an in-progress run's repo.
    newest_epoch="$created_epoch"
    if [ "$pushed_epoch" -gt "$newest_epoch" ]; then
      newest_epoch="$pushed_epoch"
    fi
    if [ "$newest_epoch" -gt "$cutoff_epoch" ]; then
      age_min=$(((now_epoch - newest_epoch) / 60))
      printf '  SKIP  %s (age %sm < %sm; created=%s pushed=%s)\n' \
        "$name" "$age_min" "$MAX_AGE_MINUTES" "$created" "$pushed"
      skipped=$((skipped + 1))
      continue
    fi
    eligible=$((eligible + 1))
    age_min=$(((now_epoch - newest_epoch) / 60))
    if [ "$DRY_RUN" -eq 1 ]; then
      printf '  WOULD-DELETE  %s (age %sm; created=%s pushed=%s)\n' \
        "$name" "$age_min" "$created" "$pushed"
      continue
    fi
    printf '  DELETE  %s (age %sm)\n' "$name" "$age_min"
    if delete_repo "$ORG/$name"; then
      deleted=$((deleted + 1))
    else
      failed=$((failed + 1))
    fi
  done <<EOF
$repos_tsv
EOF
fi

log "summary"
printf 'org:      %s\n' "$ORG"
printf 'scanned:  %s\n' "$scanned"
printf 'eligible: %s\n' "$eligible"
printf 'deleted:  %s\n' "$deleted"
printf 'skipped:  %s\n' "$skipped"
printf 'failed:   %s\n' "$failed"

if [ "$failed" -gt 0 ]; then
  fail "$failed repo(s) could not be deleted after retries"
fi
