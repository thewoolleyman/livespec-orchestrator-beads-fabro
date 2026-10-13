#!/usr/bin/env bash
# session-wait-probe-timeout-proof.sh - the REPLAYABLE Proof-of-Done recipe for
# work-item bd-ib-jqvqlf, "session_wait ends a bounded wait when a gate-status
# probe times out, reporting a running gate as unavailable".
#
# WHY THIS IS A TRACKED FILE RATHER THAN A SCRATCH SCRIPT
#
# The Proof-of-Done legs are two INDEPENDENT sessions: `proof_capture` authors
# and runs reproduction steps, and `proof_verify` replays those same steps
# verbatim on a different adapter. That makes a published step a program a
# STRANGER has to run unchanged, and it is the reason the first capture of this
# item was graded `not_reproduced`: every proof-producing step named a FIXED
# `--wait-id`, which the capture's own execution had already consumed in the
# sandbox's wait store. A wait id is single-use - `_register_wait` in
# `_session_wait_records.py` returns `REGISTRATION_CONFLICT` when the record
# path merely EXISTS, live or not - so the replay refused at registration
# before launching a single probe, and NOTHING about the per-probe-timeout
# behaviour was exercised. The refusal looked like a defect in the tree; it was
# a defect in the recipe.
#
# So this recipe is built to be run unchanged, by anyone, any number of times:
#
#   - Every wait id, scratch path and shim marker is derived from a token that
#     is fresh per invocation (UTC timestamp + pid + nanoseconds), so two
#     sessions may replay concurrently without colliding.
#   - It touches ONLY gates and wait records it created itself, and it removes
#     exactly those on the way out - never a pre-existing gate run, never
#     another wait id's record, never anything tracked.
#   - It GRADES itself. Each expectation is checked, and the final line is a
#     machine-readable verdict with a non-zero exit on any failure, so a
#     replayer reads a verdict instead of re-deriving one from prose.
#
# Committing it is what makes its program text available to the replayer by
# construction: the complete source is in the tree the replay already has,
# at a path that does not move, so no step has to re-publish it.
#
# WHAT IT PROVES (the three Definition-of-Done assertions, in order)
#
#   Assertion 1 - a bounded wait over a still-RUNNING gate whose gate-status
#     probe exceeds the per-probe timeout keeps waiting, and the gate reads
#     RUNNING once a later probe completes.           -> proof 01, control 02
#   Assertion 2 - a bounded wait over a gate that genuinely finishes returns
#     that gate's own terminal state and exit code at the existing polling
#     cadence.                                        -> proof 03
#   Assertion 3 - a COMPLETED probe carrying no state line still ends the wait
#     with the distinct unavailable outcome.          -> proof 04
#
# Proof 02 is the CONTROL, and it is what makes proof 01 evidence about this
# change rather than about the host: it re-runs the identical request against a
# tree whose ONLY difference is `_session_wait_gate.py` restored from
# `origin/master`, and that run must end `target-ended` / `UNAVAILABLE` on the
# very gate that is still running.
#
# USAGE
#
#   dev-tooling/session-wait-probe-timeout-proof.sh
#
# Run it from the repository root. It needs `mise`, `just` with the
# worktree-discipline pack installed (`just install-worktree-pack`, which
# `just bootstrap` delegates to - the `gate-*` recipes come from there),
# `python3`, and a reachable `origin` for the control's `git show
# origin/master:...`. It takes about 70 seconds, almost all of it the two
# deadline-bound waits. No credential is required and none is read.

set -uo pipefail

# Deliberately NOT `set -e`: several steps read a NON-ZERO exit as the evidence
# they are collecting (the off-PATH probe exits 127, and a refusing gate exits
# 7), so an errexit shell would abort on its own proof.

readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

