#!/bin/sh
# bd-guard-wrapper-sentinel — install.sh/rollback.sh identify this guard by
# grepping the whole file for the exact marker `bd-guard-wrapper-sentinel`; do
# NOT remove or rename it. (A line-anchored check would miss it: line 1 is the
# shebang, so the recognizers scan the entire file for this token, not one
# line.)
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
# This wrapper guards ONLY the EXPLICIT non-lifecycle operations that a
# single-command wrapper on `bd` v1.0.5 can detect with high confidence:
#
#   1. `bd update ... --status <S>` where S is not one of the 7 lifecycle
#      statuses (e.g. open, in_progress, deferred, done, or any unknown value);
#   2. `bd update ... --claim` (which sets status=in_progress);
#   3. `bd reopen ...` (which sets status back to the non-lifecycle `open`) —
#      a single-token subcommand, so detection is unambiguous;
#   4. `bd ready ... --claim` (the advertised "grab work" path, which sets
#      status=in_progress) — scanned in a DEDICATED `ready` phase that checks
#      ONLY --claim, so a bare `bd ready` list or a `bd ready --status <x>`
#      filter is never misread as a status write;
#   5. `bd defer <id>` (which sets status to the non-lifecycle `deferred`) —
#      a single-token subcommand, exactly the `reopen` shape. NOTE this is the
#      defer SUBCOMMAND, distinct from `update --defer <date>` (a defer-date
#      FLAG that writes no status and is NOT guarded).
#
# EVERYTHING ELSE passes through UNCHANGED — `list`, `show`, `close`, `dep`,
# `config`, `history`, `--json`, and every other subcommand/flag.
#
# CREATE NORMALIZATION (the sixth channel). beads v1.0.5 `bd create` hardcodes
# status `open` (a NON-lifecycle status): there is no `create --status` flag and
# no default-status config on v1.0.5, so every plain create mints an `open` item
# — the last raw drift channel. To close it, the wrapper forces a QUALIFYING
# create to land the lifecycle status `backlog` via a guard-side two-step: it
# runs the real create, then (FAIL-OPEN) issues `bd update <new-id> --status
# backlog`. A create is QUALIFYING when the subcommand is `create` / `new` / `q`
# (quick-capture) AND it is NONE of these exclusions:
#   * `--type event` (audit event beads, not work items);
#   * `--ephemeral` (incl. its `=true` form);
#   * `--dry-run` (nothing is created; incl. its `=true` form);
#   * `--help` / `-h` (prints help, creates nothing — its help TEXT contains
#     example ids that must never be mistaken for a real new id);
#   * a BATCH create (`--file` / `-f` / `--graph`, incl. clustered `-fFILE`) —
#     it mints MANY ids; forcing is SKIPPED for batch in this first cut and left
#     to the store normalizer (documented, not silent — see the create-phase
#     scan and README);
#   * a TENANT/DB SELECTOR (`-C` / `--directory` / `--db` / `--global` /
#     `--repo`, incl. `=`-forms and clustered `-Cdir`) — the create mints in one
#     tenant/db while the FLAG-LESS follow-up `update` would target another, so
#     forcing would strand the new item `open` OR (worse) mutate a same-id item
#     in the WRONG tenant. Such creates pass through unforced (land `open` →
#     the store normalizer catches them). We deliberately do NOT try to
#     propagate the selector onto `update` (exclusion is the safe fix);
#   * a create already carrying a lifecycle `--status <s>` (future-proofing for
#     when beads ships create-time `--status`: a lifecycle value is respected,
#     a non-lifecycle value is still normalized to `backlog`).
# The forcing is FAIL-OPEN: if the follow-up update fails, the create's own exit
# code and output are untouched and a stranded `open` is caught by the store
# normalizer. Create never trips a violation, so it is never BLOCKED (even in
# fail mode) — only normalized. The new id is extracted FORM-ANCHORED (JSON
# first-`"id"`-field, or the token after `Created issue: `, or a whole-output
# single id token) — NEVER first-hyphenated-token-anywhere, which legacy
# `--json`'s alphabetically-sorted keys would defeat by exposing a real id
# inside e.g. a `--description` field. The create's stdout is replayed AFTER the
# follow-up update completes, so a consumer that reads the id and immediately
# updates the item cannot race the guard's own backlog update.
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

