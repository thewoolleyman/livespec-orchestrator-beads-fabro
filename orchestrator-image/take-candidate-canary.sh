#!/usr/bin/env bash
# take-candidate-canary.sh - take ONE candidate canary: file a fixture work-item
# from the committed template, then dispatch it to a NAMED factory.
#
# WHY THIS EXISTS
# ---------------
# A canary measures the ENGINE - a candidate Fabro build, a re-pinned carrier, a
# restarted factory host. Whatever brief it carries is instrumentation, so the
# one property that brief must have is that it cannot fail for a reason of its
# own. Canaries 5 and 6 of plan `fabro-currency` did exactly that: both reached
# the `dod_gate` node and were refused, because the canary reused a real backlog
# item whose `References` line named a heading that governs something else. At
# the surface an operator watches, an item-quality refusal is indistinguishable
# from the engine fault the canary was taken to look for - which is why the
# second canary repeated the first's mistake.
#
# So the brief is the committed fixture at
# orchestrator-image/candidate-canary-work-item-template.md, reviewed once
# through the ordinary gates and thereafter rendered mechanically. Filing a
# canary by hand is how a canary acquires an unreviewed brief again; this script
# is the sanctioned way to take one.
#
# WHAT IT DOES, IN TWO LEGS
# -------------------------
#   1. Files a FRESH fixture work-item from that template, through the shared
#      capture seam (committed-ceiling validation, then the one intake gate
#      every other filing door uses). Fresh every time: a reused item would
#      accumulate the comments, claims and audit of every canary before it, so
#      the brief would grow with each one.
#   2. Dispatches that item to the factory NAMED on the command line.
#
# Both legs, in that order. A file-without-dispatch leaves a fresh fixture item
# stranded in the ledger, which is worse than not taking the canary at all, so
# the dispatch is not optional and --dry-run stops before leg 1 rather than
# between the two.
#
# WHY --factory IS REQUIRED AND NEVER DEFAULTED
# ---------------------------------------------
# A canary is usually evidence ABOUT A PARTICULAR ENGINE, and the configured
# factories can carry different Fabro builds. A dispatch that silently took
# `dispatcher.default_factory` would exercise the wrong build and return a
# perfectly normal green run, with no error and nothing in the output to say
# which engine answered. Naming the factory is what makes the evidence mean
# anything, so this script refuses without it rather than choosing for you.
#
# REQUIRED ENV (normally from the 1Password wrapper)
# --------------------------------------------------
#   BEADS_DOLT_PASSWORD
#     The tenant password both legs need to reach the ledger. The bin wrappers
#     self-heal by re-exec'ing through the configured credential wrapper when it
#     is absent, so running this outside the wrapper normally still works; run it
#     under the wrapper to avoid the re-exec.
#
# USAGE
#   just take-candidate-canary -- --factory hp
#   just take-candidate-canary -- --factory hp-candidate --dry-run

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
FILE_CANARY="$REPO_ROOT/.claude-plugin/scripts/bin/take_candidate_canary.py"
DISPATCHER="$REPO_ROOT/.claude-plugin/scripts/bin/dispatcher.py"
TEMPLATE="$REPO_ROOT/orchestrator-image/candidate-canary-work-item-template.md"
INVOKER="${LIVESPEC_INVOKER:-operator:take-candidate-canary}"

FACTORY=""
DRY_RUN=0

usage() {
  cat <<'USAGE'
Usage:
  just take-candidate-canary -- --factory <name> [--dry-run]
  bash orchestrator-image/take-candidate-canary.sh --factory <name> [--dry-run]

Files one fixture canary work-item from the committed template at
orchestrator-image/candidate-canary-work-item-template.md and dispatches it to
the named factory.

Options:
  --factory NAME   REQUIRED. The configured `dispatcher.factories` name to
                   dispatch to (e.g. hp, hp-candidate). Never defaulted: a
                   canary is evidence about a particular engine.
  --dry-run        Report what would be taken and file nothing.
  --help, -h       Show this help.

Env overrides:
  LIVESPEC_INVOKER   Journal invoker attribution for the dispatch.
                     Default: operator:take-candidate-canary.
USAGE
}

log() {
  printf ':: take-candidate-canary: %s\n' "$1" >&2
}

fail() {
  printf 'ERROR: take-candidate-canary: %s\n' "$1" >&2
  exit 1
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --factory)
      [ "$#" -ge 2 ] || fail '--factory needs a value'
      FACTORY="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --help | -h)
      usage
      exit 0
      ;;
    *)
      usage >&2
      fail "unrecognized argument: $1"
      ;;
  esac
done

[ -n "$FACTORY" ] || {
  usage >&2
  fail '--factory <name> is required; a canary is evidence about one engine'
}
[ -f "$TEMPLATE" ] || fail "no committed fixture template at $TEMPLATE"
[ -f "$FILE_CANARY" ] || fail "no canary filing entry point at $FILE_CANARY"
[ -f "$DISPATCHER" ] || fail "no dispatcher entry point at $DISPATCHER"

if [ "$DRY_RUN" -eq 1 ]; then
  log "would file one canary from $TEMPLATE and dispatch it to factory $FACTORY"
  exit 0
fi

# `bd` resolves its tenant from the current directory's .beads/config.yaml, so
# both legs run from the repository root rather than from wherever the operator
# invoked this.
cd "$REPO_ROOT"

log "filing one fixture canary from $TEMPLATE"
canary_id="$(uv run python "$FILE_CANARY" --factory "$FACTORY" --project-root "$REPO_ROOT")"
[ -n "$canary_id" ] || fail 'the filing leg printed no work-item id'

log "dispatching $canary_id to factory $FACTORY"
uv run python "$DISPATCHER" dispatch \
  --repo "$REPO_ROOT" \
  --item "$canary_id" \
  --factory "$FACTORY" \
  --invoker "$INVOKER"
