"""Scenarios 87 and 88, driven through the dispatch seam a real dispatch uses.

Binds `SPECIFICATION/scenarios.md` "## Scenario 87 — A node's adapter resolves
through three layers and the record names the supplying layer" and
"## Scenario 88 — An arbitrary adapter with an env map and args renders without
a code change". Both heading-coverage entries owed an integration-tier test.

SO EVERY CASE STARTS FROM A COMMITTED `.livespec.jsonc` ON DISK AND THIS
REPOSITORY'S OWN COMMITTED `workflow.toml`, and resolves them through
`prepare_acp_nodes` — the one function a dispatch calls. That is the whole
content of the tier here: the unit-tier file
`tests/livespec_orchestrator_beads_fabro/commands/test_acp_node_layers.py`
grades the merge against overlays handed to it, and a merge can be perfectly
correct while nothing joins it to the configuration an operator writes or to
the record a triager later reads. Nothing below constructs an overlay, a
catalog entry or a workflow input by hand.

THE WORKFLOW LAYER IS THE REAL COMMITTED ONE, deliberately, because it is the
half a fixture cannot stand in for: a fixture workflow would keep every
assertion below true while the shipped workflow stopped declaring an adapter
input for a node, which is exactly how a node becomes unconfigurable while the
journal still reports the adapter it was told to run.

NO ASSERTION HERE NAMES AN AGENT OR A MODEL. Which model a factory node runs is
an operator dial (`tests/conftest.py` `_no_test_reads_the_committed_acp_routing`,
maintainer ruling 2026-10-18), so the committed defaults are asserted
STRUCTURALLY — which layer supplied each field, and that the env segment is
sorted and precedes the command — never by their text. That is also what
Scenarios 87 and 88 actually say: the claims are about precedence, attribution
and render ORDER, not about any particular endpoint.

AND THE RENDERED BYTES ARE ASSERTED AS A SUFFIX RATHER THAN WHOLE, for the same
reason: a repository entry supplying a `command` still MERGES the workflow
default's env over which it sits, so the full string necessarily carries the
committed dial's values. The suffix is the part Scenario 88 fixes — the command
followed by its args in order — and the sorted-env property is asserted over
whatever keys the merge produced.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import (
    DISPATCH_LAYER,
    REPOSITORY_LAYER,
    WORKFLOW_LAYER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_nodes import (
    ACP_NODES_STAGE,
    prepare_acp_nodes,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMMITTED_WORKFLOW = (
    _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
)

# A command no catalog knows and no provider serves, so it can only have
# arrived from the layer that declared it.
_LOCAL_ROUTER_COMMAND = "uvx --from local-router local-acp"
_PROVIDER_ARGS = ("-c", "model_provider=local-llm-fleet", "-c", "model=qwen3-coder-next")
_ROUTER_ENV = {
    "ZZ_ROUTER_TRAILER": "last-in-sorted-order",
    "AA_ROUTER_LEADER": "first-in-sorted-order",
    "MM_ROUTER_MIDDLE": "between-the-two",
}


class _RecordingJournal:
    """The dispatch journal, kept in memory so the record can be read back."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _governed_repo(*, tmp_path: Path, acp_nodes: dict[str, object]) -> Path:
    """A governed repository whose committed configuration declares `acp_nodes`."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "git_author": {
                    "operator_name": "Operator",
                    "operator_email": "operator@example.com",
                },
                "livespec-orchestrator-beads-fabro": {"dispatcher": {"acp_nodes": acp_nodes}},
            }
        ),
        encoding="utf-8",
    )
    return repo


def _prepared(
    *,
    tmp_path: Path,
    acp_nodes: dict[str, object],
    overrides: tuple[str, ...] = (),
) -> tuple[Any, _RecordingJournal]:
    """Resolve one dispatch's adapters, returning the resolution and the journal."""
    journal = _RecordingJournal()
    resolution = prepare_acp_nodes(
        repo=_governed_repo(tmp_path=tmp_path, acp_nodes=acp_nodes),
        committed=_COMMITTED_WORKFLOW,
        overrides=overrides,
        journal=journal,
        work_item_id="bd-ib-tghmyn",
    )
    return resolution, journal


def _journaled_nodes(*, journal: _RecordingJournal) -> dict[str, Any]:
    """The one ACP record this dispatch wrote, as `node -> projection`."""
    [record] = [entry for entry in journal.records if entry["stage"] == ACP_NODES_STAGE]
    nodes: Any = record["acp_nodes"]
    return dict(nodes)


def _env_segment(*, rendered: str, command: str) -> list[str]:
    """The `NAME=value` words a rendered adapter carries ahead of its command."""
    head, separator, _tail = rendered.partition(command)
    assert separator == command, f"the command is absent from {rendered!r}"
    return head.split()


def test_scenario87_a_repository_entry_overrides_the_workflow_default_for_one_node_only(
    tmp_path: Path,
) -> None:
    """The entry wins for `implement`, every other node keeps its default, and the record says so."""
    resolution, journal = _prepared(
        tmp_path=tmp_path,
        acp_nodes={"implement": {"command": _LOCAL_ROUTER_COMMAND}},
    )

    assert not isinstance(resolution, str), resolution
    assert resolution.nodes["implement"].adapter.command == _LOCAL_ROUTER_COMMAND
    nodes = _journaled_nodes(journal=journal)
    assert nodes["implement"]["layers"]["command"] == REPOSITORY_LAYER
    # SCOPED TO THE NODE CONFIGURED. Every OTHER node the workflow declares an
    # adapter input for must still be attributed to the workflow, which is the
    # half a too-broad override would break while `implement` still looked right.
    others = {node for node in nodes if node != "implement"}
    assert others
    assert {nodes[node]["layers"]["command"] for node in others} == {WORKFLOW_LAYER}
    assert _LOCAL_ROUTER_COMMAND not in json.dumps({node: nodes[node] for node in others})


