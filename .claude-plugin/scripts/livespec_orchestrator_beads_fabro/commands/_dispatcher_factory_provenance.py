"""The factory-provenance marker every Dispatcher-launched sandbox declares.

WHY THE MARKER EXISTS (work-item bd-ib-dosmpm, plan
`mechanically-enforce-factory-usage`). A commit made inside a Fabro sandbox
and a commit hand-cranked in a host worktree are indistinguishable after the
fact: both carry the same authorship, the same trailers and the same hooks.
The dev-tooling half of this gate refuses staged product `.py` outside the
factory, so it needs something the sandbox DECLARES about itself and a host
worktree does not. This is that declaration — one `git config` key, written
into the sandbox clone's LOCAL config by a prepare step, exactly as the
sandbox-exemption marker beside it already is. Local config only: it never
leaves the ephemeral sandbox, because pushes carry refs and not config.

WHY THE OVERLAY AND NOT `workflow.toml`. The committed run config is FORKED
per repository (the console fork, the groom variant, the homelab/openbrain
adopter forks), so a prepare step written into one fork covers one consumer
and silently omits the rest — and an omission here reads downstream as "this
commit was hand-cranked", which is the one verdict the gate must never reach
by accident. The Dispatcher's overlay renderer appends its blocks to
whichever config a dispatch selected, so injecting here covers every
consumer by construction.

WHY THE PRE-LAUNCH DISPATCH ID AND NOT THE FABRO RUN ID. The Fabro run id
only exists once `fabro run` has launched (it is parsed back out of that
command's output by `_fabro_port.fabro_run_id_from_output`), and the overlay
this step rides in is an INPUT to that launch. A prepare step therefore
cannot see it. The Dispatcher's own `dispatch_id` — the uuid4 minted before
launch in `_dispatcher_loop`, already carried into the OTel correlation
overlays — is available at render time and identifies the same dispatch, so
the marker declares that instead.

THE KEY HAS A SECOND READER, AND IT IS NOT A PYTHON ONE (bd-ib-zddbkq). The
reserved workflow's `needs_human` terminal reads this key out of the sandbox
clone's local config to NAME the run-scoped ref it preserves an unfinished tree
on, because neither engine supplies a usable run id on that node's stdin: the
Petri-era engine sets `context.internal.run_id` to the literal `petri`, which
collapsed every needs-human outcome onto one shared ref, and the pinned engine
supplies no stdin to a script node at all. This value is the only identifier
reaching that node that is unique to the run on BOTH engines, which is why the
terminal prefers it over the engine's own context value rather than the other
way round.

So a RENAME here is not local. The terminal spells the key inside a shell string
no type checker and no import graph can see, and losing it would drop that node
onto its stdin fallback — the shared placeholder on one engine, nothing at all
on the other. `tests/integration/test_needs_human_preservation_ref_identity.py`
binds the two spellings by asserting the terminal's own script reads the key this
constant declares; keep them in lockstep, exactly as the `LIVESPEC_NEEDS_HUMAN`
sentinel is kept in lockstep with `_dispatcher_plan.NEEDS_HUMAN_MARKER`.
"""

from __future__ import annotations

import json
import shlex

__all__: list[str] = [
    "FACTORY_RUN_ID_MARKER",
    "factory_run_id_prepare_steps_block",
]

# The git-config key the sandbox declares its factory provenance under. Named
# for the RUN rather than for the dispatcher because its reader is the
# dev-tooling commit gate, which knows only that some factory run provisioned
# this clone. The value is this repository's `dispatch_id`.
FACTORY_RUN_ID_MARKER = "livespec.factoryRunId"


def factory_run_id_prepare_steps_block(*, dispatch_id: str | None) -> str:
    """Render the factory-provenance `[[run.prepare.steps]]` block.

    Empty string when `dispatch_id` is None — a direct caller that minted no
    dispatch id declares no provenance rather than declaring an empty one,
    mirroring the sibling projections' absent-input arms. Every production
    dispatch carries one: `materialize_overlay` forwards the id the
    Dispatcher minted before launch.

    The id is `shlex.quote`-ed even though it is a uuid4 hex by construction:
    the step body is a shell command, and a value that reached it unquoted
    would be a command-injection surface the moment a caller passed something
    else. The whole script is then `json.dumps`-ed to TOML-quote it, matching
    every sibling block in the overlay.
    """
    if dispatch_id is None:
        return ""
    script = f"git config {FACTORY_RUN_ID_MARKER} {shlex.quote(dispatch_id)}"
    lines = [
        "",
        "# --- Dispatcher-materialized factory-provenance marker: declare, in the",
        "# --- sandbox clone's local config, the dispatch that provisioned it, so",
        "# --- the dev-tooling commit gate can tell a factory commit from a",
        "# --- hand-cranked one (bd-ib-dosmpm) ---",
        "[[run.prepare.steps]]",
        f"script = {json.dumps(script)}",
    ]
    return "\n".join(lines) + "\n"
