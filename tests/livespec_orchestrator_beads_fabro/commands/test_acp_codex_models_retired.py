"""The RETIRED `dispatcher.codex_models` shorthand, and the migration it prints.

Binds `SPECIFICATION/contracts.md` section "Built-in ACP node defaults":
"`dispatcher.codex_models` is retired. A repository routes a node to Codex by
writing a structured entry whose `agent` is `codex-acp` for THAT node; no
class-shaped shorthand exists. A `.livespec.jsonc` that sets
`dispatcher.codex_models` MUST refuse before claim, and the refusal MUST print
the equivalent `dispatcher.acp_nodes` entries -- `{"agent": "codex-acp",
"model": <model>, "effort": <reasoning_effort>}` under each node the retired
class covered (`implement`, `fix` and `review_fix` for `implementer`; `pr` for
`pr`) -- so the migration is a copy."

REFUSAL IS ASSERTED THROUGH THE REPOSITORY LAYER THE DISPATCH ACTUALLY READS,
not against a predicate. `repository_acp_overlays` is what
`_dispatcher_acp_nodes.prepare_acp_nodes` calls, and its string return is what
`_dispatcher_loop_materialize.materialize_dispatch` turns into a
`MaterializationRefusal` -- which is the "before claim" the contract names,
because it is reached before any Fabro run exists. A test asserting that some
helper CAN produce the message would pass equally against a build that never
called it.

THE MIGRATION IS ASSERTED AS A COPY, WHICH IS A STRONGER CLAIM THAN "MENTIONS
THE NODE". The contract's stated purpose for the printed entries is that an
operator can copy them, so each expected entry is written out here as the exact
JSON object a reader would paste, and the refusal has to contain those bytes.
Asserting only that the node NAMES appear would pass against a message that
listed them and left the operator to re-derive the model and effort -- which is
the one thing the retirement takes away from them.

THE UN-PINNED TIER MIGRATES TO THE MANUAL FORM, NOT TO A STRUCTURED ENTRY. The
same section says the opt-out "is a MANUAL-form candidate" and that "there is no
structured spelling of the opt-out", so a faithful copy of a `model: ""` tier
cannot be a structured entry; printing one would re-pin a node the operator had
deliberately un-pinned.
"""

from __future__ import annotations

import importlib
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

# The retired built-in tier values, restated rather than imported. A test
# reading them from the module under test could not tell a deliberate change
# from a regression, and these are exactly the values an operator's migration
# has to preserve.
_IMPLEMENTER_ENTRY = '{"agent": "codex-acp", "model": "gpt-5.5", "effort": "low"}'
_PR_ENTRY = '{"agent": "codex-acp", "model": "gpt-5.3-codex-spark", "effort": "high"}'

_IMPLEMENTER_NODES = ("implement", "fix", "review_fix")


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _overlays(*, block: dict[str, Any]) -> Any:
    """The repository layer resolved for one dispatcher block, or its refusal.

    The catalogs are resolved from the same block and asserted well-formed, so a
    catalog fault cannot give any case below a second, silent way to pass.
    """
    catalogs = _module(name="_acp_catalogs").resolve_acp_catalogs(block=block)
    assert not isinstance(catalogs, str), catalogs
    return _module(name="_acp_node_repository").repository_acp_overlays(
        block=block, catalogs=catalogs
    )


def test_a_configured_implementer_tier_refuses_naming_the_retired_key() -> None:
    """Setting `codex_models` refuses, and the refusal names the retired key."""
    refusal = _overlays(block={"codex_models": {"implementer": {"model": "gpt-5.5"}}})

    assert isinstance(refusal, str), (
        "dispatcher.codex_models must refuse before claim; "
        f"the repository layer resolved it instead and returned {refusal!r}"
    )
    assert "dispatcher.codex_models" in refusal
    assert "retired" in refusal


def test_the_implementer_tier_prints_a_copyable_entry_for_each_node_it_covered() -> None:
    """Every node the `implementer` class covered gets its structured entry."""
    refusal = _overlays(block={"codex_models": {"implementer": {}}})

    assert isinstance(refusal, str), refusal
    for node in _IMPLEMENTER_NODES:
        assert (
            f"dispatcher.acp_nodes.{node}" in refusal
        ), f"the migration must name {node!r}, which the retired implementer class covered"
    assert refusal.count(_IMPLEMENTER_ENTRY) == len(_IMPLEMENTER_NODES), (
        "each covered node must carry the copyable structured entry, "
        f"expected {_IMPLEMENTER_ENTRY!r} in:\n{refusal}"
    )
    assert (
        "dispatcher.acp_nodes.pr" not in refusal
    ), "the pr node was NOT covered by the implementer class and must not be printed"


def test_the_pr_tier_prints_only_the_pr_node_entry() -> None:
    """The `pr` class covered exactly one node, and the migration says so."""
    refusal = _overlays(block={"codex_models": {"pr": {}}})

    assert isinstance(refusal, str), refusal
    assert (
        f"dispatcher.acp_nodes.pr: {_PR_ENTRY}" in refusal
    ), f"expected the pr entry {_PR_ENTRY!r} in:\n{refusal}"
    for node in _IMPLEMENTER_NODES:
        assert f"dispatcher.acp_nodes.{node}" not in refusal


def test_an_operators_own_model_and_effort_survive_into_the_printed_entry() -> None:
    """The copy preserves what the operator wrote, not the built-in default."""
    refusal = _overlays(
        block={"codex_models": {"pr": {"model": "gpt-5.6-terra", "reasoning_effort": "xhigh"}}}
    )

    assert isinstance(refusal, str), refusal
    assert '{"agent": "codex-acp", "model": "gpt-5.6-terra", "effort": "xhigh"}' in refusal


def test_the_un_pinned_opt_out_migrates_to_the_manual_form() -> None:
    """A `model: ""` tier has no structured spelling, so the copy is manual."""
    refusal = _overlays(block={"codex_models": {"pr": {"model": ""}}})

    assert isinstance(refusal, str), refusal
    assert '"agent": "codex-acp"' not in refusal, (
        "an un-pinned tier must NOT migrate to a structured entry; "
        f"that would re-pin a node the operator un-pinned:\n{refusal}"
    )
    assert (
        "/opt/livespec/codex-acp/bin/codex-acp" in refusal
    ), f"the un-pinned copy is the manual-form base string:\n{refusal}"


def test_a_malformed_codex_models_value_still_refuses_rather_than_crashing() -> None:
    """The key's PRESENCE is what is retired, not any particular shape.

    A non-table value, and a non-table class entry under one, are the two
    shapes with nothing in them to copy. Both must still refuse: the contract
    retires the key itself, and the alternative to refusing is an uncaught
    AttributeError from reaching into a string as though it were a table --
    a crash where the operator should be reading a migration.
    """
    for value in ("gpt-5.5", ["implementer"], 7, {"implementer": "gpt-5.5"}):
        refusal = _overlays(block={"codex_models": value})

        assert isinstance(
            refusal, str
        ), f"a codex_models of {value!r} must still refuse; got {refusal!r}"
        assert "dispatcher.codex_models" in refusal
        assert "retired" in refusal


def test_a_block_that_sets_no_codex_models_resolves_normally() -> None:
    """The control: the retirement refuses the key, never every dispatch."""
    overlays = _overlays(block={})

    assert not isinstance(overlays, str), overlays
    assert dict(overlays) == {}
