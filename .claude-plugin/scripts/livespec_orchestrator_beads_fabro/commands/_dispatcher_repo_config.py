"""What a dispatch target's committed `.livespec.jsonc` says, as ONE read.

Split out of `_dispatcher_loop_selection` by cohesion: that module's own
docstring named three concerns — dispatch-loop selection, preparation, and the
janitor ref — and this is the third. It is a peer of the other per-concern
readers in this tree rather than a helper of the selection pass, which is what
the coupling already said: FOUR modules with no part in choosing what to
dispatch (`_dispatcher_host_record_target`,
`_dispatcher_integration_validation`, `_dispatcher_loop_plan` and
`_dispatcher_reconcile_merged`) reach for `livespec_config_text`, and none of
them wants anything else the selection pass holds.

Both names stay PUBLIC and `_dispatcher_loop_selection` imports them back, so
its `__all__` and every existing call site are unchanged — only PUBLIC names
may cross a module boundary here, and `janitor_core_ref` is additionally
re-exported by `dispatcher` itself.

THE PAIR IS ONE CONCERN AND NOT TWO. `janitor_core_ref` is the committed
core-pin resolution taken OVER that text, so it is the read's one caller that
belongs with it; the resolution it delegates to
(`janitor_core_ref_from_config`) stays in `_dispatcher_plan`, where the rest of
the plan's configuration grammar lives.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    janitor_core_ref_from_config,
)

__all__: list[str] = [
    "janitor_core_ref",
    "livespec_config_text",
]


def janitor_core_ref(*, repo: Path) -> str:
    return janitor_core_ref_from_config(config_text=livespec_config_text(repo=repo))


def livespec_config_text(*, repo: Path) -> str:
    """The target repository's committed `.livespec.jsonc`; `{}` when it has none.

    A repository with no config declares nothing, which is the same input as an
    empty object -- the resolver, not this reader, decides which fields that
    leaves unresolved.

    PUBLIC because plan build reads it too: the WHOLE integration contract now
    resolves from this one text, so the reader that answers it crosses a module
    boundary rather than staying private to the core-pin wrapper above.
    """
    config = repo / ".livespec.jsonc"
    if not config.exists():
        return "{}"
    return config.read_text(encoding="utf-8")
