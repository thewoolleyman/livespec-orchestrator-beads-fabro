"""The ABSOLUTE credential-use deadline, and the in-sandbox guard that enforces it.

WHY A GUARD EXISTS AT ALL. `_dispatcher_credential_requirement` derives an
ALLOWANCE -- a sum over per-operation bounds the engine enforces. That is not a
maximum wall clock and must never be presented as one: `fabro-core`'s executor
takes `retry_target` jumps no DOT edge expresses, and inter-stage work runs
outside every deadline a derivation multiplies. What turns the allowance into a
real maximum CREDENTIAL-USE duration is enforcement, and this module is it.

WHERE THE ENFORCEMENT HAS TO LIVE, which is the design constraint. It cannot be
host-side. A host watchdog that times out or kills its own waiting subprocess
stops a LOCAL PROCESS, not a remote worker: the sandbox keeps running and keeps
using the credential, and the host's own death would silently disarm the bound.
So the deadline is projected into the sandbox as an ABSOLUTE INSTANT and
enforced there, by a script that wraps every coding-agent launch. Nothing about
the enforcement depends on the Dispatcher still being connected.

WHY AN ABSOLUTE EPOCH RATHER THAN A DURATION. A duration restarts. The bound has
to survive a retry, a resumed launch and a later node start after an arbitrary
inter-stage or queue delay, and the only value with that property is an instant
computed once. Every launch re-reads the same number, so a node entered an hour
late gets an hour less and a retried node gets no fresh budget.

THE GRACE ENDS **BY** THE DEADLINE, which is the part that is easy to get
backwards and was wrong in this module's first draft. A guard that sent TERM at
the deadline and escalated to KILL some seconds later would permit those seconds
of credential use PAST the stated bound -- so the bound would not be the bound.
The reaper therefore signals TERM at `deadline - grace` and KILL **at**
`deadline`: a well-behaved agent still gets a chance to exit cleanly, and every
process is gone by the instant the deadline names. The grace is spent inside the
allowance, never after it.

THE CAP IS THE OTHER SUBTLE PART, and it is a correctness requirement rather
than conservatism. The deadline is NOT simply `projected_epoch + allowance`:
time passes between the final freshness measurement and the projection (a
bounded renewal request, a queue wait, sandbox preparation), and anchoring on
the projection instant alone would stamp a deadline LATER than the credential's
own usable life -- authorising work the token cannot cover. So the deadline is
also capped at the observed expiry minus the documented margin, and the EARLIER
of the two wins. The margin stays headroom exactly as `required_seconds`
promises; it is never spent as execution time.

FAIL-CLOSED, AND WHY THE ABSENT-DEADLINE ARM MATTERS. A guard that ran the
command when it could not read its own deadline would turn this whole mechanism
into decoration the first time a projection changed shape. The script refuses
when the variable is absent or unparseable, and says which.

THE REAPER DISARMS WHEN ITS GROUP IS FINISHED, and this is a correctness
requirement rather than hygiene. The first draft never cancelled the reaper --
correctly, because the adapter is often not the process holding the credential,
so cancelling on the direct child's exit left a grandchild unbounded. But it
bought that by sleeping blindly to the deadline and then signalling. At the
allowance this actually runs at, roughly seven days, a one-second command left a
kill armed against a RECYCLABLE pid/pgid for a week; inside a long-lived sandbox
that number is reused by ordinary work, so the reaper could signal a group it
never launched. The reaper therefore polls, and OWNERSHIP decides: it disarms the
first pass on which the group is finished or no longer ours, and it stays armed
while any member survives.

WHAT "OURS" MEANS, STATED NARROWLY SO THE GUARANTEE IS NOT OVERSOLD. Polling a
bare numeric pgid narrows the exposure but proves nothing -- the group can empty
and the number be reused between two passes. So the leader's INCARNATION (its
`/proc/<pid>/stat` start time) is recorded at launch and checked on every pass
and again immediately before each signal: a resident leader with that start time
is unambiguously ours, a resident leader with a different one is a recycled id
and disarms, and an absent leader means surviving members carrying that pgrp are
still ours because claiming the id requires a process whose pid equals it. The
residual window is the check-then-signal race inherent to signalling by pid on
POSIX -- sh has no pidfd -- NOT the multi-day exposure a blind sleep carried.
This is a bounded-exposure claim, not a proof that a recycled identifier can
never be signalled.
"""