# Mode resolution (precedence): explicit env var > host-wide mode file > warn.
# WHY THE FILE: the fleet credential wrapper (with-livespec-env.sh) scrubs the
# environment (sudo env_reset / env -i) before bd runs, so an exported
# LIVESPEC_BD_GUARD_MODE never reaches real callers. The mode FILE survives the
# scrub and is the host-wide switch:
#     echo fail | sudo tee /usr/local/etc/livespec-bd-guard.mode   # block
#     echo warn | sudo tee /usr/local/etc/livespec-bd-guard.mode   # observe
# Default (no env, no file, or any non-`fail` value) stays warn — never blocks.
MODE_FILE="${LIVESPEC_BD_GUARD_MODE_FILE:-/usr/local/etc/livespec-bd-guard.mode}"
MODE="${LIVESPEC_BD_GUARD_MODE:-}"
if [ -z "$MODE" ] && [ -r "$MODE_FILE" ]; then
    # head|tr, NOT `read`: `read` returns EOF-nonzero on a file with no trailing
    # newline and the `|| MODE=""` fallback would then clobber a VALID value,
    # silently degrading `fail` to warn. `head -n1 | tr -d` strips all whitespace
    # (incl. CR) so `fail`, `fail\n`, `fail\r\n`, and ` fail ` all resolve to fail.
    MODE=$(head -n1 "$MODE_FILE" 2>/dev/null | tr -d '[:space:]')
fi
MODE="${MODE:-warn}"

# Display argv for telemetry, captured at top level (a function's $* would shadow it).
_bdg_argv="$*"

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
#   * phase=ready  — after a `ready` subcommand: look ONLY for a --claim (which
#     grabs a ready item into in_progress). Deliberately does NOT scan --status,
#     so a bare `bd ready` list or a `bd ready --status <x>` filter never trips.
# The single-token `reopen` and `defer` subcommands (both direct non-lifecycle
# status writes) are flagged directly in the global phase.
# If the subcommand is anything else, we stop early.
# ---------------------------------------------------------------------------
phase="global"
expect_value=0        # skip the next token: it is a consumed flag value
want_status_value=0   # the previous token was --status/-s in separate form
after_ddash=0         # a `--` end-of-flags terminator has been seen
status_value=""       # the captured --status/-s value (empty = none seen)
saw_claim=0           # a --claim flag was seen
saw_reopen=0          # the `reopen` subcommand was seen
saw_defer=0           # the `defer` subcommand was seen
guarded_sub="update"  # subcommand a --claim was seen under (update|ready), for the message
_bdg_op=""            # telemetry: a summary of the flagged op (reopen / claim /
                      # status:<value>), empty when nothing was flagged

# --- create-normalization scan state (phase=create) --------------------------
is_create=0           # a create/new/q subcommand was seen
create_excluded=0     # --ephemeral / --dry-run / --help seen (do not force)
create_batch=0        # --file/-f/--graph seen (batch create; forcing SKIPPED)
create_tenant_selector=0 # -C/--directory/--db/--global/--repo seen (wrong-tenant risk; do not force)
create_type=""        # the captured --type/-t value ("event" excludes)
create_status_value="" # a create-time --status/-s value (future-proofing)
want_type_value=0     # the previous token was --type/-t in separate form
want_create_status=0  # the previous token was a create --status/-s (separate)

