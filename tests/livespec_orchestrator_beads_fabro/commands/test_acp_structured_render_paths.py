"""The structured render's remaining decision paths, driven one by one.

Companion to `test_acp_structured_render`, which binds the acceptance assertion
(a structured entry renders into the manual form, deterministically, before the
merge). This module exercises the DECISIONS that assertion's cases do not reach:
the two mechanisms no shipped agent renders through a committed entry, the
carrier fallback, and each refusal the resolver can produce.

WHY THE UNRENDERED MECHANISMS NEED A CASE AT ALL. `arg` and `protocol` are
ratified spellings of the mechanism grammar -- `SPECIFICATION/contracts.md`
section "Agent and model catalogs" makes the mapping "EXACTLY ONE of `protocol`
... or an explicit per-agent environment or argument mapping" -- and no SHIPPED
entry uses `arg` today. An unexercised branch in a renderer is one whose first
real use is an operator's dispatch, so each is driven here through a
repository-supplied agent entry, which is the very surface an operator would
reach for.

EVERY REFUSAL IS CHECKED ON ITS MESSAGE. A refusal an operator cannot map back
to a configuration line is the failure the closed grammar exists to remove, so
each case asserts the fully-qualified key is in the text rather than merely that
a string came back.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_KEY = "dispatcher.acp_nodes.implement"

_WORKFLOW_INPUTS: dict[str, str] = {
    "implement_adapter": "WORKFLOW=implement placeholder-adapter",
    "fix_adapter": "WORKFLOW=fix placeholder-adapter",
    "review_fix_adapter": "WORKFLOW=review_fix placeholder-adapter",
    "pr_adapter": "WORKFLOW=pr placeholder-adapter",
    "review_adapter": "WORKFLOW=review placeholder-adapter",
    "disposition_adapter": "WORKFLOW=disposition placeholder-adapter",
}


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _agent(*, mechanism: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    """One repository-supplied agent entry, complete under the closed grammar."""
    return {
        "display_name": "Local Agent",
        "account_domain": "local-allowance",
        "provider": "local",
        "version": "1.0.0",
        "command": "/opt/local/bin/local-acp",
        "mechanism": mechanism,
        "effort_levels": ["low", "high"],
        **overrides,
    }


def _local_model() -> dict[str, Any]:
    return {"local/local-1": {"display_name": "Local 1"}}


def _resolved(*, block: dict[str, Any]) -> Any:
    catalogs = _module(name="_acp_catalogs").resolve_acp_catalogs(block=block)
    if isinstance(catalogs, str):
        return catalogs
    overlays = _module(name="_acp_node_repository").repository_acp_overlays(
        block=block, catalogs=catalogs
    )
    if isinstance(overlays, str):
        return overlays
    return _module(name="_acp_node_layers").resolve_acp_nodes(
        workflow_inputs=_WORKFLOW_INPUTS, repository=overlays, dispatch={}
    )


def _rendered_implement(*, block: dict[str, Any]) -> str:
    resolution = _resolved(block=block)
    assert not isinstance(resolution, str), resolution
    return resolution.nodes["implement"].rendered


def test_an_arg_mechanism_renders_its_template_as_argv_tokens() -> None:
    """An argument mapping appends the tokens its template expands to.

    The template is shell-tokenized after substitution, so one setting may
    contribute several argv tokens -- `-c model=<value>` is two, which is the
    shape the retired Codex `-c` form had and the reason the grammar is a
    template rather than a flag name.
    """
    rendered = _rendered_implement(
        block={
            "agent_catalog": {
                "local-acp": _agent(
                    mechanism={
                        "kind": "arg",
                        "model": "-c model={value}",
                        "effort": "-c model_reasoning_effort={value}",
                    }
                )
            },
            "model_catalog": _local_model(),
            "acp_nodes": {
                "implement": {"agent": "local-acp", "model": "local-1", "effort": "high"}
            },
        }
    )

    assert rendered == ("/opt/local/bin/local-acp -c model=local-1 -c model_reasoning_effort=high")


def test_a_protocol_mechanism_renders_the_launch_distribution_untouched() -> None:
    """In-protocol selection puts NOTHING into the adapter.

    The requested values ride the rendered chain's `config_options` instead, so
    the adapter bytes are the launch distribution exactly. Asserting that is what
    separates the two mechanisms: an implementation that also wrote the model
    into the environment would satisfy every other case in this module.
    """
    rendered = _rendered_implement(
        block={
            "agent_catalog": {
                "local-acp": _agent(
                    mechanism={"kind": "protocol", "model": "model", "effort": "effort"},
                    env={"LOCAL_MODE": "write"},
                )
            },
            "model_catalog": _local_model(),
            "acp_nodes": {
                "implement": {"agent": "local-acp", "model": "local-1", "effort": "high"}
            },
        }
    )

    assert rendered == "LOCAL_MODE=write /opt/local/bin/local-acp"
    assert "local-1" not in rendered


def test_a_json_carrier_the_entry_declares_no_object_for_starts_empty() -> None:
    """An agent taking its whole session configuration from the pin alone.

    The carrier is absent from the entry's `env`, so the render starts from the
    empty object rather than refusing: there is nothing to preserve, and
    refusing would forbid a legitimate agent shape.
    """
    rendered = _rendered_implement(
        block={
            "agent_catalog": {
                "local-acp": _agent(
                    mechanism={
                        "kind": "json_env",
                        "env": "LOCAL_CONFIG",
                        "model": "model",
                        "effort": "effort",
                    }
                )
            },
            "model_catalog": _local_model(),
            "acp_nodes": {
                "implement": {"agent": "local-acp", "model": "local-1", "effort": "high"}
            },
        }
    )

    assert rendered == (
        'LOCAL_CONFIG=\'{"effort":"high","model":"local-1"}\' /opt/local/bin/local-acp'
    )


def test_a_json_carrier_holding_something_other_than_an_object_refuses_at_parse_time() -> None:
    """The render MERGES into that object, so a non-object has nothing to merge into.

    Catching it in the catalog parser rather than in the renderer is what keeps
    the renderer a total function: the alternative surfaces as a crash inside
    layer resolution, nowhere near the configuration line at fault.
    """
    for carried in ("not json", "[1, 2]", '"a string"'):
        refusal = _module(name="_acp_agent_catalog").resolve_agent_catalog(
            block={
                "agent_catalog": {
                    "local-acp": _agent(
                        mechanism={
                            "kind": "json_env",
                            "env": "LOCAL_CONFIG",
                            "model": "model",
                        },
                        env={"LOCAL_CONFIG": carried},
                    )
                }
            }
        )
        assert isinstance(refusal, str), carried
        assert "dispatcher.agent_catalog.local-acp.env['LOCAL_CONFIG']" in refusal, carried


def test_a_json_carrier_is_checked_on_the_read_only_environment_too() -> None:
    """Both declared environments are carriers, so both are checked.

    A read-only posture holding unparseable configuration would pass a
    write-environment-only check and then fail at the one node that uses it --
    which is the node a reviewer runs, so the failure would surface as a review
    outage rather than as a configuration error.
    """
    refusal = _module(name="_acp_agent_catalog").resolve_agent_catalog(
        block={
            "agent_catalog": {
                "local-acp": _agent(
                    mechanism={"kind": "json_env", "env": "LOCAL_CONFIG", "model": "model"},
                    env={"LOCAL_CONFIG": "{}"},
                    read_only_env={"LOCAL_CONFIG": "not json"},
                )
            }
        }
    )

    assert isinstance(refusal, str)
    assert "dispatcher.agent_catalog.local-acp.env['LOCAL_CONFIG']" in refusal


def test_an_agent_absent_from_the_catalog_refuses_naming_it() -> None:
    """The first of the section's two lookup failures."""
    refusal = _resolved(
        block={"acp_nodes": {"implement": {"agent": "psychic-acp", "model": "any"}}}
    )

    assert isinstance(refusal, str)
    assert f"{_KEY}.agent" in refusal
    assert "'psychic-acp'" in refusal
    assert "claude-acp" in refusal


