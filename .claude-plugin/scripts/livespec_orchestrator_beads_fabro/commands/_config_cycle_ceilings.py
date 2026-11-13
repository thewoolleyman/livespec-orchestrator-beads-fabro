"""The config-reading seam for the two adopted per-cycle runtime ceilings.

Split out of `_config` for the same reason `_node_timeouts` and `_config_acp`
are: the POLICY — what a ceiling means, what a value must satisfy, and what a
breach is — lives in `_dispatcher_cycle_ceilings`, which is pure and directly
testable, while this module is the one place that goes to the repository's
committed `.livespec.jsonc` to find out which ceilings it has adopted.

It is also its OWN module rather than another `resolve_*` seam inside `_config`
because that file already sits in the per-file LLOC soft band, and the reason
`dispatcher_block` was made public is exactly this: a policy module that owns
its resolver reads the block from outside rather than growing `_config` by one
seam per key.

THE READ IS DELIBERATELY NOT FAIL-SOFT. `dispatcher_block` RAISES when
`.livespec.jsonc` cannot be read, and that exception is left alone here: an
unreadable configuration file is not "this repository adopted no ceiling", and
collapsing the two would tell an operator their ceilings are unadopted when what
actually happened is a stray comma. The caller — the pre-dispatch wall — already
maps that failure to its own refusal, so the dispatch still refuses before any
claim rather than proceeding on a guess.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_ceilings import (
    AdoptedCycleCeilings,
    adopted_cycle_ceilings,
)

__all__: list[str] = [
    "resolve_adopted_cycle_ceilings",
]


def resolve_adopted_cycle_ceilings(*, cwd: Path) -> AdoptedCycleCeilings | str:
    """Resolve this repository's adopted per-cycle runtime ceilings, or refuse.

    Returns the resolved pair for a repository whose declaration is valid
    (including one that adopts neither ceiling), or the refusal string naming
    the offending setting and value.
    """
    return adopted_cycle_ceilings(block=dispatcher_block(cwd=cwd))
