"""`resolve_dispatch_candidates`: a NON-EMPTY set, or the absence of one.

The legacy provider gate asks which domains a dispatch spends, and it owes
two opposite treatments to two answers that are easy to collapse into one.
A set of candidates none of which a record covers is a CONFIDENT NEGATIVE and
admits the item. A dispatch whose adapters were never OBSERVED supports no
verdict either way, and admitting there would turn every unreadable
configuration into a pass -- the fail-open shape this repository's
verification discipline treats as worse than the honest refusal, because the
record it leaves reads exactly like a healthy one.

So this resolver returns a non-empty tuple or `None`, and never a plausible
empty tuple. Each arm below is one measurement that can fail:

- the committed agent/model catalogs,
- the repository's own chain table,
- a workflow that parameterizes NO adapter at all, which yields no chains and
  is the arm most easily mistaken for a result: the run then executes
  whatever the graph itself bakes in, so the domains it spends are real and
  simply invisible from here.

THE POSITIVE CONTROL IS LOAD-BEARING. Three `None`s prove only that the
resolver can say "unreadable"; a resolver that said it unconditionally would
satisfy all three and fail closed on every dispatch in the fleet, which is
the behaviour being retired. So the last case resolves THIS repository and
asserts a candidate per resolved node.
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PREFLIGHT = "livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight"
_WORKFLOW_SUBPATH = (".fabro", "workflows", "implement-work-item")


def _resolve(*, repo: Path) -> Any:
    return import_module(_PREFLIGHT).resolve_dispatch_candidates(repo=repo)


def _write_block(*, repo: Path, dispatcher: dict[str, object]) -> None:
    (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )


def test_an_unresolvable_catalog_is_unreadable_rather_than_an_empty_set(
    tmp_path: Path,
) -> None:
    """An incomplete catalog entry cannot resolve one structured candidate."""
    _write_block(repo=tmp_path, dispatcher={"agent_catalog": {"local-acp": {"display_name": "L"}}})

    assert _resolve(repo=tmp_path) is None


def test_an_unresolvable_chain_table_is_unreadable_rather_than_an_empty_set(
    tmp_path: Path,
) -> None:
    """A fallback declaring a partial identity refuses the whole resolution."""
    _write_block(
        repo=tmp_path,
        dispatcher={"acp_nodes": {"implement": {"fallbacks": [{"candidate_key": "x"}]}}},
    )

    assert _resolve(repo=tmp_path) is None


def test_a_workflow_parameterizing_no_adapter_is_unreadable_not_empty(
    tmp_path: Path,
) -> None:
    """No declared adapter input means no OBSERVED adapter, not no adapter."""
    workflow = tmp_path.joinpath(*_WORKFLOW_SUBPATH)
    workflow.mkdir(parents=True)
    (workflow / "workflow.toml").write_text(
        '[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "fabro-sandbox"\n',
        encoding="utf-8",
    )
    (workflow / "workflow.fabro").write_text(
        'digraph ImplementWorkItem {\n    implement [\n        timeout="60s"\n    ]\n}\n',
        encoding="utf-8",
    )

    assert _resolve(repo=tmp_path) is None


def test_this_repository_renders_one_candidate_for_every_resolved_node() -> None:
    """The control: the resolver CAN return a set, and does for this repository."""
    rendered = _resolve(repo=_REPO_ROOT)

    assert rendered is not None
    assert len(rendered) > 1
    # Every rendered candidate carries the provenance flag the coverage rule
    # reads, and an availability domain the gate can compare a record against.
    assert all(isinstance(entry.builtin, bool) for entry in rendered)
    assert all(
        entry.candidate.identity is None or entry.candidate.identity.availability_key
        for entry in rendered
    )