# One fresh token per invocation. The nanoseconds field is what makes two
# invocations in the same second distinct, and the pid covers two shells that
# somehow read the same nanosecond.
readonly TOKEN="$(date -u +%Y%m%dT%H%M%SZ)-$$-$(date +%N)"
readonly SCRATCH="${TMPDIR:-/tmp}/bd-ib-jqvqlf-proof/$TOKEN"
readonly SHIM_BIN="$SCRATCH/shim-bin"
readonly MARKER="$SCRATCH/first-probe-slow.marker"
readonly MASTER_PLUGIN="$SCRATCH/master-plugin"
readonly WAIT_STORE="$REPO_ROOT/tmp/session-waits"
readonly GATE_STORE="$REPO_ROOT/tmp/gate-runs"
readonly CHANGED_MODULE="scripts/livespec_orchestrator_beads_fabro/commands/_session_wait_gate.py"

# Gates this invocation started, so cleanup can reap exactly those.
declare -a CREATED_GATES=()
# Wait ids this invocation registered, so cleanup can remove exactly those.
declare -a CREATED_WAIT_IDS=()

failures=0
checks=0

say() { printf '%s\n' "$*"; }
section() { printf '\n========== %s ==========\n' "$*"; }

# One graded expectation. Prints PASS/FAIL with the expected and actual values,
# so the transcript this emits IS the proof rather than a summary of it.
expect() {
    local label="$1" expected="$2" actual="$3"
    checks=$((checks + 1))
    if [[ "$actual" == "$expected" ]]; then
        printf '  PASS  %-46s expected=%s actual=%s\n' "$label" "$expected" "$actual"
    else
        printf '  FAIL  %-46s expected=%s actual=%s\n' "$label" "$expected" "$actual"
        failures=$((failures + 1))
    fi
}

# A numeric-range expectation, for the timing claims. A wait that held its
# deadline and a wait that returned at its first probe differ by an order of
# magnitude, so a range is the honest assertion and an equality would be a
# flake on a loaded host.
expect_between() {
    local label="$1" low="$2" high="$3" actual="$4"
    checks=$((checks + 1))
    if awk -v a="$actual" -v l="$low" -v h="$high" 'BEGIN{exit !(a>=l && a<=h)}'; then
        printf '  PASS  %-46s expected=%s..%s actual=%s\n' "$label" "$low" "$high" "$actual"
    else
        printf '  FAIL  %-46s expected=%s..%s actual=%s\n' "$label" "$low" "$high" "$actual"
        failures=$((failures + 1))
    fi
}

# Read one field out of a session-wait JSON result. The reader is here, in the
# tracked recipe, rather than inline at each call site, so the replayer has one
# program text to read instead of four.
#
#   field  command_outcome | trigger_exit_code | unfinished_count
#          state:<gate-run-id> | exit_code:<gate-run-id> | trigger_is:<gate-run-id>
json_field() {
    local payload="$1" field="$2"
    printf '%s' "$payload" | python3 -c '
import json, sys

payload = json.loads(sys.stdin.read())
field = sys.argv[1]


def observation(run_id):
    """The observation whose target identity ends in this gate run id."""
    for identity, value in (payload.get("observations") or {}).items():
        if identity.endswith(":" + run_id):
            return value
    return None


if field == "command_outcome":
    print(payload.get("command_outcome"))
elif field == "trigger_exit_code":
    print(payload.get("trigger_exit_code"))
elif field == "unfinished_count":
    print(len(payload.get("unfinished_targets") or []))
elif field.startswith("state:"):
    found = observation(field.split(":", 1)[1])
    print((found or {}).get("state"))
elif field.startswith("exit_code:"):
    found = observation(field.split(":", 1)[1])
    print((found or {}).get("exit_code"))
elif field.startswith("trigger_is:"):
    trigger = payload.get("trigger_target") or ""
    print(str(trigger.endswith(":" + field.split(":", 1)[1])).lower())
elif field.startswith("unfinished_has:"):
    run_id = field.split(":", 1)[1]
    targets = payload.get("unfinished_targets") or []
    print(str(any(t.endswith(":" + run_id) for t in targets)).lower())
else:
    raise SystemExit("unknown field " + field)
' "$field" 2>/dev/null
}