def test_a_model_the_catalog_does_not_declare_for_that_provider_refuses() -> None:
    """The second lookup failure, and the remedy is named in the message."""
    refusal = _resolved(
        block={"acp_nodes": {"implement": {"agent": "claude-acp", "model": "claude-opus-99"}}}
    )

    assert isinstance(refusal, str)
    assert f"{_KEY}.model" in refusal
    assert "anthropic" in refusal
    assert "dispatcher.model_catalog" in refusal


def test_an_effort_the_agent_does_not_declare_refuses_naming_the_declared_levels() -> None:
    """The third refusal the section requires before claim."""
    refusal = _resolved(
        block={
            "acp_nodes": {
                "implement": {"agent": "claude-acp", "model": "claude-opus-5", "effort": "ultra"}
            }
        }
    )

    assert isinstance(refusal, str)
    assert f"{_KEY}.effort" in refusal
    assert "'ultra'" in refusal
    assert "low, medium, high" in refusal


def test_an_agent_declaring_no_effort_levels_refuses_any_declared_effort() -> None:
    """An agent with an empty level set has no admissible effort at all."""
    refusal = _resolved(
        block={
            "agent_catalog": {
                "local-acp": _agent(
                    mechanism={"kind": "env", "model": "LOCAL_MODEL"}, effort_levels=[]
                )
            },
            "model_catalog": _local_model(),
            "acp_nodes": {
                "implement": {"agent": "local-acp", "model": "local-1", "effort": "high"}
            },
        }
    )

    assert isinstance(refusal, str)
    assert "(none)" in refusal