from __future__ import annotations

__all__: list[str] = [
    "CREDENTIAL_EXPIRY_ENV_VAR",
    "CREDENTIAL_REQUIRED_REMAINING_ENV_VAR",
    "CREDENTIAL_USE_DEADLINE_ENV_VAR",
    "GUARD_REFUSAL_EXIT_CODE",
    "GUARD_SCRIPT_PATH",
    "GUARD_TERM_GRACE_SECONDS",
    "credential_use_deadline_epoch_capped",
    "guard_script_text",
    "guarded_acp_command",
]

# The ONE name the host writes and the sandbox reads. Spelled once, because a
# producer and a consumer that disagree about it leave the guard permanently
# unable to read a deadline -- which, fail-closed, refuses every dispatch.
CREDENTIAL_USE_DEADLINE_ENV_VAR = "LIVESPEC_CREDENTIAL_USE_DEADLINE_EPOCH"

# The two inputs the STARTUP grade needs, and the reason it is a different
# measurement from the deadline check beside it. The deadline bounds how long
# execution may CONTINUE; these decide whether it may BEGIN, by letting the
# sandbox re-measure the credential's remaining lifetime against its OWN clock.
# Admission already graded that lifetime, but it did so on the host at an earlier
# instant, and queueing or preparation can age the credential below the
# requirement in between -- which is exactly the window a deadline check cannot
# see, because a deadline stamped from a long allowance stays comfortably future
# while the credential underneath it expires.
CREDENTIAL_EXPIRY_ENV_VAR = "LIVESPEC_CREDENTIAL_EXPIRY_EPOCH"
CREDENTIAL_REQUIRED_REMAINING_ENV_VAR = "LIVESPEC_CREDENTIAL_REQUIRED_REMAINING_SECONDS"

# Where the prepare step writes the guard inside the sandbox.
GUARD_SCRIPT_PATH = "/workspace/.livespec/credential-use-guard.sh"

# Distinct from 1 so a refusal is distinguishable from the wrapped command's own
# failure: an operator reading a stage failure needs to know whether the agent
# ran and failed or never started.
GUARD_REFUSAL_EXIT_CODE = 78

# Spent INSIDE the allowance, before the deadline, never after it. See the
# module docstring: a grace that ran past the deadline would mean the deadline
# was not the bound.
GUARD_TERM_GRACE_SECONDS = 5


def credential_use_deadline_epoch_capped(
    *,
    projected_epoch: int,
    allowance_seconds: int,
    credential_expiry_epoch: int,
    margin_seconds: int,
) -> int:
    """The absolute instant after which the worker may not use the credential.

    The EARLIER of two bounds, and both are load-bearing:

    - `projected_epoch + allowance_seconds` -- the execution the workflow can
      legitimately need.
    - `credential_expiry_epoch - margin_seconds` -- the credential's own usable
      life, keeping the documented margin as headroom rather than spending it.

    Taking the minimum is what makes the delay between the final freshness
    measurement and the projection harmless. Anchoring on the projection instant
    alone would stamp a deadline later than the token can cover whenever that
    delay is non-zero, which is every real dispatch.
    """
    return min(
        projected_epoch + allowance_seconds,
        credential_expiry_epoch - margin_seconds,
    )


def guarded_acp_command(*, argv: list[str]) -> list[str]:
    """Wrap one resolved adapter argv so the deadline governs its execution.

    Applied to the ARGV rather than to an adapter identity, because the supported
    launch routes differ only in how that argv was produced: a built-in catalog
    adapter, a literal `acp.command` written by hand in a custom graph, and a
    fallback candidate all end up as an argv the engine execs. A guard attached
    per-adapter would leave the literal route unbounded -- and that is the route
    a repository is most likely to add without telling anyone.
    """
    return ["/bin/sh", GUARD_SCRIPT_PATH, "--", *argv]