# Start a detached gate and remember it for cleanup. The run id is published
# in the GLOBAL `started_gate_run_id` rather than echoed to stdout, and the
# difference is load-bearing: a caller that reads an echoed id has to use a
# command substitution, which runs this function in a SUBSHELL, and the
# `CREATED_GATES` append would then be made in a child process and lost. The
# first draft of this recipe did exactly that, and the result was a cleanup
# that printed no reap line at all while two `sleep` gate trees kept running
# after the verdict - a leak whose only symptom was the ABSENCE of output.
started_gate_run_id=""
start_gate() {
    local run_id
    run_id=$(mise exec -- just gate-start -- "$@" 2>/dev/null | tail -1)
    if [[ -z "$run_id" ]]; then
        say "FATAL: gate-start printed no run id for: $*"
        say "       Is the worktree-discipline pack installed? Run: just install-worktree-pack"
        return 1
    fi
    CREATED_GATES+=("$run_id")
    started_gate_run_id="$run_id"
}

# Kill a process and every descendant, deepest first. `gate-run.sh` puts its
# own `__child` supervisor in the pid file, that supervisor re-execs another
# copy of itself, and the real command hangs off THAT - so a single `kill`
# plus one level of `pkill -P` leaves the innermost process alive, which is
# how the leak above survived its own cleanup.
kill_tree() {
    local pid="$1" child
    for child in $(pgrep -P "$pid" 2>/dev/null); do
        kill_tree "$child"
    done
    kill "$pid" 2>/dev/null
    sleep 0.1
    if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null
    fi
}

# The operator's own surface for one gate, reduced to its state/exit/verdict
# lines. This is the independent instrument every assertion cross-checks the
# wait against: the wait's reading has to agree with what an operator sees.
gate_lines() {
    mise exec -- just gate-status "$1" 2>&1 |
        grep -E "^[[:space:]]*(state|exit_code|VERDICT)"
}

gate_state() {
    gate_lines "$1" | sed -n 's/^[[:space:]]*state[[:space:]]*:[[:space:]]*//p' | head -1
}

# Remove only what this invocation created. Called explicitly before the
# verdict so its own hygiene check can still fail the run, and left on the EXIT
# trap so an early exit still reaps; the guard makes the second call a no-op.
cleaned=0
cleanup() {
    if [[ "$cleaned" -eq 1 ]]; then
        return 0
    fi
    cleaned=1
    section "CLEANUP - only what this invocation created"
    local run_id pid
    for run_id in "${CREATED_GATES[@]+"${CREATED_GATES[@]}"}"; do
        pid=$(cat "$GATE_STORE/$run_id/pid" 2>/dev/null)
        if [[ -n "$pid" ]]; then
            kill_tree "$pid"
        fi
        # Grade the reap on the WHOLE tree, not on the pid-file process alone.
        # Every `gate-run.sh` process of this gate carries the gate's own run
        # directory in its command line, so this counts the survivors by name
        # instead of trusting that killing the top killed the rest - which is
        # the mistake that let the first draft's leak report a clean cleanup.
        local survivors
        survivors=$(pgrep -fc "$GATE_STORE/$run_id" 2>/dev/null || true)
        survivors=${survivors:-0}
        if [[ "$survivors" -eq 0 ]]; then
            say "  gate $run_id reaped with its descendants (0 survivors)"
        else
            say "  gate $run_id STILL HAS $survivors live process(es) after kill -9"
            failures=$((failures + 1))
        fi
        rm -rf "$GATE_STORE/$run_id"
    done
    local wait_id
    for wait_id in "${CREATED_WAIT_IDS[@]+"${CREATED_WAIT_IDS[@]}"}"; do
        rm -f "$WAIT_STORE/$wait_id.json"
        say "  wait record $wait_id removed"
    done
    rm -rf "$SCRATCH"
    say "  scratch $SCRATCH removed"
    # Nothing TRACKED may have changed. This is the recipe's own hygiene
    # check, graded rather than merely assumed, because the capture and verify
    # stages are both READ-ONLY on the tree.
    #
    # It grades `--untracked-files=no` deliberately. The recipe writes only
    # into the gitignored `tmp/` (its gates and wait records) and into the
    # scratch directory outside the clone, so a modified tracked file would be
    # a real escape, while the untracked count is not the recipe's to own - a
    # session may legitimately be carrying an untracked file of its own, and
    # grading that would make this recipe fail on a tree it never touched.
    # The full count is still PRINTED, because the capture stage owes an empty
    # one before it posts and this is where it reads it.
    local tracked_dirty full_dirty
    tracked_dirty=$(git status --porcelain --untracked-files=no | wc -l)
    full_dirty=$(git status --porcelain | wc -l)
    say "  modified TRACKED files: $tracked_dirty (MUST be 0)"
    say "  git status --porcelain lines, including untracked: $full_dirty"
    if [[ "$tracked_dirty" != "0" ]]; then
        failures=$((failures + 1))
    fi
}
trap cleanup EXIT

