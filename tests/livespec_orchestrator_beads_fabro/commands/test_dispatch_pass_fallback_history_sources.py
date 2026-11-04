"""Where the dispatch pass reads fallback history from, after v127.

Binds the third Definition-of-Done assertion of work-item `bd-ib-qm6r1` against
`SPECIFICATION/contracts.md` — cited at FILE level, because a heading-level
citation rots the moment the heading is reworded. That revision replaced the
engine-event projection with "the per-node selection record ... and the
`provider-limit-release` record are the authoritative fallback history", and
said in as many words that the Dispatcher "MUST NOT depend on any engine
fallback or failover event".

THE REMOVAL IS ASSERTED AS AN IMPORT-GRAPH PROPERTY, not as a per-call-site
absence, and the SCOPE is stated: every `.py` under the package's `commands/`
tree. A call site removed while a sibling still imports the module leaves the
projection one line from returning, and a per-file assertion cannot see that —
this is the shape an absence assertion has to take to be worth anything.

THE POSITIVE CONTROL IS THE OTHER HALF OF THE SAME CLAUSE. "Removed" is
satisfied just as well by a build that removed the two authoritative sources
too, so the two surviving record stages are asserted PRESENT and still written
by the pass. Without that pairing this module passes against a Dispatcher with
no fallback history at all.

THE CONSTANT THE PROJECTION OWNED IS ASSERTED TO SURVIVE. `_dispatcher_cost_
chain` bounds its own events read with the same figure, so deleting the module
that declared it would take the cost path's bound with it — a removal whose
only symptom is an unbounded subprocess on a slow factory.
"""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

# The projection's own modules: the port call and its terminal hook, named by
# the Definition of Done, plus the two the clause's removal strands — the
# event-to-ledger projection they both route through, and the reconciliation
# replay whose entire input was the projection-failure facts.
_RETIRED_MODULES: tuple[str, ...] = (
    "_acp_projection_run",
    "_acp_projection_terminal",
    "_acp_event_projection",
    "_dispatcher_reconcile_acp_projection",
)


def test_every_retired_projection_module_file_is_gone() -> None:
    """No call site can be re-added for a module that is not there."""
    assert [name for name in _RETIRED_MODULES if (_COMMANDS / f"{name}.py").is_file()] == []


def test_every_retired_projection_module_is_unimportable() -> None:
    """The files' absence is not a stale bytecode cache still answering."""
    resolvable = [
        name
        for name in _RETIRED_MODULES
        if importlib.util.find_spec(f"{_PACKAGE}.{name}") is not None
    ]
    assert resolvable == []


def test_no_module_in_the_commands_tree_imports_a_retired_projection_module() -> None:
    """Scope: every `.py` under the package's `commands/` tree, read as text."""
    offenders = {
        path.name: [name for name in _RETIRED_MODULES if name in path.read_text(encoding="utf-8")]
        for path in sorted(_COMMANDS.glob("*.py"))
    }
    assert {name: hits for name, hits in offenders.items() if hits} == {}


def test_the_two_authoritative_fallback_history_records_still_exist() -> None:
    """The control: the clause replaced the projection, it did not empty it."""
    selection = importlib.import_module(f"{_PACKAGE}._acp_node_selection")
    release = importlib.import_module(f"{_PACKAGE}._dispatcher_provider_limit_records")

    assert selection.ACP_NODE_SELECTION_STAGE == "acp-node-selection"
    assert release.PROVIDER_LIMIT_RELEASE_STAGE == "provider-limit-release"


def test_the_dispatch_pass_still_writes_both_of_those_records() -> None:
    """Present as a CONSTANT is not present as a WRITER; assert the writers."""
    selection = importlib.import_module(f"{_PACKAGE}._acp_node_selection")
    disposition = importlib.import_module(f"{_PACKAGE}._dispatcher_provider_limit_disposition")

    assert callable(selection.acp_node_selection_record)
    assert callable(disposition.dispose_provider_limit_release)


def test_the_events_read_bound_survives_for_the_cost_path() -> None:
    """The retired module declared it; the cost chain's own read still needs it."""
    cost_chain = importlib.import_module(f"{_PACKAGE}._dispatcher_cost_chain")

    assert cost_chain.ACP_EVENTS_TIMEOUT_SECONDS == 30.0
