"""The implement node's adapter label, for grouping calibration by adapter.

Plan slice S3's board groups post-hoc Red share by repository AND by adapter,
so the terminal calibration span needs a bounded adapter label. It is derived
from the `acp-nodes` journal record the dispatch already wrote, classified
against the COMMITTED agent catalog's launch distributions — never parsed by
hand out of a command line, because the catalog is the one place that knows
which bytes belong to which registry agent id.
"""

from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.commands._acp_agent_catalog import (
    CLAUDE_AGENT_ID,
    CODEX_AGENT_ID,
    builtin_agent_catalog,
)

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_implement_adapter"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_implement_adapter.py"
)


def _module() -> ModuleType:
    """Import the module under test, asserting it exists first."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


def _acp_nodes_record(*, nodes: dict[str, object], work_item_id: str = "bd-ib-3h5vfq") -> dict:
    return {"stage": "acp-nodes", "work_item_id": work_item_id, "acp_nodes": nodes}


def test_a_rendered_claude_adapter_classifies_as_the_claude_registry_agent() -> None:
    module = _module()
    rendered = builtin_agent_catalog()[CLAUDE_AGENT_ID].command

    label = module.implement_adapter_label(
        records=(
            _acp_nodes_record(
                nodes={
                    "implement": {
                        "input": "implement_adapter",
                        "adapter": f"ANTHROPIC_MODEL=claude-opus-5 {rendered}",
                    }
                }
            ),
        ),
        work_item_id="bd-ib-3h5vfq",
    )

    assert label == CLAUDE_AGENT_ID


def test_the_structural_record_form_classifies_from_command_and_args() -> None:
    module = _module()
    entry = builtin_agent_catalog()[CODEX_AGENT_ID]

    label = module.implement_adapter_label(
        records=(
            _acp_nodes_record(
                nodes={
                    "implement": {
                        "input": "implement_adapter",
                        "command": entry.command,
                        "args": list(entry.args),
                        "env_keys": ["CODEX_CONFIG"],
                        "primary_generation_digest": "deadbeef",
                    }
                }
            ),
        ),
        work_item_id="bd-ib-3h5vfq",
    )

    assert label == CODEX_AGENT_ID


def test_the_latest_resolution_for_the_item_wins() -> None:
    module = _module()
    claude = builtin_agent_catalog()[CLAUDE_AGENT_ID].command
    codex = builtin_agent_catalog()[CODEX_AGENT_ID].command

    label = module.implement_adapter_label(
        records=(
            _acp_nodes_record(nodes={"implement": {"adapter": claude}}),
            _acp_nodes_record(nodes={"implement": {"adapter": codex}}),
        ),
        work_item_id="bd-ib-3h5vfq",
    )

    assert label == CODEX_AGENT_ID


def test_another_items_resolution_is_not_read() -> None:
    module = _module()
    claude = builtin_agent_catalog()[CLAUDE_AGENT_ID].command

    label = module.implement_adapter_label(
        records=(
            _acp_nodes_record(nodes={"implement": {"adapter": claude}}, work_item_id="bd-ib-other"),
        ),
        work_item_id="bd-ib-3h5vfq",
    )

    assert label is None


def test_an_adapter_no_catalog_entry_explains_is_labelled_unknown() -> None:
    module = _module()

    label = module.implement_adapter_label(
        records=(
            _acp_nodes_record(nodes={"implement": {"adapter": "/opt/private/some-acp --serve"}}),
        ),
        work_item_id="bd-ib-3h5vfq",
    )

    assert label == module.UNKNOWN_ADAPTER


def test_no_acp_nodes_record_reads_as_unobservable() -> None:
    module = _module()

    assert (
        module.implement_adapter_label(
            records=({"stage": "outcome", "work_item_id": "bd-ib-3h5vfq"},),
            work_item_id="bd-ib-3h5vfq",
        )
        is None
    )
    assert module.implement_adapter_label(records=(), work_item_id="bd-ib-3h5vfq") is None


def test_a_record_with_no_implement_node_reads_as_unobservable() -> None:
    module = _module()
    claude = builtin_agent_catalog()[CLAUDE_AGENT_ID].command

    assert (
        module.implement_adapter_label(
            records=(_acp_nodes_record(nodes={"review": {"adapter": claude}}),),
            work_item_id="bd-ib-3h5vfq",
        )
        is None
    )


def test_a_malformed_record_shape_reads_as_unobservable() -> None:
    module = _module()

    for nodes in ("not a mapping", {"implement": "not a mapping"}, {}):
        assert (
            module.implement_adapter_label(
                records=(_acp_nodes_record(nodes=nodes),),  # pyright: ignore[reportArgumentType]
                work_item_id="bd-ib-3h5vfq",
            )
            is None
        )
    assert (
        module.implement_adapter_label(
            records=({"stage": "acp-nodes", "work_item_id": "bd-ib-3h5vfq"},),
            work_item_id="bd-ib-3h5vfq",
        )
        is None
    )


def test_a_structural_record_with_unusable_command_and_args_is_unknown() -> None:
    module = _module()

    label = module.implement_adapter_label(
        records=(_acp_nodes_record(nodes={"implement": {"command": 7, "args": ["ok", 9]}}),),
        work_item_id="bd-ib-3h5vfq",
    )

    assert label == module.UNKNOWN_ADAPTER


def test_the_longest_matching_catalog_command_wins() -> None:
    module = _module()
    claude = builtin_agent_catalog()[CLAUDE_AGENT_ID]
    short = replace(claude, agent_id="npx-only", command="npx")

    label = module.adapter_label_for(
        text=f"ANTHROPIC_MODEL=claude-opus-5 {claude.command}",
        catalog={"npx-only": short, CLAUDE_AGENT_ID: claude},
    )

    assert label == CLAUDE_AGENT_ID