# Elapsed wall-clock seconds, to two decimals, for the timing claims.
now() { date +%s.%N; }
elapsed_since() { awk -v s="$1" -v e="$(now)" 'BEGIN{printf "%.2f", e-s}'; }

mkdir -p "$SCRATCH" "$SHIM_BIN" || exit 1

say "work-item   : bd-ib-jqvqlf"
say "recipe      : dev-tooling/session-wait-probe-timeout-proof.sh"
say "token       : $TOKEN"
say "scratch     : $SCRATCH"
say "head        : $(git rev-parse HEAD)"
say "repo root   : $REPO_ROOT"

# ---------------------------------------------------------------------------
# The first-call-slow `mise` shim.
#
# Placed first on PATH it makes the session wait's FIRST gate-status probe
# exceed the per-probe timeout (`GateStatusLauncher.launch` clamps each probe
# to `min(1.0, max(0.01, timeout_seconds))`) and every later probe complete
# normally. That is exactly the loaded-host condition this item was filed for,
# produced deterministically instead of waited for.
#
# The marker is token-scoped, so a concurrent replay cannot arm or disarm this
# invocation's shim.
# ---------------------------------------------------------------------------
cat > "$SHIM_BIN/mise" <<SHIM
#!/bin/sh
# Generated by dev-tooling/session-wait-probe-timeout-proof.sh (token $TOKEN).
# SLOW on the FIRST invocation only; the real \`mise\` on every later one.
shim_dir=\$(CDPATH= cd -- "\$(dirname -- "\$0")" && pwd)
marker="$MARKER"
if [ ! -e "\$marker" ]; then
  : > "\$marker"
  sleep 3 </dev/null >/dev/null 2>&1
fi
PATH=\$(python3 -c 'import os,sys; print(os.pathsep.join(p for p in os.environ["PATH"].split(os.pathsep) if p != sys.argv[1]))' "\$shim_dir")
export PATH
exec mise "\$@"
SHIM
chmod +x "$SHIM_BIN/mise" || exit 1

say ""
say "--- the shim's complete source, as generated for this invocation ---"
cat "$SHIM_BIN/mise"

# ===========================================================================
section "ASSERTION 1 - a timed-out probe keeps the wait waiting (proof 01)"
# ===========================================================================

start_gate sleep 900 || exit 1
run1="$started_gate_run_id"
say "gate run id : $run1  (a gate that stays RUNNING for the whole proof)"

say ""
say "\$ just gate-status $run1   # before the wait"
gate_lines "$run1"
expect "gate is RUNNING before the wait" "RUNNING" "$(gate_state "$run1")"