for arg in "$@"; do
    if [ "$want_type_value" -eq 1 ]; then
        create_type="$arg"
        want_type_value=0
        continue
    fi
    if [ "$want_create_status" -eq 1 ]; then
        create_status_value="$arg"
        want_create_status=0
        continue
    fi
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
            # Tenant/DB SELECTORS (value-taking, separate-word): a create under
            # any of these mints in a DIFFERENT tenant/db than the flag-less
            # follow-up `update` would target, so a create carrying one is
            # EXCLUDED from forcing (wrong-tenant blocker). Mark it AND consume
            # the value. `--global` (boolean) is handled just below.
            -C|--directory|--db)
                create_tenant_selector=1
                expect_value=1
                ;;
            # Other value-taking GLOBAL flags in separate-word form: skip their
            # value. This set must track beads' persistent String flags (bd
            # `cmd/bd/main.go`); `--format` is a hidden String alias for `--json`.
            --actor|--dolt-auto-commit|--format)
                expect_value=1
                ;;
            # `--global` selects the shared-server DB — also a tenant selector.
            --global)
                create_tenant_selector=1
                ;;
            # Root-level `--` end-of-flags terminator: everything after it is
            # positional to bd's ROOT command, so no subcommand follows and
            # there is nothing to guard. `break` (do not merely skip) so
            # `bd -- update x --claim` is never mis-detected — it performs no
            # update, and flagging it would be a spurious block in fail mode.
            --)
                break
                ;;
            # `=`-forms and clustered short form of the value-taking tenant
            # selectors (a path value is always "set", no truthy check needed).
            -C=*|--directory=*|--db=*|-C?*)
                create_tenant_selector=1
                ;;
            # `--global=<truthy>` boolean =-form: a truthy value selects the
            # shared-server db (must precede the generic `--*=*` skip below, which
            # would otherwise swallow it and leave the create wrongly forced).
            --global=*)
                case "${arg#*=}" in
                    0|f|F|false|FALSE|False) : ;;
                    *) create_tenant_selector=1 ;;
                esac
                ;;
            # `=`-form or boolean global flags are single self-contained
            # tokens; just skip them.
            --*=*) : ;;
            -*) : ;;
            *)
                # First positional token = the subcommand.
                case "$arg" in
                    update)
                        phase="args"
                        guarded_sub="update"
                        ;;
                    ready)
                        # `bd ready --claim` claims a ready item -> in_progress
                        # (beads' advertised "grab work" path). Scan ONLY for
                        # --claim in a dedicated `ready` phase — NOT the update
                        # phase — so a bare `bd ready` list (or `bd ready --status
                        # <x>` filtering) is NEVER misread as a status write.
                        phase="ready"
                        guarded_sub="ready"
                        ;;
                    reopen)
                        # `bd reopen` sets status to the non-lifecycle `open`.
                        # Single-token op — flag it and stop scanning.
                        saw_reopen=1
                        break
                        ;;
                    defer)
                        # `bd defer <id>` sets status to the non-lifecycle
                        # `deferred` (a direct status write, exactly the `reopen`
                        # shape). Single-token op — flag it and stop scanning.
                        saw_defer=1
                        break
                        ;;
                    create|new|q)
                        # create / new (aliases) and q (quick-capture) all mint
                        # a NEW item that bd v1.0.5 hardcodes to the non-lifecycle
                        # `open`. Enter a dedicated `create` phase to detect the
                        # exclusions; the passthrough tail then forces a
                        # QUALIFYING create to lifecycle `backlog`. Do NOT break —
                        # keep scanning the create's flags.
                        is_create=1
                        phase="create"
                        ;;
                    *)
                        # Not a guarded subcommand: nothing to guard.
                        break
                        ;;
                esac
                ;;
        esac
        continue
    fi

    if [ "$phase" = "ready" ]; then
        # ready phase: ONLY --claim matters. `bd ready` has no lifecycle --status
        # write, so we deliberately do NOT scan for --status here (avoids a
        # false-positive block on a `bd ready --status <x>` list filter).
        case "$arg" in
            --claim) saw_claim=1 ;;
            --claim=*)
                case "${arg#--claim=}" in
                    0|f|F|false|FALSE|False) : ;;
                    *) saw_claim=1 ;;
                esac
                ;;
            *) : ;;
        esac
        continue
    fi

    if [ "$phase" = "create" ]; then
        # create phase: detect the EXCLUSIONS that must NOT be forced to
        # `backlog` (event type, ephemeral, dry-run, batch) and capture any
        # future create-time --status. Value-taking flags have their value
        # skipped so a value that LOOKS like an exclusion flag (e.g. a --title of
        # "--ephemeral") is never misread. Flag set derived from `bd create
        # --help` on bd v1.0.5.
        case "$arg" in
            --)
                # End-of-flags: everything after is the positional title, never
                # a flag — no further exclusion can appear, so stop scanning.
                break
                ;;
            # Exclusions: ephemeral / dry-run (bare boolean forms), and --help/-h
            # (prints help + creates nothing; its help TEXT carries example ids).
            --ephemeral|--dry-run|--help|-h)
                create_excluded=1
                ;;
            # `=`-forms of the boolean exclusions: exclude on a TRUTHY value only
            # (mirrors the --claim=* idiom), so `--ephemeral=false` / `--dry-run=false`
            # — which DO create a real item — are still forced.
            --ephemeral=*|--dry-run=*)
                case "${arg#*=}" in
                    0|f|F|false|FALSE|False) : ;;
                    *) create_excluded=1 ;;
                esac
                ;;
            # --type/-t: CAPTURE the value (a value of `event` excludes). Handled
            # before the generic value-skip so the type value is inspected.
            --type|-t)
                want_type_value=1
                ;;
            --type=*)
                create_type="${arg#--type=}"
                ;;
            -t=*)
                create_type="${arg#-t=}"
                ;;
            -t?*)
                # Clustered short form: -tVALUE
                create_type="${arg#-t}"
                ;;
            # Batch creates mint MANY ids from a file/graph; forcing a single id
            # is not meaningful, so SKIP forcing for batch (documented; left to
            # the store normalizer). Separate, =-form, AND clustered `-fFILE`.
            --file|-f|--graph|--file=*|-f=*|--graph=*|-f?*)
                create_batch=1
                ;;
            # TENANT/DB SELECTORS placed AFTER the subcommand. bd is cobra:
            # persistent flags are equally valid after `create` (that is how
            # `bd create ... --json` works), so `-C`/`--directory`/`--db`/
            # `--global`/`--repo` can appear HERE, not only in the global phase.
            # Any of them means the create mints in a DIFFERENT tenant/db than
            # the flag-less follow-up `update` would target — a wrong-tenant risk
            # — so EXCLUDE such a create from forcing. Mirror the global phase.
            # Value-taking ones (`-C`/`--directory`/`--db`/`--repo`) consume their
            # separate-word value too.
            -C|--directory|--db|--repo)
                create_tenant_selector=1
                expect_value=1
                ;;
            -C=*|--directory=*|--db=*|--repo=*|-C?*)
                create_tenant_selector=1
                ;;
            --global)
                create_tenant_selector=1
                ;;
            --global=*)
                case "${arg#*=}" in
                    0|f|F|false|FALSE|False) : ;;
                    *) create_tenant_selector=1 ;;
                esac
                ;;
            # Future-proofing: a create-time --status/-s (absent on v1.0.5).
            # CAPTURE it so a lifecycle value is respected (not overridden).
            --status|-s)
                want_create_status=1
                ;;
            --status=*)
                create_status_value="${arg#--status=}"
                ;;
            -s=*)
                create_status_value="${arg#-s=}"
                ;;
            -s?*)
                create_status_value="${arg#-s}"
                ;;
            # Value-taking CREATE flags (separate-word form): skip their value so
            # a value like "--ephemeral" or "event" is not misread. This is the
            # `bd create --help` value-taking set MINUS the specially-handled
            # --type/-t, --file/-f, --graph, --repo, and --status/-s above.
            --acceptance|--append-notes|-a|--assignee|--body-file|--context|\
            --defer|--deps|-d|--description|--design|--design-file|--due|-e|\
            --estimate|--event-actor|--event-category|--event-payload|\
            --event-target|--external-ref|--id|-l|--labels|--metadata|\
            --mol-type|--notes|--parent|-p|--priority|--skills|\
            --spec-id|--title|--waits-for|--waits-for-gate|--wisp-type)
                expect_value=1
                ;;
            *)
                : # positional title, boolean flag, or =-form value — ignore.
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
        --claim=*)
            # bd's `--claim` is a pflag boolean, so the `=`-form sets it too.
            # Treat any truthy value as a claim; leave only an explicit false
            # (the values bd itself accepts as false) unflagged.
            case "${arg#--claim=}" in
                0|f|F|false|FALSE|False) : ;;
                *) saw_claim=1 ;;
            esac
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

