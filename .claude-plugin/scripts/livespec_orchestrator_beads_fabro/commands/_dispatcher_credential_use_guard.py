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
"""

from __future__ import annotations

__all__: list[str] = [
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
    echo "credential-use guard: $remaining seconds of credential-use budget remain."
    exit 0
fi

if [ "$#" -eq 0 ]; then
    echo "credential-use guard refused: no command was given to guard." >&2
    exit {GUARD_REFUSAL_EXIT_CODE}
fi

# TERM lands a grace BEFORE the deadline so a well-behaved agent can exit
# cleanly inside its allowance; KILL lands AT the deadline. A grace that ran
# past the deadline would permit credential use beyond the stated bound.
term_wait=$((remaining - {GUARD_TERM_GRACE_SECONDS}))
if [ "$term_wait" -lt 0 ]; then
    term_wait=0
fi
kill_wait=$((remaining - term_wait))

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

exec 3<&-

# The reaper's stdio is detached. It outlives this shell deliberately (see
# below), and a reaper still holding the inherited stdout would keep the pipe
# open after the agent finished -- so any consumer reading this launch to EOF
# would block until the deadline instead of seeing the agent exit.
(
    sleep "$term_wait"
    kill -TERM "-$child" 2>/dev/null || kill -TERM "$child" 2>/dev/null
    sleep "$kill_wait"
    kill -KILL "-$child" 2>/dev/null || kill -KILL "$child" 2>/dev/null
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
exit "$status"
"""