# Establish that the shim really does breach the 1.0s per-probe clamp, by
# measuring the probe command itself. Without this, proof 01 would rest on an
# assumption about the shim rather than a measurement of it.
rm -f "$MARKER"
started=$(now)
PATH="$SHIM_BIN:$PATH" mise exec -- just gate-status "$run1" >/dev/null 2>&1
first_probe=$(elapsed_since "$started")
started=$(now)
PATH="$SHIM_BIN:$PATH" mise exec -- just gate-status "$run1" >/dev/null 2>&1
later_probe=$(elapsed_since "$started")
say ""
say "shim first-probe latency : ${first_probe}s   (must exceed the 1.0s clamp)"
say "shim later-probe latency : ${later_probe}s   (must complete well inside it)"
expect_between "first probe exceeds the 1.0s clamp" 1.01 600 "$first_probe"
expect_between "later probe completes inside the clamp" 0 0.99 "$later_probe"

wait_id1="$TOKEN-timeout"
CREATED_WAIT_IDS+=("$wait_id1")
rm -f "$MARKER"
say ""
say "\$ PATH=\$SHIM_BIN:\$PATH python3 .claude-plugin/scripts/bin/session_wait.py wait \\"
say "    --repo . --session-id $TOKEN-timeout --wait-id $wait_id1 \\"
say "    --deadline-seconds 25 --gate $run1"
started=$(now)
result1=$(PATH="$SHIM_BIN:$PATH" python3 .claude-plugin/scripts/bin/session_wait.py \
    wait --repo . --session-id "$TOKEN-timeout" --wait-id "$wait_id1" \
    --deadline-seconds 25 --gate "$run1" 2>&1)
cli1=$?
elapsed1=$(elapsed_since "$started")
printf '%s\n' "$result1"
say "elapsed_seconds=$elapsed1"
say "cli_exit=$cli1"

expect "command_outcome" "deadline" "$(json_field "$result1" command_outcome)"
expect "the gate reads RUNNING" "RUNNING" "$(json_field "$result1" "state:$run1")"
expect "the gate is reported unfinished" "true" "$(json_field "$result1" "unfinished_has:$run1")"
expect "nothing is named as the trigger" "None" "$(json_field "$result1" trigger_exit_code)"
expect "cli exit" "0" "$cli1"
# The whole point: the wait held its 25s deadline instead of returning at the
# ~1s probe timeout. 20s is the floor that separates those two outcomes.
expect_between "the wait held its deadline" 20 60 "$elapsed1"

say ""
say "\$ just gate-status $run1   # the gate was RUNNING throughout"
gate_lines "$run1"
expect "gate still RUNNING after the wait" "RUNNING" "$(gate_state "$run1")"

# ===========================================================================
section "ASSERTION 1 CONTROL - origin/master on the same gate (proof 02)"
# ===========================================================================
# Copy the plugin tree to scratch, restore ONLY the one module this change
# touches from origin/master, and re-run the IDENTICAL request against the very
# same still-running gate. If the control also held its deadline, proof 01
# would be evidence about the host and not about this change.

rm -rf "$MASTER_PLUGIN"
cp -r .claude-plugin "$MASTER_PLUGIN" || exit 1
find "$MASTER_PLUGIN" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null
git fetch --quiet origin master 2>/dev/null
if ! git show "origin/master:.claude-plugin/$CHANGED_MODULE" > "$MASTER_PLUGIN/$CHANGED_MODULE"; then
    say "FATAL: could not read $CHANGED_MODULE from origin/master; is origin reachable?"
    exit 1
fi

say "\$ diff -rq \$MASTER_PLUGIN .claude-plugin   # expect exactly ONE differing file"
differing=$(diff -rq "$MASTER_PLUGIN" .claude-plugin 2>&1 | grep -v __pycache__)
printf '%s\n' "$differing"
expect "exactly one file differs from master" "1" "$(printf '%s\n' "$differing" | grep -c .)"
expect "and it is the changed module" "1" "$(printf '%s\n' "$differing" | grep -c "_session_wait_gate.py")"