if [ "$saw_reopen" -eq 1 ]; then
    violated=1
    _bdg_op="reopen"
    guard_warn "bd reopen" "bd update --status <lifecycle> (e.g. backlog)"
fi

if [ "$saw_defer" -eq 1 ]; then
    violated=1
    _bdg_op="defer"
    guard_warn "bd defer" "bd update --status <lifecycle> (e.g. backlog)"
fi

if [ "$saw_claim" -eq 1 ]; then
    violated=1
    _bdg_op="claim"
    guard_warn "bd $guarded_sub --claim" "--status active"
fi

if [ -n "$status_value" ]; then
    case "$LIFECYCLE_STATUSES" in
        *" $status_value "*)
            : # conformant lifecycle status — no violation.
            ;;
        *)
            violated=1
            _bdg_op="status:$status_value"
            if [ "$status_value" = "in_progress" ]; then
                guard_warn "bd update --status $status_value" "--status active"
            else
                guard_warn "bd update --status $status_value" \
                    "one of:$LIFECYCLE_STATUSES(or 'bd close')"
            fi
            ;;
    esac
fi

# Create-normalization verdict: decide whether this create should be forced to
# lifecycle `backlog`. Qualifying = a create/new/q that is NOT excluded (event
# type / ephemeral / dry-run / help), NOT a batch (file/graph), NOT carrying a
# tenant/db selector (-C/--directory/--db/--global/--repo — the follow-up update
# would otherwise hit the wrong tenant), and NOT already carrying a LIFECYCLE
# --status (a lifecycle value is respected; a non-lifecycle value is still
# normalized). This never sets `violated` — a create is never blocked, only
# normalized.
is_forced_create=0
if [ "$is_create" -eq 1 ] && [ "$create_excluded" -eq 0 ] && [ "$create_batch" -eq 0 ] \
        && [ "$create_tenant_selector" -eq 0 ]; then
    case "$create_type" in
        event)
            : # audit event bead — not a work item; do not force.
            ;;
        *)
            is_forced_create=1
            if [ -n "$create_status_value" ]; then
                case "$LIFECYCLE_STATUSES" in
                    *" $create_status_value "*)
                        is_forced_create=0 # already a lifecycle status — respect it.
                        ;;
                    *)
                        : # non-lifecycle status — still normalize to backlog.
                        ;;
                esac
            fi
            ;;
    esac
