#!/bin/sh
# bd-guard.sh — warn-first guard wrapper that fronts every `bd` invocation.
#
# WHY THIS EXISTS (stopgap): the fleet's beads tenant keeps accumulating
# NON-lifecycle statuses because raw `bd` usage bypasses the conformant store
# path. The livespec lifecycle statuses are exactly:
#
#     backlog  pending-approval  ready  active  acceptance  blocked  closed
#
# (this set is authoritative: it is `ALLOWED_BEADS_STATUSES` in
# `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/_store_statuses.py`,
# itself DERIVED from the `WorkItemStatus` Literal with `done` projected to
# `closed`). Beads' native `open` / `in_progress` / `deferred`, and
# `bd update --claim` (which sets `in_progress`), are NON-conformant.
#
# This wrapper guards ONLY the two EXPLICIT non-lifecycle operations that a
# single-command wrapper on `bd` v1.0.5 can detect with high confidence:
#
#   1. `bd update ... --status <S>` where S is not one of the 7 lifecycle
#      statuses (e.g. open, in_progress, deferred, done, or any unknown value);
#   2. `bd update ... --claim` (which sets status=in_progress).
#
# EVERYTHING ELSE passes through UNCHANGED — `create`, `list`, `show`, `close`,
# `dep`, `config`, `history`, `--json`, and every other subcommand/flag. The
# bare-`create` -> `open` case is deliberately OUT OF SCOPE (it cannot be
# cleanly guarded at a single-command wrapper on v1.0.5; it is handled by the
# store normalizer + the upstream `status.default` work).
#
# This is a STOPGAP until beads ships the upstream fixes. It is designed to be
# TRIVIALLY REMOVABLE: rollback restores the real `bd`, and the whole
# `bd-guard/` directory can be deleted.
#
# BEHAVIOR (the load-bearing contract):
#   * Mode via env LIVESPEC_BD_GUARD_MODE, DEFAULT `warn`:
#       - warn: print a one-line stderr warning naming the violation + the
#         correct alternative, then STILL exec the real bd (transparent
#         passthrough — nothing breaks). This is the observation phase used to
#         enumerate offending callers.
#       - fail: print the same message as an error and exit non-zero WITHOUT
#         execing (block the operation).
#     Any other / unset value is treated as `warn` — the wrapper NEVER blocks
#     unless explicitly set to `fail`, so a misconfiguration cannot brick bd.
#   * Transparency: for every passthrough (and warn-mode violation) argv is
#     preserved EXACTLY and the real bd's stdin/stdout/stderr + exit code are
#     preserved via `exec` (no fork, no wait, no added latency). Warnings go to
#     STDERR only — stdout is never touched, so `--json` output stays
#     byte-identical.
#   * The real bd is located via env LIVESPEC_BD_REAL if set, else the default
#     /usr/local/bin/bd-real (the path the installer relocates the real binary
#     to). This parameterization is what makes the wrapper hermetically
#     testable against a stub.

set -u

REAL="${LIVESPEC_BD_REAL:-/usr/local/bin/bd-real}"
MODE="${LIVESPEC_BD_GUARD_MODE:-warn}"

# The 7 livespec lifecycle statuses, space-padded for substring matching.
# Keep in lockstep with ALLOWED_BEADS_STATUSES (see header).
LIFECYCLE_STATUSES=" backlog pending-approval ready active acceptance blocked closed "

# Emit a violation to stderr in the standardized one-line form
# `livespec bd-guard: '<subject>' is non-lifecycle; use <alternative>`.
# Never writes to stdout.
guard_warn() {
    # $1 = subject (e.g. "bd update --status in_progress")
    # $2 = alternative (e.g. "--status active")
    printf 'livespec bd-guard: %s\n' "'$1' is non-lifecycle; use $2" >&2
}

