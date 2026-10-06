"""Projecting the absolute credential-use deadline and its guard into a sandbox.

`_dispatcher_credential_use_guard` owns the ENFORCEMENT -- the POSIX-sh guard, the
reaper, and the arithmetic that caps a deadline against the credential's own
expiry. This module owns the TRANSPORT: the two `[[run.prepare.steps]]` blocks and
the `[environments.<id>.env]` lines that carry that guard and that deadline into a
run. The split is the usual pure-from-impure one turned sideways -- the guard is a
tested artifact that knows nothing about run configuration, and this module knows
nothing about process groups.

THE DISCRIMINATOR IS PROTECTION, NOT THE PRESENCE OF A DEADLINE, and it cuts both
ways, which is why both arms are spelled out here rather than left to a caller:

- A dispatch that projects a Codex credential IS protected. The guard is
  installed, the deadline rides the env table, and the startup check refuses
  before any coding-agent node runs.
- A dispatch that projects NO Codex credential is NOT protected, and must keep
  running normally. There is no credential whose use needs bounding, so
  installing a guard would either write an empty script and abort the sandbox at
  prepare time, or wrap an ordinary adapter into a launch that can only refuse.
  Both break working execution and neither protects anything.

The third case -- a credential projected with NO deadline stamped -- is broken
protection rather than a legitimate configuration, and it is refused by the
OVERLAY RENDERER rather than here: this module renders text, so the only refusal
available to it would be an empty block, which is indistinguishable from the
unprotected shape above. The renderer declines to produce an overlay at all.

WHY THE SCRIPT TRAVELS AS AN ENV VALUE. The guard has to exist inside the sandbox
before any node runs, and the engine offers no file-projection primitive; the same
constraint already makes `codex_auth.json` ride the env table. So the generated
install step `printf`s the variable and then READS IT BACK with `test -s`. That
read-back is load-bearing rather than belt-and-braces: a projection that silently
produced an empty guard would otherwise surface as a coding-agent node refusing
several minutes later, with a message about a missing deadline rather than about
the install that never happened.

WHY THE STARTUP CHECK IS RENDERED LAST. The caller appends this block after every
other prepare step, so the check observes the time preparation itself consumed --
sibling clones, credential projection, the plugin-cache gate. A check placed
earlier would forgive exactly the aging it exists to catch, and queue delay plus
preparation is precisely how a credential that was sufficient at admission becomes
insufficient by the time an agent would use it.
"""

from __future__ import annotations

import json

from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
    CREDENTIAL_USE_DEADLINE_ENV_VAR,
    GUARD_SCRIPT_PATH,
    guard_script_text,
)

__all__: list[str] = [
    "credential_use_env_lines",
    "credential_use_guard_prepare_steps_block",
]

# The transport for the guard's own text. Private because it is an implementation
# detail of the two functions below -- the producer and the consumer of this name
# are both in this file, which is what keeps a disagreement about it impossible.
_GUARD_SCRIPT_ENV_VAR = "LIVESPEC_CREDENTIAL_USE_GUARD_SCRIPT"


def credential_use_env_lines(*, deadline_epoch: int | None) -> str:
    """Render the deadline and the guard script as `[environments.<id>.env]` lines.

    Empty string when `deadline_epoch` is None -- the unprotected shape, which
    must carry neither name. Both values are `json.dumps`-ed so the multi-line
    guard single-line-encodes with `\\n` escapes (valid TOML), exactly as the
    Codex auth snapshot beside it does.

    The deadline is rendered as a STRING because a TOML env table carries strings
    and the guard reads it with `${...}`; it is an epoch INSTANT rather than a
    duration, which is what makes a retry, a resumed launch, or a late node start
    inherit the remaining budget instead of a fresh one.
    """
    if deadline_epoch is None:
        return ""
    return (
        f"{CREDENTIAL_USE_DEADLINE_ENV_VAR} = {json.dumps(str(deadline_epoch))}\n"
        f"{_GUARD_SCRIPT_ENV_VAR} = {json.dumps(guard_script_text())}\n"
    )


def credential_use_guard_prepare_steps_block(*, deadline_epoch: int | None) -> str:
    """Render the install + startup-check `[[run.prepare.steps]]` blocks.

    Empty string when `deadline_epoch` is None. Two steps, in this order:

    1. INSTALL -- write the guard from its env value, make it executable, and read
       it back with `test -s` so an empty projection aborts the sandbox here
       rather than surfacing as an unexplained node refusal later.
    2. CHECK -- run the guard's `--check-start`, which exits non-zero when the
       deadline has already passed. A prepare step exiting non-zero means no
       coding-agent node ever runs, which is the whole point: the refusal lands
       BEFORE any credential use, not mid-turn.

    The check deliberately does NOT re-apply the admission requirement. Remaining
    runway below that requirement while the deadline is still future is the normal
    consequence of queueing and preparation, and refusing it would turn the
    enforcement into a second, stricter admission gate applied at the one place
    where no renewal is possible -- no dispatch would survive a queue wait.
    """
    if deadline_epoch is None:
        return ""
    install = (
        f'mkdir -p "$(dirname {GUARD_SCRIPT_PATH})"'
        f' && printf %s "${_GUARD_SCRIPT_ENV_VAR}" > {GUARD_SCRIPT_PATH}'
        f" && chmod 700 {GUARD_SCRIPT_PATH}"
        f" && test -s {GUARD_SCRIPT_PATH}"
    )
    check = f"/bin/sh {GUARD_SCRIPT_PATH} --check-start"
    lines = [
        "",
        "# --- Dispatcher-materialized credential-use enforcement: install the",
        "# --- absolute-deadline guard, then refuse at startup if queueing or",
        "# --- preparation already consumed the projected budget ---",
        "[[run.prepare.steps]]",
        f"script = {json.dumps(install)}",
        "",
        "[[run.prepare.steps]]",
        f"script = {json.dumps(check)}",
    ]
    return "\n".join(lines) + "\n"