def guard_script_text() -> str:
    """The POSIX-sh guard, rendered for the sandbox.

    POSIX sh rather than Python because it wraps the adapter exec itself: it has
    to be present and runnable before any interpreter this plugin controls, and
    it must add no import surface to the launch path.

    WHAT IT DOES, in the order that matters:

    1. Reads the absolute deadline. Absent or unparseable REFUSES -- a guard that
       proceeded when blinded would be decoration.
    2. `--check-start` reports whether a launch may begin, then exits. This is
       the queue/preparation-aging check a prepare step runs before any
       coding-agent node, so a credential that aged below its remaining worker
       lifetime while the run sat queued refuses at startup rather than mid-turn.
    3. A LATE START refuses. A node entered after the deadline never execs the
       agent, which is what makes inter-stage and queue delay count against the
       bound instead of being forgiven.
    4. Otherwise it execs the command in its OWN PROCESS GROUP, with STDIN
       EXPLICITLY PRESERVED, and arms a reaper. The stdin redirection is
       load-bearing rather than defensive: ACP is bidirectional stdio, and POSIX
       hands an asynchronous command /dev/null for stdin unless told otherwise.

    THE REMAINING BUDGET IS MEASURED FRACTIONALLY AND FLOORED. `date +%s` floors
    the current instant, so a guard entered part-way through a second credited
    itself the remainder of that second and killed late by exactly that
    fraction. Flooring a fractional measurement instead makes every sleep due at
    or BEFORE the epoch.
       The reaper signals the whole GROUP -- TERM at `deadline - grace`, KILL
       **at** `deadline` -- so credential-using children and a lingering
       grandchild die with it, a TERM-resistant agent stops anyway, and nothing
       is still executing after the instant the deadline names.

    The remaining time is computed from the deadline and the CURRENT clock on
    every invocation, so nothing an adapter puts in the environment can extend
    it: there is no duration input to inflate. `render_adapter` additionally
    REFUSES an adapter that declares the deadline variable itself, because the
    rendered command places env pairs ahead of the executable.
    """
    return f"""#!/bin/sh
# Generated by livespec-orchestrator-beads-fabro. Do not edit inside the sandbox.
#
# Enforces the ABSOLUTE credential-use deadline the Dispatcher projected. The
# deadline is an instant, not a duration, so a retry, a resumed launch, or a
# node entered late gets the remaining budget rather than a fresh one. Every
# process is stopped BY the deadline: TERM lands a grace period BEFORE it and
# KILL lands AT it, so the grace is spent inside the allowance.
set -u

deadline="${{{CREDENTIAL_USE_DEADLINE_ENV_VAR}:-}}"

if [ -z "$deadline" ]; then
    echo "credential-use guard refused: {CREDENTIAL_USE_DEADLINE_ENV_VAR} is not set," \\
         "so no credential-use deadline could be read. The guard fails closed:" \\
         "a coding agent is not launched against an unknown bound." >&2
    exit {GUARD_REFUSAL_EXIT_CODE}
fi

case "$deadline" in
    ''|*[!0-9]*)
        echo "credential-use guard refused: {CREDENTIAL_USE_DEADLINE_ENV_VAR} is" \\
             "'$deadline', which is not an epoch second, so the deadline could not" \\
             "be read. The guard fails closed." >&2
        exit {GUARD_REFUSAL_EXIT_CODE}
        ;;
esac

mode="run"
if [ "${{1:-}}" = "--check-start" ]; then
    mode="check"
    shift
elif [ "${{1:-}}" = "--" ]; then
    shift
fi

# FRACTIONAL now, floored CONSERVATIVELY. `date +%s` floors the current instant,
# so a guard starting at epoch+0.65 computed a whole extra second of budget and
# landed its KILL at deadline+0.65 -- systematic rounding, not scheduler jitter,
# and a deadline that is late by construction is not a deadline. The remaining
# budget is therefore measured from the fractional instant and floored, so every
# sleep is due at or BEFORE the epoch rather than after it.
now_frac="$(date +%s.%N)"
remaining="$(
    awk -v d="$deadline" -v n="$now_frac" \
        'BEGIN{{r=d-n; if (r<0) r=0; printf "%d", int(r)}}' 2>/dev/null
)"
if [ -z "$remaining" ]; then
    # No awk: fall back to integer seconds MINUS ONE, which is the conservative
    # direction. Losing up to a second of allowance is acceptable; granting one
    # past the deadline is not.
    remaining=$((deadline - $(date +%s) - 1))
    if [ "$remaining" -lt 0 ]; then
        remaining=0
    fi
fi
now="${{now_frac%%.*}}"

if [ "$remaining" -le 0 ]; then
    echo "credential-use guard refused: the projected credential-use deadline" \\
         "($deadline) passed $((now - deadline)) seconds ago, so this launch is" \\
         "not started. The deadline is absolute and is not reset by a retry, a" \\
         "resumed launch, or a later node start." >&2
    exit {GUARD_REFUSAL_EXIT_CODE}
fi

if [ "$mode" = "check" ]; then
    # THE CREDENTIAL GRADE, which is a different measurement from the deadline
    # check above and is why reaching this line is not yet an admission. The
    # deadline can be comfortably future while the credential underneath it has
    # aged below what this dispatch needs -- queueing and preparation consume
    # wall clock against BOTH, but a deadline derived from a long allowance
    # absorbs that silently. Re-measured here on the SANDBOX's clock, against the
    # requirement the host resolved, because the host's own grade was taken at an
    # earlier instant and cannot speak for this one.
    cred_expiry="${{{CREDENTIAL_EXPIRY_ENV_VAR}:-}}"
    cred_required="${{{CREDENTIAL_REQUIRED_REMAINING_ENV_VAR}:-}}"
    if [ -n "$cred_expiry" ] || [ -n "$cred_required" ]; then
        # EXACTLY ONE present is a half-wired projection, not a deadline-only
        # launch, so it fails closed rather than silently grading nothing. A
        # projection supplying NEITHER is the deadline-only shape this guard also
        # serves, and it is left to the deadline check alone.
        if [ -z "$cred_expiry" ] || [ -z "$cred_required" ]; then
            echo "credential-use guard refused: only one of" \\
                 "{CREDENTIAL_EXPIRY_ENV_VAR} and" \\
                 "{CREDENTIAL_REQUIRED_REMAINING_ENV_VAR} was projected, so the" \\
                 "credential's remaining lifetime could not be graded. The guard" \\
                 "fails closed." >&2
            exit {GUARD_REFUSAL_EXIT_CODE}
        fi
        case "$cred_expiry$cred_required" in
            ''|*[!0-9]*)
                echo "credential-use guard refused: the projected credential expiry" \\
                     "('$cred_expiry') or required remaining lifetime" \\
                     "('$cred_required') is not an epoch second, so the" \\
                     "credential's remaining lifetime could not be graded. The" \\
                     "guard fails closed." >&2
                exit {GUARD_REFUSAL_EXIT_CODE}
                ;;
        esac
        cred_remaining=$((cred_expiry - now))
        # STRICTLY GREATER, matching the admission criterion exactly. A credential
        # whose remaining lifetime EQUALS the requirement would finish its last
        # enforced second with zero margin left, which is the one state the margin
        # exists to prevent -- and a sandbox grading it more leniently than
        # admission did would admit work admission would have refused.
        if [ "$cred_remaining" -le "$cred_required" ]; then
            echo "credential-use guard refused: the projected credential has" \\
                 "$cred_remaining seconds of remaining lifetime, which does not" \\
                 "exceed the $cred_required seconds this dispatch requires. It" \\
                 "aged below that requirement while the run was queued or" \\
                 "prepared, so no coding-agent node is started against it." >&2
            exit {GUARD_REFUSAL_EXIT_CODE}
        fi
        echo "credential-use guard: the credential has $cred_remaining seconds of" \\
             "remaining lifetime, above the $cred_required required."
    fi
    echo "credential-use guard: $remaining seconds of credential-use budget remain."
    exit 0
fi

if [ "$#" -eq 0 ]; then
    echo "credential-use guard refused: no command was given to guard." >&2
    exit {GUARD_REFUSAL_EXIT_CODE}
fi

# TERM lands a grace BEFORE the deadline so a well-behaved agent can exit
# cleanly inside its allowance; KILL lands AT the deadline. A grace that ran
# past the deadline would permit credential use beyond the stated bound. Both
# are ABSOLUTE instants rather than durations, because the reaper POLLS now: a
# duration recomputed on each pass would drift, while an instant cannot.
term_epoch=$((deadline - {GUARD_TERM_GRACE_SECONDS}))
kill_epoch="$deadline"

# Field 22 of /proc/<pid>/stat -- the start time of one process INCARNATION,
# which is what turns a recyclable numeric id into an identity.
#
# `##` -- LONGEST prefix removal -- is load-bearing, and `#` here was an
# enforcement bypass. `comm` is operator-supplied text that may itself contain
# `') '`, so for a leader named `agent) worker` the line reads
# `<pid> (agent) worker) S 1 <pgid> ...` and a shortest-prefix strip stops at the
# FIRST delimiter, shifting every column behind it: the group id read 1 and the
# start time 0 instead of the real values. `group_is_ours` then saw a mismatch,
# concluded the group was not ours, disarmed the reaper, and let the agent run
# past the deadline -- measured at 4.693s beyond it. No field behind `comm` can
# contain `') '` (they are all numeric or a single character), so the LAST
# occurrence is always the comm terminator. `read` is a builtin: no fork.
incarnation() {{
    read -r _inc_line < "/proc/$1/stat" 2>/dev/null || return 1
    _inc_rest="${{_inc_line##*') '}}"
    [ "$_inc_rest" != "$_inc_line" ] || return 1
    # Deliberate word splitting: positionals are the only POSIX way to index.
    # shellcheck disable=SC2086
    set -- $_inc_rest
    [ "$#" -ge 20 ] || return 1
    shift 19
    echo "$1"
}}

# Does ANY process still carry our process-group id? Consulted only once our
# leader has exited -- the orphaned-group case, i.e. a credential-using
# grandchild that outlived the adapter.
# Field 5 is the group id, and it sits behind `comm` too, so it takes the same
# LONGEST-prefix strip for the same reason -- see `incarnation` above. A
# shortest-prefix strip here would read an unrelated column and report our group
# as empty, which disarms the reaper on exactly the orphaned-descendant case it
# exists to cover.
group_has_member() {{
    for _ghm_proc in /proc/[0-9]*; do
        read -r _ghm_line < "$_ghm_proc/stat" 2>/dev/null || continue
        _ghm_rest="${{_ghm_line##*') '}}"
        [ "$_ghm_rest" != "$_ghm_line" ] || continue
        # shellcheck disable=SC2086
        set -- $_ghm_rest
        [ "$#" -ge 3 ] || continue
        shift 2
        if [ "$1" = "$pgid" ]; then
            return 0
        fi
    done
    return 1
}}

# IS THE GROUP STILL OURS, AND STILL OCCUPIED? This is the ownership test the
# whole disarm rests on, and the reason it is not merely `kill -0 -$pgid`.
#
# If our leader is resident with the RECORDED start time, the id is
# unambiguously ours. If a process with that pid exists carrying a DIFFERENT
# start time, the id has already been recycled by a new leader and signalling it
# would reach unrelated work -- so that is a disarm, never a signal. If no such
# process exists our leader has exited, and the id cannot be claimed by anyone
# else without a process whose pid equals it appearing, which the previous branch
# detects; so surviving members carrying that pgrp are still ours.
#
# THE GUARANTEE THIS BUYS, STATED NARROWLY. The reaper signals only while
# ownership is positively established, and it re-establishes it immediately
# before each signal. The residual window is the check-then-signal race inherent
# to signalling by pid on POSIX -- there is no pidfd in sh -- NOT the multi-day
# exposure a blind sleep carried.
group_is_ours() {{
    _gio_now="$(incarnation "$pgid")" || {{
        group_has_member && return 0
        return 1
    }}
    [ "$_gio_now" = "$leader_incarnation" ] || return 1
    return 0
}}

# Seconds until an absolute epoch, floored CONSERVATIVELY, so a wait is due at
# or BEFORE the instant rather than after it.
until_epoch() {{
    awk -v d="$1" -v n="$(date +%s.%N)" \\
        'BEGIN{{r=d-n; if (r<0) r=0; printf "%d", int(r)}}' 2>/dev/null ||
        echo 0
}}

# STDIN IS PRESERVED EXPLICITLY, and this is not optional: ACP is a
# bidirectional stdio protocol, and POSIX gives an ASYNCHRONOUS command in a
# non-interactive shell its stdin from /dev/null unless the redirection is
# written out. Without the saved descriptor below, every guarded agent read EOF
# on its first protocol request and the session was dead on arrival -- a defect
# no marker-file or exit-status case can see, because the wrapped command still
# starts and still exits 0.
exec 3<&0

# Own process group, so the reaper can signal every credential-using descendant
# rather than only the adapter that happened to be the direct child.
setsid "$@" <&3 &
child=$!
pgid="$child"

exec 3<&-

# The leader's incarnation, recorded ONCE and immediately. This is the ownership
# token: every later decision to signal is checked against it, so a recycled
# pgid is distinguishable from our own group. Recorded before the reaper starts
# so the reaper can never run without it.
leader_incarnation="$(incarnation "$pgid")" || leader_incarnation=""

# The reaper's stdio is detached. It outlives this shell deliberately (see
# below), and a reaper still holding the inherited stdout would keep the pipe
# open after the agent finished -- so any consumer reading this launch to EOF
# would block until the deadline instead of seeing the agent exit.
#
# IT POLLS RATHER THAN SLEEPING, and that is the correctness fix rather than a
# refinement. A blind sleep to the deadline left a kill armed against a
# recyclable pgid for the WHOLE allowance -- roughly seven days here -- so a
# command that finished in a second could signal whatever inherited the number a
# week later. The reaper now disarms the moment the group is finished or no
# longer ours, and re-establishes ownership immediately before each signal.
(
    while :; do
        group_is_ours || exit 0
        left="$(until_epoch "$term_epoch")"
        [ "$left" -le 0 ] && break
        # Capped so a finished group is noticed promptly rather than at the
        # deadline, which is the entire point of polling.
        [ "$left" -gt 5 ] && left=5
        sleep "$left"
    done
    group_is_ours || exit 0
    kill -TERM "-$pgid" 2>/dev/null || kill -TERM "$pgid" 2>/dev/null
    while :; do
        group_is_ours || exit 0
        left="$(until_epoch "$kill_epoch")"
        [ "$left" -le 0 ] && break
        sleep 0.2
    done
    group_is_ours || exit 0
    kill -KILL "-$pgid" 2>/dev/null || kill -KILL "$pgid" 2>/dev/null
) >/dev/null 2>&1 </dev/null &

wait "$child"
status=$?

# The reaper is NOT cancelled here, and that is the point rather than an
# oversight. The adapter is frequently NOT the process holding the credential:
# it spawns a child and returns, so `wait` above completes while a
# credential-using grandchild keeps running. Cancelling the reaper on the direct
# child's exit left exactly that grandchild unbounded. Leaving it armed means
# the group is signalled at the deadline whatever the adapter did -- and because
# it is detached, it keeps enforcing even if this shell is killed.
#
# What ENDS the reaper is therefore the group emptying, not this shell exiting:
# a finished group disarms it within one poll, while a surviving descendant
# keeps it armed exactly as before.
exit "$status"
"""