# ---------------------------------------------------------------------------
# Detection. We scan a COPY of the argv (via `for` over "$@", which does not
# mutate "$@"), so the ORIGINAL argv is handed to `exec` untouched.
#
# Two passes' worth of logic in one loop, driven by `phase`:
#   * phase=global — before the subcommand: skip global flags (and the values
#     of the value-taking ones) until we see the first positional token, which
#     is the subcommand.
#   * phase=args   — after an `update` subcommand: look for a non-lifecycle
#     --status/-s value or a --claim, honoring a `--` end-of-flags terminator
#     and skipping the values of value-taking update flags (so a value that
#     merely LOOKS like `--claim`/`-s` is not misread).
# If the subcommand is anything other than `update`, we stop early.
# ---------------------------------------------------------------------------
phase="global"
expect_value=0        # skip the next token: it is a consumed flag value
want_status_value=0   # the previous token was --status/-s in separate form
after_ddash=0         # a `--` end-of-flags terminator has been seen
status_value=""       # the captured --status/-s value (empty = none seen)
saw_claim=0           # a --claim flag was seen

for arg in "$@"; do
    if [ "$want_status_value" -eq 1 ]; then
        status_value="$arg"
        want_status_value=0
        continue
    fi
    if [ "$expect_value" -eq 1 ]; then
        expect_value=0
        continue
    fi

    if [ "$phase" = "global" ]; then
        case "$arg" in
            # Value-taking GLOBAL flags in separate-word form: skip their value.
            --actor|--db|-C|--directory|--dolt-auto-commit)
                expect_value=1
                ;;
            # `=`-form or boolean global flags and the end-of-flags marker are
            # single self-contained tokens; just skip them.
            --*=*|-C=*|--) : ;;
            -*) : ;;
            *)
                # First positional token = the subcommand.
                if [ "$arg" = "update" ]; then
                    phase="args"
                else
                    # Not an update: nothing to guard.
                    break
                fi
                ;;
        esac
        continue
    fi

    # phase = args (inside an `update` subcommand)
    if [ "$after_ddash" -eq 1 ]; then
        # Everything after `--` is positional, never a flag.
        continue
    fi
    case "$arg" in
        --)
            after_ddash=1
            ;;
        --claim)
            saw_claim=1
            ;;
        --status|-s)
            want_status_value=1
            ;;
        --status=*)
            status_value="${arg#--status=}"
            ;;
        -s=*)
            status_value="${arg#-s=}"
            ;;
        -s?*)
            # Clustered short form: -sVALUE
            status_value="${arg#-s}"
            ;;
        # Value-taking UPDATE flags (separate-word form): skip their value so a
        # value like `--claim` or `-s` is not misread as a flag. Derived from
        # `bd update --help` on bd v1.0.5.
        --acceptance|--add-label|--append-notes|-a|--assignee|--await-id|\
        --body-file|--defer|-d|--description|--design|--design-file|--due|\
        -e|--estimate|--external-ref|--metadata|--notes|--parent|-p|\
        --priority|--remove-label|--session|--set-labels|--set-metadata|\
        --spec-id|--title|-t|--type|--unset-metadata)
            expect_value=1
            ;;
        *)
            : # positional id, boolean flag, or `=`-form value — ignore.
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Verdict. Collect any violations, then act per mode.
# ---------------------------------------------------------------------------
violated=0

if [ "$saw_claim" -eq 1 ]; then
    violated=1
    guard_warn "bd update --claim" "--status active"
fi

if [ -n "$status_value" ]; then
    case "$LIFECYCLE_STATUSES" in
        *" $status_value "*)
            : # conformant lifecycle status — no violation.
            ;;
        *)
            violated=1
            if [ "$status_value" = "in_progress" ]; then
                guard_warn "bd update --status $status_value" "--status active"
            else
                guard_warn "bd update --status $status_value" \
                    "one of:$LIFECYCLE_STATUSES(or 'bd close')"
            fi
            ;;
    esac
fi

if [ "$violated" -eq 1 ] && [ "$MODE" = "fail" ]; then
    # fail mode: block WITHOUT execing. The message(s) above already printed
    # to stderr; exit non-zero.
    exit 3
fi

# warn mode (default), or no violation: transparent passthrough. `exec`
# replaces this process, preserving argv, the std streams, and the exit code
# of the real bd exactly, with no added fork/latency.
exec "$REAL" "$@"