fi

# --- new-id extraction (FORM-ANCHORED, never first-token-anywhere) -----------
# Extract the NEW issue id from a create's stdout. beads v1.0.5's legacy --json
# (the DEFAULT when BD_JSON_ENVELOPE is unset) re-marshals the issue through a
# map with ALPHABETICALLY-SORTED keys, so `assignee`/`created_by`/`description`/
# `external_ref` all precede `"id"`. A naive first-hyphenated-token grep would
# then grab a REAL id embedded in e.g. `--description "Discovered from bd-x"` and
# demote the wrong item. So anchor on the OUTPUT FORM, in order:
#   1. JSON (stdout starts with `{`)  -> the FIRST `"id": "<v>"` field. Safe in
#      BOTH json modes (envelope has id first in data; legacy sorts metadata
#      after id) and JSON-escaping guarantees no literal `"id":` inside a value.
#   2. a line containing `Created issue: ` -> the token immediately AFTER it.
#   3. the whole trimmed output is a single id token -> use it (--silent / q).
#   4. else nothing (skip the follow-up; the store normalizer catches it).
# The candidate is then VALIDATED against the beads id shape
# (`^[a-z][a-z0-9]*(-[a-z0-9]+)+$`); anything else yields empty. $1 = stdout.
_bdg_extract_id() {
    _eo="$1"
    _cand=""
    case "$_eo" in
        "{"*)
            _idf=$(printf '%s\n' "$_eo" | grep -oE '"id"[[:space:]]*:[[:space:]]*"[^"]*"' | head -n1)
            _cand=$(printf '%s' "$_idf" | grep -oE '"[^"]*"$' | tr -d '"')
            ;;
        *"Created issue: "*)
            _rest=${_eo#*Created issue: }
            _cand=$(printf '%s' "${_rest%% *}" | tr -d '[:space:]')
            ;;
        *)
            _cand=$(printf '%s' "$_eo" | tr -d '[:space:]')
            ;;
    esac
    # Reject empty, any non-id char, or a leading/trailing hyphen.
    case "$_cand" in
        ""|*[!a-z0-9-]*|-*|*-) return ;;
    esac
    # Require: starts lowercase-alpha AND contains at least one hyphen group.
    case "$_cand" in
        [a-z]*-*) printf '%s' "$_cand" ;;
    esac
}