wait_id2="$TOKEN-control"
CREATED_WAIT_IDS+=("$wait_id2")
rm -f "$MARKER"
say ""
say "\$ PATH=\$SHIM_BIN:\$PATH python3 \$MASTER_PLUGIN/scripts/bin/session_wait.py wait \\"
say "    --repo \$PWD --session-id $TOKEN-control --wait-id $wait_id2 \\"
say "    --deadline-seconds 25 --gate $run1"
started=$(now)
result2=$(PATH="$SHIM_BIN:$PATH" python3 "$MASTER_PLUGIN/scripts/bin/session_wait.py" \
    wait --repo "$PWD" --session-id "$TOKEN-control" --wait-id "$wait_id2" \
    --deadline-seconds 25 --gate "$run1" 2>&1)
cli2=$?
elapsed2=$(elapsed_since "$started")
printf '%s\n' "$result2"
say "elapsed_seconds=$elapsed2"
say "cli_exit=$cli2"

expect "CONTROL command_outcome" "target-ended" "$(json_field "$result2" command_outcome)"
expect "CONTROL misreads the gate" "UNAVAILABLE" "$(json_field "$result2" "state:$run1")"
expect "CONTROL names the running gate as trigger" "true" "$(json_field "$result2" "trigger_is:$run1")"
expect "CONTROL reports nothing unfinished" "0" "$(json_field "$result2" unfinished_count)"
expect_between "CONTROL returned early, not at its deadline" 0 20 "$elapsed2"

say ""
say "\$ just gate-status $run1   # the gate the control called UNAVAILABLE is still RUNNING"
gate_lines "$run1"
expect "gate still RUNNING after the control" "RUNNING" "$(gate_state "$run1")"

# ===========================================================================
section "ASSERTION 2 - a gate that finishes wakes the wait (proof 03)"
# ===========================================================================
# A gate that runs for 8 seconds and then REFUSES with exit 7. The wait must
# return that gate's own verdict and exit code, at the polling cadence, and
# nowhere near its 60s deadline.

start_gate sh -c 'sleep 8; exit 7' || exit 1
run2="$started_gate_run_id"
say "gate run id : $run2  (runs 8s, then exits 7)"

wait_id3="$TOKEN-finish"
CREATED_WAIT_IDS+=("$wait_id3")
say ""
say "\$ python3 .claude-plugin/scripts/bin/session_wait.py wait \\"
say "    --repo . --session-id $TOKEN-finish --wait-id $wait_id3 \\"
say "    --deadline-seconds 60 --gate $run2"
started=$(now)
result3=$(python3 .claude-plugin/scripts/bin/session_wait.py \
    wait --repo . --session-id "$TOKEN-finish" --wait-id "$wait_id3" \
    --deadline-seconds 60 --gate "$run2" 2>&1)
cli3=$?
elapsed3=$(elapsed_since "$started")
returned_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf '%s\n' "$result3"
say "elapsed_seconds=$elapsed3"
say "cli_exit=$cli3"

expect "command_outcome" "target-ended" "$(json_field "$result3" command_outcome)"
expect "the gate's ACTUAL terminal state" "FAILED" "$(json_field "$result3" "state:$run2")"
expect "the gate's ACTUAL exit code" "7" "$(json_field "$result3" "exit_code:$run2")"
expect "trigger_exit_code" "7" "$(json_field "$result3" trigger_exit_code)"
expect "the finished gate is the trigger" "true" "$(json_field "$result3" "trigger_is:$run2")"
expect "nothing left unfinished" "0" "$(json_field "$result3" unfinished_count)"
expect "cli exit" "0" "$cli3"
# At the polling cadence: the gate's own 8s plus launch and one poll round -
# emphatically not the 60s deadline.
expect_between "woke at the gate's end, not the deadline" 8 30 "$elapsed3"

say ""
say "wait_returned_at = $returned_at"
say "gate_finished_at = $(cat "$GATE_STORE/$run2/finished_at" 2>&1)"
say "gate_exit_code   = $(cat "$GATE_STORE/$run2/exit_code" 2>&1)"
expect "the gate recorded exit 7 itself" "7" "$(cat "$GATE_STORE/$run2/exit_code" 2>/dev/null)"

