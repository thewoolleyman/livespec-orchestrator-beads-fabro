"""Projecting credential-use enforcement and its guard into a sandbox.

`_dispatcher_credential_use_guard` owns the ENFORCEMENT -- the POSIX-sh guard, the
reaper, the deadline arithmetic and the startup grade. This module owns the
TRANSPORT: the two `[[run.prepare.steps]]` blocks and the
`[environments.<id>.env]` lines that carry that guard and its three inputs into a
run. The split is the usual pure-from-impure one turned sideways -- the guard is a
tested artifact that knows nothing about run configuration, and this module knows
nothing about process groups.

TWO DIFFERENT QUANTITIES REACH THE SANDBOX, and they answer different questions.
The ABSOLUTE DEADLINE bounds how long execution may CONTINUE. The observed
CREDENTIAL EXPIRY and the resolved REQUIREMENT let the sandbox decide, on its OWN
clock, whether execution may BEGIN at all: admission graded the credential on the
host at an earlier instant, and queueing or preparation can age it below the
requirement in between. Projecting only the deadline would carry a bound on
continuation while leaving that aging unobserved, which is the defect this module
was first written with.

THE DISCRIMINATOR IS PROTECTION, NOT THE PRESENCE OF A DEADLINE, and it cuts both
ways, which is why both arms are spelled out here rather than left to a caller:

- A dispatch that projects a Codex credential IS protected. The guard is
  installed, all three inputs ride the env table, and the startup check refuses
  before any coding-agent node runs.
- A dispatch that projects NO Codex credential is NOT protected, and must keep
  running normally. There is no credential whose use needs bounding, so
  installing a guard would either write an empty script and abort the sandbox at
  prepare time, or wrap an ordinary adapter into a launch that can only refuse.
  Both break working execution and neither protects anything.

The third case -- a credential projected with NO enforcement -- is broken
protection rather than a legitimate configuration, and it is refused by the OVERLAY
RENDERER rather than here: this module renders text, so the only refusal available
to it would be an empty block, which is indistinguishable from the unprotected
shape above. The renderer declines to produce an overlay at all.

WHY THE THREE INPUTS ARE ONE VALUE. A half-wired projection -- a deadline with no
expiry, so the startup grade silently degrades to a deadline check -- is exactly
the shape this module shipped with, and a runtime check for it would be one more
thing to get right. `CredentialUseProjection` makes it UNREPRESENTABLE instead:
there is no way to construct the partial state, so nothing downstream needs to
detect it.

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
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
    CREDENTIAL_EXPIRY_ENV_VAR,
    CREDENTIAL_REQUIRED_REMAINING_ENV_VAR,
    CREDENTIAL_USE_DEADLINE_ENV_VAR,
    GUARD_SCRIPT_PATH,
    guard_script_text,
)

__all__: list[str] = [
    "CredentialUseProjection",
    "credential_use_env_lines",
    "credential_use_guard_prepare_steps_block",
]

# The transport for the guard's own text. Private because it is an implementation
# detail of the two functions below -- the producer and the consumer of this name
# are both in this file, which is what keeps a disagreement about it impossible.
_GUARD_SCRIPT_ENV_VAR = "LIVESPEC_CREDENTIAL_USE_GUARD_SCRIPT"


@dataclass(frozen=True, kw_only=True)
class CredentialUseProjection:
    """Everything a protected sandbox needs in order to enforce, as ONE value.

    The three fields are inseparable BY CONSTRUCTION, and that is the point. A
    deadline without `credential_expiry_epoch` would leave the startup grade
    unable to measure the credential and silently degrade to a deadline check --
    the exact defect this type retires -- so the partial state is not
    representable rather than detected after the fact.

    - `deadline_epoch` -- the absolute instant after which the worker may not use
      the credential. Already capped against the credential's own expiry by
      `credential_use_deadline_epoch_capped`; an epoch rather than a duration, so
      a retried or resumed launch inherits what is left of it.
    - `credential_expiry_epoch` -- the expiry the host OBSERVED in the credential
      it projected, which is what lets the sandbox re-measure remaining lifetime
      against its own clock.
    - `required_remaining_seconds` -- the lifetime this dispatch requires, as the
      host RESOLVED it (the execution allowance plus the documented margin).
      Carried rather than recomputed in the sandbox, because the sandbox cannot
      see the workflow the host selected.
    """

    deadline_epoch: int
    credential_expiry_epoch: int
    required_remaining_seconds: int


def credential_use_env_lines(*, projection: CredentialUseProjection | None) -> str:
    """Render the enforcement inputs as `[environments.<id>.env]` lines.

    Empty string when `projection` is None -- the unprotected shape, which must
    carry none of these names. Every value is `json.dumps`-ed so the multi-line
    guard single-line-encodes with `\\n` escapes (valid TOML), exactly as the Codex
    auth snapshot beside it does.

    The integers are rendered as STRINGS because a TOML env table carries strings
    and the guard reads them with `${...}`.
    """
    if projection is None:
        return ""
    return (
        f"{CREDENTIAL_USE_DEADLINE_ENV_VAR} = {json.dumps(str(projection.deadline_epoch))}\n"
        f"{CREDENTIAL_EXPIRY_ENV_VAR} = "
        f"{json.dumps(str(projection.credential_expiry_epoch))}\n"
        f"{CREDENTIAL_REQUIRED_REMAINING_ENV_VAR} = "
        f"{json.dumps(str(projection.required_remaining_seconds))}\n"
        f"{_GUARD_SCRIPT_ENV_VAR} = {json.dumps(guard_script_text())}\n"
    )


def credential_use_guard_prepare_steps_block(*, projection: CredentialUseProjection | None) -> str:
    """Render the install + startup-check `[[run.prepare.steps]]` blocks.

    Empty string when `projection` is None. Two steps, in this order:

    1. INSTALL -- write the guard from its env value, make it executable, and read
       it back with `test -s` so an empty projection aborts the sandbox here
       rather than surfacing as an unexplained node refusal later.
    2. CHECK -- run the guard's `--check-start`, which grades BOTH the absolute
       deadline and the credential's remaining lifetime against the sandbox's own
       clock, and exits non-zero on either shortfall. A prepare step exiting
       non-zero means no coding-agent node ever runs, which is the whole point:
       the refusal lands BEFORE any credential use, not mid-turn.
    """
    if projection is None:
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
        "# --- preparation consumed the budget or aged the credential below the",
        "# --- lifetime this dispatch requires ---",
        "[[run.prepare.steps]]",
        f"script = {json.dumps(install)}",
        "",
        "[[run.prepare.steps]]",
        f"script = {json.dumps(check)}",
    ]
    return "\n".join(lines) + "\n"
