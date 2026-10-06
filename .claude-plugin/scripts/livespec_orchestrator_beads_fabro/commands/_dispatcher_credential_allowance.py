"""The engine-cost arithmetic behind one workflow's execution allowance.

Split from `_dispatcher_credential_requirement` by cohesion: that module
RESOLVES which workflow a dispatch selected and reads its graph, while this one
answers the narrower arithmetic question of what one node attempt costs OUTSIDE
the node timeout a derivation multiplies, and renders the resulting figure with
the configuration behind it.

WHAT GOES INTO THE ALLOWANCE. `_dispatcher_execution_budget` composes the
enforced per-operation bounds and takes the per-attempt costs as a
caller-supplied input. This module computes that input from engine behaviour
measured on the pinned revision rather than from a round number:

- The CHECKPOINT. `fabro-sandbox/src/sandbox_git.rs` spends `commit_timeout_ms`
  independently on `git add`, on `git diff --cached` and on `git commit`, then
  another ten seconds resolving the head SHA. So the ceiling is three times the
  configured budget plus ten, not the budget itself -- which is why that value
  is READ from the run config rather than assumed: a repository that raises
  `commit_timeout` to survive its own hooks raises this cost threefold, and a
  hand-written constant here would silently under-count exactly the
  repositories that needed it most.
- The CHANGED-FILE SCANS. `acp.rs` runs one on each side of `run_acp_turn`
  (thirty seconds apiece in `changed_files.rs`) plus an optional five-second
  last-file lookup.
- The TURN-ENTRY MINT, thirty seconds, bounded separately from the node timeout.
- The RETRY BACKOFF, whose capped sixty-second delay is multiplied by the
  `[0.5, 1.5)` jitter in `fabro-util/src/backoff.rs`, so ninety is its ceiling.

These are billed per ATTEMPT, which over-counts the checkpoint -- checkpoints
happen between stages, so a node's retries inside one visit share one. That
direction is correct for a credential floor and wrong for a forecast; do not
reuse this figure as one.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from livespec_orchestrator_beads_fabro.commands._dispatcher_projection import (
    CODEX_FRESHNESS_MARGIN_SECONDS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_toml_read import (
    TomlDocumentUnparseable,
    TomlStringUnreadable,
    toml_section_string_declaration,
)

__all__: list[str] = [
    "commit_timeout_seconds",
    "per_attempt_overhead_seconds",
    "requirement_detail",
]

# Per-attempt engine costs that sit OUTSIDE the node timeout a derivation
# multiplies, each read from the pinned engine and named so a reader can check
# one without re-deriving the sum. The module docstring carries the source for
# each; these are the numbers it cites.
_CHECKPOINT_GIT_CALLS = 3
_CHECKPOINT_HEAD_SHA_SECONDS = 10
_CHANGED_FILE_SCAN_SECONDS = 65
_TURN_ENTRY_MINT_SECONDS = 30
_RETRY_BACKOFF_CEILING_SECONDS = 90

# Fabro's own checkpoint budget when a run config declares none. This is the
# ENGINE's default rather than a figure invented here -- the committed run
# config's own comment records it as the stock budget that destroyed completed
# work on gate-heavy repositories, which is why this repository raises it.
_STOCK_COMMIT_TIMEOUT_SECONDS = 30

_CHECKPOINT_SECTION = "run.checkpoint"
_COMMIT_TIMEOUT_KEY = "commit_timeout"
_DURATION_RE = re.compile(r"^(?P<value>\d+)(?P<unit>[smh]?)$")
_UNIT_SECONDS = {"": 1, "s": 1, "m": 60, "h": 3600}


def commit_timeout_seconds(*, committed_text: str) -> int | str:
    """The run config's checkpoint commit budget in seconds, or a refusal.

    An ABSENT key is the engine's own stock thirty seconds rather than a
    refusal: a run config declaring no `[run.checkpoint]` is a complete,
    ordinary config, and the engine's documented default is a measured value
    rather than one invented here. A key that IS declared but unparseable
    refuses, because then the configuration states a budget this derivation
    cannot account for.
    """
    declaration = toml_section_string_declaration(
        text=committed_text, section=_CHECKPOINT_SECTION, key=_COMMIT_TIMEOUT_KEY
    )
    if isinstance(declaration, TomlDocumentUnparseable):
        # NOT an absence. A run config that is not TOML tells us nothing about
        # what it declares, including whether it declares a checkpoint budget,
        # so contributing stock defaults from it would be sizing a credential
        # floor against a file the engine itself would reject.
        return (
            f"credential lifetime requirement unresolved: the selected workflow's "
            f"run config is not valid TOML ({declaration.detail}), so neither its "
            f"checkpoint budget nor anything else it declares could be read."
        )
    if isinstance(declaration, TomlStringUnreadable):
        # DECLARED but not a string, which is the case the earlier regex readers
        # could not express and therefore got wrong in the expensive direction:
        # they returned the same `None` as an absent key, so a configured budget
        # they could not read was silently replaced by the engine's stock thirty
        # seconds, and since the checkpoint enters the allowance multiplied by
        # three the floor came out well BELOW what the configuration asks for.
        # Nothing in the result said so -- the smaller figure is just as
        # well-formed a number. Refusing names what could not be read instead.
        return (
            f"credential lifetime requirement unresolved: the selected workflow "
            f"declares [{_CHECKPOINT_SECTION}] {_COMMIT_TIMEOUT_KEY} = "
            f"{declaration.raw}, which is not a duration string, so the "
            f"checkpoint time a run can spend between stages cannot be accounted "
            f"for. The engine's stock budget is NOT used in its place: that would "
            f"silently grade the credential against less time than the "
            f"configuration asks for."
        )
    if declaration is None:
        return _STOCK_COMMIT_TIMEOUT_SECONDS
    raw = declaration
    match = _DURATION_RE.match(raw.strip())
    if match is None:
        return (
            f"credential lifetime requirement unresolved: the selected workflow "
            f"declares [{_CHECKPOINT_SECTION}] {_COMMIT_TIMEOUT_KEY} = {raw!r}, which "
            f"is not a whole number of seconds, minutes or hours, so the checkpoint "
            f"time a run can spend between stages cannot be accounted for."
        )
    return int(match.group("value")) * _UNIT_SECONDS[match.group("unit")]


def per_attempt_overhead_seconds(*, commit_timeout_seconds: int) -> int:
    """Engine time one node attempt can spend OUTSIDE its own node timeout."""
    return (
        commit_timeout_seconds * _CHECKPOINT_GIT_CALLS
        + _CHECKPOINT_HEAD_SHA_SECONDS
        + _CHANGED_FILE_SCAN_SECONDS
        + _TURN_ENTRY_MINT_SECONDS
        + _RETRY_BACKOFF_CEILING_SECONDS
    )


def requirement_detail(
    *,
    workflow_name: str,
    allowance_seconds: int,
    overhead_seconds: int,
    inputs: Mapping[str, int],
) -> str:
    """The figure with the configuration behind it, including which inputs it read.

    The inputs are NAMED rather than summarized because they are the one part of
    this figure a per-item label can move: an operator comparing a status reading
    against a dispatch refusal needs to see whether the two read the same cap,
    and a bare number cannot tell them.
    """
    rendered = ", ".join(f"{name}={value}" for name, value in sorted(inputs.items())) or "none"
    return (
        f"workflow {workflow_name!r} resolves an execution ALLOWANCE of "
        f"{allowance_seconds} seconds — the sum over the visit caps, retry budgets "
        f"and resolved node timeouts the engine enforces for this dispatch, with "
        f"graph inputs {rendered}, plus {overhead_seconds} seconds per attempt of "
        f"checkpoint, changed-file-scan, turn-entry-mint and retry-backoff time the "
        f"engine spends outside a node timeout. That allowance is NOT the graph's "
        f"maximum wall clock — retry_target jumps and inter-stage work sit outside "
        f"every bound it sums — so it is made a maximum CREDENTIAL-USE duration by "
        f"enforcement instead: the freshness gate requires "
        f"{allowance_seconds + CODEX_FRESHNESS_MARGIN_SECONDS} seconds of usable "
        f"lifetime (that allowance plus the {CODEX_FRESHNESS_MARGIN_SECONDS}-second "
        f"documented margin), and the worker refuses to launch a coding agent past "
        f"that allowance measured from the instant the credential was projected"
    )