say ""
say "\$ just gate-status $run2   # the operator's own surface agrees"
gate_lines "$run2"
expect "operator surface agrees: FAILED" "FAILED" "$(gate_state "$run2")"

# ===========================================================================
section "ASSERTION 3 - a completed probe with no state line is UNAVAILABLE (proof 04)"
# ===========================================================================
# The distinct unavailable outcome the contract permits is PRESERVED. This
# change suppresses only the exit-124 timeout case, so a probe that COMPLETED
# and simply could not read the gate must still end the wait as unavailable.
# Taking the recipe runner off PATH produces that condition: the probe exits
# 127 immediately, carrying no state line.

start_gate sleep 300 || exit 1
run3="$started_gate_run_id"
say "gate run id : $run3  (stays RUNNING; only the PROBE is broken here)"

say ""
say "\$ just gate-status $run3"
gate_lines "$run3"
expect "gate is RUNNING before the wait" "RUNNING" "$(gate_state "$run3")"

say ""
say "\$ PATH=/usr/bin:/bin sh -c \"mise exec -- just gate-status $run3; echo probe_exit=\\\$?\""
probe_out=$(PATH=/usr/bin:/bin sh -c "mise exec -- just gate-status $run3; echo probe_exit=\$?" 2>&1)
printf '%s\n' "$probe_out"
expect "the probe COMPLETED (did not time out)" "1" "$(printf '%s\n' "$probe_out" | grep -c 'probe_exit=127')"
state_lines=$(PATH=/usr/bin:/bin sh -c "mise exec -- just gate-status $run3" 2>&1 |
    grep -cE "^[[:space:]]*state[[:space:]]*:")
say "state lines in the probe output: $state_lines"
expect "the completed probe carries no state line" "0" "$state_lines"

wait_id4="$TOKEN-unavail"
CREATED_WAIT_IDS+=("$wait_id4")
say ""
say "\$ PATH=/usr/bin:/bin /usr/bin/python3 .claude-plugin/scripts/bin/session_wait.py wait \\"
say "    --repo . --session-id $TOKEN-unavail --wait-id $wait_id4 \\"
say "    --deadline-seconds 25 --gate $run3"
started=$(now)
result4=$(PATH=/usr/bin:/bin /usr/bin/python3 .claude-plugin/scripts/bin/session_wait.py \
    wait --repo . --session-id "$TOKEN-unavail" --wait-id "$wait_id4" \
    --deadline-seconds 25 --gate "$run3" 2>&1)
cli4=$?
elapsed4=$(elapsed_since "$started")
printf '%s\n' "$result4"
say "elapsed_seconds=$elapsed4"
say "cli_exit=$cli4"

expect "command_outcome" "target-ended" "$(json_field "$result4" command_outcome)"
expect "the distinct unavailable outcome survives" "UNAVAILABLE" "$(json_field "$result4" "state:$run3")"
expect "no exit code is invented" "None" "$(json_field "$result4" "exit_code:$run3")"
expect "the unreadable gate is the trigger" "true" "$(json_field "$result4" "trigger_is:$run3")"
expect "nothing left unfinished" "0" "$(json_field "$result4" unfinished_count)"
expect "cli exit" "0" "$cli4"
expect_between "returned promptly, not at its deadline" 0 20 "$elapsed4"

say ""
say "\$ just gate-status $run3   # the gate itself never ended"
gate_lines "$run3"
expect "the gate never ended" "RUNNING" "$(gate_state "$run3")"

cleanup

# ===========================================================================
section "VERDICT"
# ===========================================================================
say "checks run    : $checks"
say "checks failed : $failures"
if [[ "$failures" -eq 0 ]]; then
    say "PROOF RESULT  : PASSED - all three assertions of bd-ib-jqvqlf hold on this tree"
    exit 0
fi
say "PROOF RESULT  : FAILED - $failures of $checks graded checks did not hold"
exit 1
