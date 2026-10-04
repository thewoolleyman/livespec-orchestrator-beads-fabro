"""The sandbox capability set, and the committed mirror of it a repository may carry.

A *sandbox capability* is a named surface the sandbox can exercise for proof:
the baseline `terminal` (a shell plus the governed repository's own toolchain)
plus each additional surface the image carries, such as `headless_browser`,
`tmux` or `herdr`. `SPECIFICATION/contracts.md` section "Definition-of-Done
and Proof-of-Done stages", sub-clause "Sandbox capabilities", makes the image
the AUTHORITY: it publishes its set as one lowercase snake_case name per line
at `PUBLISHED_CAPABILITIES_PATH`, and the `dod_gate` node reads it there.

WHAT THIS MODULE OWNS, AND WHAT IT DOES NOT. The published file lives inside
the sandbox, is read by the gate node from inside the sandbox, and is
therefore not this module's business. What a HOST-side surface can see is the
committed MIRROR — `dispatcher.sandbox_capabilities` in `.livespec.jsonc` —
which exists so the gate has a fallback when the image publishes nothing, and
so a filing display can show the set without a sandbox. This module resolves
and validates that mirror, and single-sources the two literals the gate prompt
also names so the prompt and the code cannot drift apart.

WHY A MALFORMED MIRROR IS A REFUSAL RATHER THAN A BEST-EFFORT READ. The gate's
missing-capability finding is computed FROM this list, by comparing the
capability an assertion needs against the names it holds. A hyphenated,
capitalised, or empty name therefore produces no error anywhere: it simply
fails to match, and the gate reports a finding against an item whose
declaration was correct the whole time, naming a capability the image actually
has. That is a wrong answer delivered with full confidence, so the typo is
refused at dispatch — the same reasoning `_node_timeouts` records for a
non-positive timeout, and the same place: before any Fabro run exists.

An ABSENT key is not a typo and never refuses. It is an ANSWER — this
repository declares no mirror — and the contract withholds only the
missing-capability finding when the set is unknown, so an absent mirror must
leave every other duty of the gate intact.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block

__all__: list[str] = [
    "BASELINE_CAPABILITY",
    "PUBLISHED_CAPABILITIES_PATH",
    "SANDBOX_CAPABILITIES_KEY",
    "UNPUBLISHED_REPORT",
    "mirrored_sandbox_capabilities",
    "sandbox_capabilities_refusal",
]

SANDBOX_CAPABILITIES_KEY = "sandbox_capabilities"

# The file the sandbox image publishes its capability set as, read by the
# `dod_gate` node from INSIDE the sandbox. It is named here, rather than only
# in the prompt, so the prompt's binding test can compare the prose against
# one declaration instead of a second hand-typed copy of the path.
PUBLISHED_CAPABILITIES_PATH = "/etc/livespec/sandbox-capabilities"

# The capability every image has whether it publishes a file or not.
BASELINE_CAPABILITY = "terminal"

# What the gate reports when NEITHER the published file nor the committed
# mirror answers. The set is then unknown rather than empty, which is a
# material difference: an unknown set withholds the missing-capability
# finding, while an empty one would manufacture a finding for every assertion.
UNPUBLISHED_REPORT = "sandbox-capabilities: unpublished"

# Lowercase snake_case as the contract spells it: a lowercase letter first,
# then lowercase letters and digits, with single underscores between
# non-empty runs. `x11_display` conforms; `3d_printer`, `headless-browser`,
# `HeadlessBrowser` and the empty string do not.
_CAPABILITY_NAME = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")

_CONFIGURED_KEY = f"dispatcher.{SANDBOX_CAPABILITIES_KEY}"


def mirrored_sandbox_capabilities(*, block: dict[str, Any]) -> tuple[str, ...] | str:
    """The committed capability mirror in declaration order, or an actionable refusal.

    Returns the names as declared when every entry is a lowercase snake_case
    string, `()` when the key is absent, or a refusal message NAMING the key
    and the offending value. Declaration ORDER is preserved rather than sorted:
    the mirror is what an operator wrote, and a surface that displays it should
    show it back unchanged.
    """
    raw = block.get(SANDBOX_CAPABILITIES_KEY)
    if raw is None:
        return ()
    if not isinstance(raw, list):
        return (
            f"{_CONFIGURED_KEY} must be an array of lowercase snake_case "
            f"capability names; got {raw!r}"
        )
    names: list[str] = []
    for entry in cast("list[Any]", raw):
        if not isinstance(entry, str):
            return (
                f"{_CONFIGURED_KEY} entries must be lowercase snake_case "
                f"capability names; got {entry!r}"
            )
        if _CAPABILITY_NAME.match(entry) is None:
            return (
                f"{_CONFIGURED_KEY} entry {entry!r} is not a lowercase "
                f"snake_case capability name"
            )
        names.append(entry)
    return tuple(names)


def sandbox_capabilities_refusal(*, repo: Path) -> str | None:
    """The pre-dispatch refusal for a malformed mirror, or None to proceed.

    Shaped as the dispatch preamble's other refusals are — a message to report
    and short-circuit on, or `None` — so the capability mirror is validated in
    the same pass that validates the engine binary and the integration
    declaration, and by the same convention.
    """
    resolved = mirrored_sandbox_capabilities(block=dispatcher_block(cwd=repo))
    return resolved if isinstance(resolved, str) else None