def test_scenario87_a_per_dispatch_argument_overrides_the_repository_entry_and_is_journaled(
    tmp_path: Path,
) -> None:
    """The argument wins for the key it names, the entry's other keys survive, and both are attributed."""
    resolution, journal = _prepared(
        tmp_path=tmp_path,
        acp_nodes={
            "implement": {
                "command": _LOCAL_ROUTER_COMMAND,
                "env": dict(_ROUTER_ENV),
            }
        },
        overrides=(f"implement=AA_ROUTER_LEADER=from-the-dispatch {_LOCAL_ROUTER_COMMAND}",),
    )

    assert not isinstance(resolution, str), resolution
    env = dict(resolution.nodes["implement"].adapter.env)
    assert env["AA_ROUTER_LEADER"] == "from-the-dispatch"
    # The repository's OTHER keys are preserved, which is why moving one
    # variable per dispatch does not mean restating an environment.
    assert env["MM_ROUTER_MIDDLE"] == _ROUTER_ENV["MM_ROUTER_MIDDLE"]
    assert env["ZZ_ROUTER_TRAILER"] == _ROUTER_ENV["ZZ_ROUTER_TRAILER"]
    layers = _journaled_nodes(journal=journal)["implement"]["layers"]["env"]
    # Per-KEY attribution: one node's env carries values from two layers at
    # once, so a record naming a single layer for the whole map could not tell
    # a triager which variable the dispatch argument actually moved.
    assert layers["AA_ROUTER_LEADER"] == DISPATCH_LAYER
    assert layers["MM_ROUTER_MIDDLE"] == REPOSITORY_LAYER
    assert layers["ZZ_ROUTER_TRAILER"] == REPOSITORY_LAYER


def test_scenario87_a_per_dispatch_value_cannot_arrive_through_the_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ambient environment is not a layer, so setting it changes nothing.

    The variables planted below are exactly the ones an operator might expect
    to be honoured, and the rendered adapter must be byte-identical with and
    without them — which is the only way to show the resolution reads none of
    them rather than happening to agree with them.
    """
    acp_nodes: dict[str, object] = {"implement": {"command": _LOCAL_ROUTER_COMMAND}}
    before, _journal = _prepared(tmp_path=tmp_path, acp_nodes=acp_nodes)
    assert not isinstance(before, str), before

    for name in ("ANTHROPIC_MODEL", "ANTHROPIC_BASE_URL", "LIVESPEC_ACP_NODE"):
        monkeypatch.setenv(name, "the-environment-must-not-win")
    after, _again = _prepared(tmp_path=tmp_path / "second", acp_nodes=acp_nodes)

    assert not isinstance(after, str), after
    assert after.nodes["implement"].rendered == before.nodes["implement"].rendered


def test_scenario87_a_layer_naming_an_unknown_node_refuses_before_any_run_exists(
    tmp_path: Path,
) -> None:
    """A typo'd node refuses NAMING it, and journals no resolution.

    The journal is asserted empty of the ACP record for the reason the refusal
    exists: a dispatch that refused and still journaled a resolved node set
    would read, afterwards, exactly like one that had been admitted.
    """
    refusal, journal = _prepared(tmp_path=tmp_path, acp_nodes={"implemnt": "uvx typo-acp"})

    assert isinstance(refusal, str)
    assert "implemnt" in refusal
    assert [entry for entry in journal.records if entry["stage"] == ACP_NODES_STAGE] == []


def test_scenario88_an_env_map_renders_in_sorted_key_order_ahead_of_the_command(
    tmp_path: Path,
) -> None:
    """The three router keys render sorted, before the command, with no code change.

    They are DELIBERATELY declared out of order in `_ROUTER_ENV`, so a render
    that preserved declaration order — or the mapping's own iteration order —
    fails rather than coinciding with the answer.
    """
    resolution, _journal = _prepared(
        tmp_path=tmp_path,
        acp_nodes={
            "implement": {
                "command": _LOCAL_ROUTER_COMMAND,
                "env": dict(_ROUTER_ENV),
            }
        },
    )

    assert not isinstance(resolution, str), resolution
    rendered = resolution.nodes["implement"].rendered
    assert rendered.endswith(_LOCAL_ROUTER_COMMAND)
    words = _env_segment(rendered=rendered, command=_LOCAL_ROUTER_COMMAND)
    assert words == sorted(words)
    for name, value in _ROUTER_ENV.items():
        assert f"{name}={value}" in words


def test_scenario88_an_adapter_with_provider_definition_args_renders_them_in_order(
    tmp_path: Path,
) -> None:
    """A node's args follow its command verbatim, in declaration order.

    Args are the half an env map cannot express — a provider definition is
    positional — and order is load-bearing for them, which is why they are
    asserted as an exact suffix rather than as a set.
    """
    resolution, _journal = _prepared(
        tmp_path=tmp_path,
        acp_nodes={
            "review_fix": {
                "command": _LOCAL_ROUTER_COMMAND,
                "args": list(_PROVIDER_ARGS),
            }
        },
    )

    assert not isinstance(resolution, str), resolution
    review_fix = resolution.nodes["review_fix"]
    assert review_fix.adapter.args == _PROVIDER_ARGS
    suffix = " ".join((_LOCAL_ROUTER_COMMAND, *_PROVIDER_ARGS))
    assert review_fix.rendered.endswith(suffix)