# --- telemetry emit (default ON; disable: LIVESPEC_BD_GUARD_OTLP=off) ---------
# Fire a DETACHED, FAIL-OPEN bd.invoke OTLP span at the local collector. Emitted
# for BOTH passthrough AND fail-mode blocks, so enforcement is OBSERVABLE: a
# block is queryable as guard.mode=fail + guard.warned=1 + exit_code=3. The emit
# can never delay or change bd's result. Args: $1=exit_code $2=start_ns $3=end_ns.
_bdg_emit_span() {
    [ "${LIVESPEC_BD_GUARD_OTLP:-on}" = "off" ] && return 0
    command -v python3 >/dev/null 2>&1 || return 0
    _bdg_emit="${LIVESPEC_BD_GUARD_EMIT:-$(dirname -- "$0")/bd-guard-emit.py}"
    [ -f "$_bdg_emit" ] || return 0
    _bdg_ppid=$PPID
    _bdg_comm=$(cat "/proc/$_bdg_ppid/comm" 2>/dev/null || echo "")
    _bdg_cmd=$(tr '\0' ' ' < "/proc/$_bdg_ppid/cmdline" 2>/dev/null | cut -c1-160)
    BDG_ARGV="$_bdg_argv" BDG_WARNED="$violated" BDG_OP="$_bdg_op" BDG_MODE="$MODE" \
    BDG_EXIT="$1" BDG_START_NS="$2" BDG_END_NS="$3" \
    BDG_PPID="$_bdg_ppid" BDG_COMM="$_bdg_comm" BDG_CALLER_CMD="$_bdg_cmd" \
    BDG_CWD="$PWD" \
        setsid python3 "$_bdg_emit" >/dev/null 2>&1 </dev/null &
}

if [ "$violated" -eq 1 ] && [ "$MODE" = "fail" ]; then
    # fail mode: BLOCK without execing. Emit a span FIRST (so the block is
    # observable to telemetry), then exit non-zero. Messages already on stderr.
    _bdg_now=$(date +%s%N 2>/dev/null || echo 0)
    _bdg_emit_span 3 "$_bdg_now" "$_bdg_now"
    exit 3
fi

# --- create normalization (force lifecycle `backlog`) ------------------------
# A qualifying create reaches here (create never trips a violation). Run the
# real create in the FOREGROUND capturing ONLY its stdout (stderr flows through
# live, byte-for-byte); on success, FORM-ANCHORED extract the new id and
# FAIL-OPEN force it to `backlog` via a direct `bd update` (bypassing this guard;
# `backlog` is already a lifecycle status). The create's stdout is REPLAYED ONLY
# AFTER the follow-up update returns, so a consumer that reads the id and
# immediately updates the item cannot race the guard's own backlog update. A
# follow-up failure NEVER changes the create's exit code or output — a stranded
# `open` is caught by the store normalizer. This branch runs regardless of the
# OTLP setting (the span emit is a no-op when OTLP is off), so a qualifying
# create can never take the plain `exec` path below.
if [ "$is_forced_create" -eq 1 ]; then
    _bdg_op="create-forced-backlog"   # telemetry: enforcement is observable
    _bdg_cstart=$(date +%s%N 2>/dev/null || echo 0)
    _bdg_cout=$("$REAL" "$@")
    _bdg_crc=$?
    _bdg_cend=$(date +%s%N 2>/dev/null || echo 0)
    if [ "$_bdg_crc" -eq 0 ]; then
        _bdg_newid=$(_bdg_extract_id "$_bdg_cout")
        if [ -n "$_bdg_newid" ]; then
            "$REAL" update "$_bdg_newid" --status backlog >/dev/null 2>&1 || :
        fi
    fi
    # Replay captured stdout AFTER the follow-up update (see above). Command
    # substitution stripped trailing newlines; bd's create output ends in exactly
    # one, so restore a single one. Guard the empty case so a failed/silent create
    # does not gain a spurious blank line.
    if [ -n "$_bdg_cout" ]; then
        printf '%s\n' "$_bdg_cout"
    fi
    _bdg_emit_span "$_bdg_crc" "$_bdg_cstart" "$_bdg_cend"
    exit "$_bdg_crc"
fi

# Passthrough. With OTLP off, transparent exec (zero overhead). With OTLP on, run
# bd in the FOREGROUND (TTY + signals preserved) to capture exit + duration, then
# fire the detached span.
if [ "${LIVESPEC_BD_GUARD_OTLP:-on}" = "off" ]; then
    exec "$REAL" "$@"
fi

_bdg_start=$(date +%s%N 2>/dev/null || echo 0)
"$REAL" "$@"
_bdg_rc=$?
_bdg_end=$(date +%s%N 2>/dev/null || echo 0)
_bdg_emit_span "$_bdg_rc" "$_bdg_start" "$_bdg_end"
exit "$_bdg_rc"