def test_an_agent_whose_mechanism_has_no_effort_route_renders_the_model_alone() -> None:
    """A declared effort with nowhere to go is dropped rather than invented.

    This is the case an agent-level `effort_levels` declaration makes reachable:
    the level is admissible, and the mechanism still exposes no target for it, so
    the render carries the model and nothing else.
    """
    rendered = _rendered_implement(
        block={
            "agent_catalog": {
                "local-acp": _agent(mechanism={"kind": "env", "model": "LOCAL_MODEL"})
            },
            "model_catalog": _local_model(),
            "acp_nodes": {
                "implement": {"agent": "local-acp", "model": "local-1", "effort": "high"}
            },
        }
    )

    assert rendered == "LOCAL_MODEL=local-1 /opt/local/bin/local-acp"
    assert "high" not in rendered


def test_a_structured_entry_missing_agent_or_model_text_refuses() -> None:
    """The form's own two required fields, each named by its own key."""
    cases = (
        ({"agent": "claude-acp"}, "model"),
        ({"agent": "claude-acp", "model": ""}, "model"),
        ({"agent": "  ", "model": "claude-opus-5"}, "agent"),
        ({"agent": 7, "model": "claude-opus-5"}, "agent"),
    )
    for entry, field in cases:
        refusal = _resolved(block={"acp_nodes": {"implement": entry}})
        assert isinstance(refusal, str), entry
        assert f"{_KEY}.{field}" in refusal, (entry, refusal)


def test_a_structured_entry_declaring_an_unusable_effort_value_refuses() -> None:
    """A present-but-blank or wrong-typed `effort` is refused, not ignored."""
    for effort in ("", "   ", 3):
        refusal = _resolved(
            block={
                "acp_nodes": {
                    "implement": {
                        "agent": "claude-acp",
                        "model": "claude-opus-5",
                        "effort": effort,
                    }
                }
            }
        )
        assert isinstance(refusal, str), effort
        assert f"{_KEY}.effort" in refusal, (effort, refusal)


def test_a_catalog_refusal_reaches_the_overlay_resolver() -> None:
    """A broken catalog refuses the overlay resolution rather than the render.

    The order matters: a repository whose catalog will not parse cannot resolve a
    single structured entry, so the refusal has to name the catalog key rather
    than the node that happened to be read first.
    """
    refusal = _resolved(block={"agent_catalog": {"local-acp": {"display_name": "Local"}}})

    assert isinstance(refusal, str)
    assert "dispatcher.agent_catalog.local-acp" in refusal


def test_the_config_seam_resolves_both_catalogs_from_the_dispatch_target(tmp_path: Path) -> None:
    """The config-reading seam reads the SAME block the overlay resolver reads."""
    config = (
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"model_catalog": '
        '{"local/local-1": {"display_name": "Local 1"}}}}}'
    )
    _ = (tmp_path / ".livespec.jsonc").write_text(config, encoding="utf-8")
    catalogs = _module(name="_config_acp").resolve_acp_catalogs_for(cwd=tmp_path)

    assert not isinstance(catalogs, str), catalogs
    assert "local/local-1" in catalogs.models
    assert "claude-acp" in catalogs.agents


def test_the_overlay_seam_refuses_when_the_target_catalog_will_not_parse(tmp_path: Path) -> None:
    """A catalog fault refuses the overlay seam before any node resolves."""
    config = (
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"agent_catalog": '
        '{"local-acp": {"display_name": "Local"}}}}}'
    )
    _ = (tmp_path / ".livespec.jsonc").write_text(config, encoding="utf-8")
    refusal = _module(name="_config_acp").resolve_acp_node_overlays(cwd=tmp_path)

    assert isinstance(refusal, str)
    assert "dispatcher.agent_catalog.local-acp" in refusal
